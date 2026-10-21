"""Everything a person can do with their own memory: look at it, add to it, correct it, delete it.

All changes go through one lock and an atomic file write, so two requests at once cannot overwrite each other.
Each item reports where it came from (written by you, or suggested by a helper and accepted by you) and
how many answers it has been used in, so nothing in memory is a mystery.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Callable

from .quarantine import Quarantine, QuarantineError
from .tree import MemoryTree, pretty
from .vault import Record, Vault, clean_path, under
from .words import tokens

PAGE = 30
MAX_LABEL = 120


class MemoryChangeError(ValueError):
    """The change cannot be made; the message says why in plain words."""


class MemoryService:
    def __init__(self, vault_file: Path, quarantine: Quarantine, *, threads=None, registry=None,
                 clock: Callable[[], float], lock: threading.RLock | None = None):
        self.file, self.quarantine, self.threads, self.registry, self.clock = Path(vault_file), quarantine, threads, registry, clock
        self.lock = lock or threading.RLock()
        self._cache, self._overview = None, None
        self.labels_file = self.file.with_name("shelves.json")  # the short notes a person wrote about their shelves

    # -- the shelf notes -------------------------------------------------------------------------
    def labels(self) -> dict:
        try:
            raw = json.loads(self.labels_file.read_text(encoding="utf-8"))
            return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
        except (OSError, ValueError):
            return {}

    def _save_labels(self, labels: dict) -> None:
        tmp = self.labels_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(labels, indent=1), encoding="utf-8")
        os.replace(tmp, self.labels_file)

    def set_label(self, path: str, text: str) -> dict:
        path = self._path(path)
        if not isinstance(text, str) or len(text.strip()) > MAX_LABEL:
            raise MemoryChangeError(f"a note about a shelf can be at most {MAX_LABEL} characters")
        text = text.strip()
        with self.lock:
            if path not in MemoryTree(self.vault().all()).nodes:
                raise MemoryChangeError("that shelf does not exist")
            labels = self.labels()
            if text:
                labels[path] = text
            else:
                labels.pop(path, None)
            self._save_labels(labels)
        return {"path": path, "label": text}

    # -- reading ---------------------------------------------------------------------------------
    def _stamp(self):
        try:
            st = self.file.stat()
            lab = self.labels_file.stat().st_mtime_ns if self.labels_file.exists() else 0
            return (st.st_mtime_ns, st.st_size, lab)
        except OSError:
            return None

    def vault(self) -> Vault:
        """The vault as it is on disk now. Reading is cached until the file changes, so a big memory is parsed once, not on every screen refresh."""
        with self.lock:
            stamp = self._stamp()
            if stamp is not None and self._cache and self._cache[0] == stamp:
                return self._cache[1]
            v = Vault.load(self.file)
            self._cache, self._overview = (stamp, v), None
            return v

    def _helper_names(self) -> dict:
        names = {}
        if self.registry is not None:
            for r in self.registry.records.values():
                names[r.digest] = r.id.replace("-", " ").title()
        return names

    def _usage(self) -> dict[str, dict]:
        use: dict[str, dict] = {}
        if self.threads is None:
            return use
        with self.threads.lock:
            for t in self.threads.threads.values():
                for m in t.messages:
                    for fid in m.files:
                        u = use.setdefault(fid, {"answers": 0, "last_chat": "", "last_at": 0.0})
                        u["answers"] += 1
                        if m.at >= u["last_at"]:
                            u["last_at"], u["last_chat"] = m.at, t.title
        return use

    def _item(self, r: Record, use: dict, names: dict) -> dict:
        origin = r.origin or {}
        return {
            "id": r.id, "type": r.type, "sensitivity": "low" if r.sensitivity == "low" else "high", "text": r.text,
            "shelf": r.shelf, "shelf_name": pretty(r.shelf), "created": r.created, "updated": r.updated,
            "edited": r.edited, "trust": r.trust_tier,
            "source": "helper" if origin.get("pack_digest") else "you",
            "helper": names.get(origin.get("pack_digest"), "a helper") if origin.get("pack_digest") else None,
            "from_run": origin.get("run_id"),
            "used": use.get(r.id, {"answers": 0, "last_chat": "", "last_at": 0.0}),
        }

    def list(self, *, shelf: str | None = None, ids=None, q: str = "", offset: int = 0, limit: int = PAGE) -> list[dict]:
        """Files for the manager screen, one page at a time. `shelf` includes everything below it."""
        use, names = self._usage(), self._helper_names()
        recs = self.vault().all()
        if ids is not None:
            want = set(ids)
            recs = [r for r in recs if r.id in want]
        if shelf:
            recs = [r for r in recs if under(r.shelf, shelf)]
        if q.strip():
            qt = tokens(q)
            recs = [r for r in recs if qt & tokens(r.text + " " + r.shelf)]
        recs.sort(key=lambda r: (-(r.updated or r.created), r.id))
        start = max(0, offset)
        return [self._item(r, use, names) for r in recs[start:start + max(1, min(limit, 200))]]

    def overview(self) -> dict:
        """The whole tree without any file text: what the manager and the chat panels draw."""
        vault = self.vault()
        if self._overview is not None and self._cache and self._overview[0] == self._cache[0]:
            return self._overview[1]
        recs = vault.all()
        tree = MemoryTree(recs, self.labels())
        secret: dict[str, int] = {}
        for r in recs:
            if r.sensitivity != "low":
                p = r.shelf
                while True:
                    secret[p] = secret.get(p, 0) + 1
                    if "/" not in p:
                        break
                    p = p.rsplit("/", 1)[0]
        shelves = []

        def walk(path: str, depth: int):
            for o in tree.outline(path):
                shelves.append({**o, "depth": depth, "secret": secret.get(o["path"], 0), "parent": path,
                                "own": len(tree.nodes[o["path"]].own)})
                walk(o["path"], depth + 1)
        walk("", 0)
        out = {"total": len(recs), "secret": sum(1 for r in recs if r.sensitivity != "low"), "shelves": shelves}
        self._overview = (self._cache[0] if self._cache else None, out)
        return out

    # -- changing --------------------------------------------------------------------------------
    def _mutate(self, fn):
        with self.lock:
            v = Vault.load(self.file)
            out = fn(v)
            v.save(self.file)
            self._cache = self._overview = None  # the next reader sees the new file, never a stale copy
            return out

    @staticmethod
    def _level(sensitivity) -> str:
        """Two kinds of file: everyday (can be shared) and secret (never leaves). The old 'personal' counts as secret."""
        if sensitivity == "low":
            return "low"
        if sensitivity in ("medium", "high"):
            return "high"
        raise MemoryChangeError("choose everyday or secret")

    @staticmethod
    def _path(raw) -> str:
        try:
            return clean_path(raw or "")
        except ValueError as e:
            raise MemoryChangeError(str(e)) from e

    def _referenced(self) -> set[str]:
        """Ids that a chat's settings or past answers still point at; a new file must never take one over."""
        ids: set[str] = set()
        if self.threads is not None:
            with self.threads.lock:
                for t in self.threads.threads.values():
                    ids.update(t.lens.include, t.lens.exclude)
                    for m in t.messages:
                        ids.update(m.files)
        return ids

    def add(self, type: str, text: str, sensitivity: str, path: str = "") -> dict:
        now = self.clock()
        sensitivity, path = self._level(sensitivity), self._path(path)

        def go(v: Vault):
            rid = v.next_id("m")
            while rid in self._referenced():
                rid = "m" + str(int(rid[1:]) + 1)
            try:
                rec = Record(rid, type, sensitivity, (text or "").strip(), created=now, path=path)
            except ValueError as e:
                raise MemoryChangeError(str(e)) from e
            v.add(rec)
            return rec
        rec = self._mutate(go)
        return {"id": rec.id}

    def add_many(self, items: list, sensitivity: str, type: str, path: str = "") -> dict:
        """Save several notes at once (for example from an imported file), all or nothing."""
        if not isinstance(items, list) or not items or len(items) > 50:
            raise MemoryChangeError("add between 1 and 50 notes at a time")
        now = self.clock()
        sensitivity, path = self._level(sensitivity), self._path(path)

        def go(v: Vault):
            ids = []
            taken = self._referenced()
            for text in items:
                if not isinstance(text, str):
                    raise MemoryChangeError("each note must be text")
                rid = v.next_id("m")
                while rid in taken:
                    rid = "m" + str(int(rid[1:]) + 1)
                try:
                    v.add(Record(rid, type, sensitivity, text.strip(), created=now, path=path))
                except ValueError as e:
                    raise MemoryChangeError(str(e)) from e
                ids.append(rid)
            return ids
        return {"ids": self._mutate(go)}

    def update(self, record_id: str, *, text=None, sensitivity=None, type=None, path=None) -> dict:
        now = self.clock()

        for name, val in (("text", text), ("sensitivity", sensitivity), ("type", type), ("shelf", path)):
            if val is not None and not isinstance(val, str):
                raise MemoryChangeError(f"{name} must be text")
        sensitivity = None if sensitivity is None else self._level(sensitivity)
        path = None if path is None else self._path(path)

        def go(v: Vault):
            if v.get(record_id) is None:
                raise MemoryChangeError("that file is no longer in your memory")
            try:
                return v.update(record_id, now=now, text=None if text is None else text.strip(), sensitivity=sensitivity, type=type, path=path)
            except ValueError as e:
                raise MemoryChangeError(str(e)) from e
        rec = self._mutate(go)
        return {"id": rec.id, "edited": rec.edited}

    def move_shelf(self, source: str, target: str) -> dict:
        """Rename a shelf, or move it inside another one. Every file under it comes along; chats that had it open follow."""
        source, target = self._path(source), self._path(target)
        if not source or not target:
            raise MemoryChangeError("name the shelf and where it should go")
        if source == target:
            raise MemoryChangeError("that shelf is already there")
        if under(target, source):
            raise MemoryChangeError("a shelf cannot be moved into itself")

        def go(v: Vault):
            moved = [r for r in v.all() if under(r.shelf, source)]
            if not moved:
                raise MemoryChangeError("that shelf does not exist")
            for r in moved:
                new = target + r.shelf[len(source):]
                try:
                    v.update(r.id, now=self.clock(), path=self._path(new))
                except ValueError as e:
                    raise MemoryChangeError(str(e)) from e
            return len(moved)
        with self.lock:
            n = self._mutate(go)
            labels = self.labels()
            self._save_labels({(target + k[len(source):] if under(k, source) else k): v for k, v in labels.items()})
            if self.threads is not None:
                with self.threads.lock:
                    for t in self.threads.threads.values():
                        t.lens.shelves = sorted({(target + x[len(source):]) if under(x, source) else x for x in t.lens.shelves})
                    self.threads.save()
        return {"moved": n}

    def delete(self, record_id: str) -> dict:
        def go(v: Vault):
            if v.remove(record_id) is None:
                raise MemoryChangeError("that file is no longer in your memory")
        self._mutate(go)
        if self.threads is not None:  # it can no longer be shared, so every chat forgets it was ever picked
            with self.threads.lock:
                for t in self.threads.threads.values():
                    t.lens.include = [i for i in t.lens.include if i != record_id]
                    t.lens.exclude = [i for i in t.lens.exclude if i != record_id]
                self.threads.save()
        return {"deleted": record_id}

    # -- suggestions from helpers ------------------------------------------------------------------
    def accept_proposal(self, proposal_id: str) -> dict:
        try:
            rec = self._mutate(lambda v: self.quarantine.accept(proposal_id, v))
        except QuarantineError as e:
            raise MemoryChangeError(str(e)) from e
        return {"accepted": rec.id}

    def reject_proposal(self, proposal_id: str) -> dict:
        with self.lock:
            try:
                self.quarantine.reject(proposal_id)
            except QuarantineError as e:
                raise MemoryChangeError(str(e)) from e
        return {"rejected": proposal_id}

    def revert_run(self, run_id: str) -> dict:
        return self._mutate(lambda v: self.quarantine.revert_run(run_id, v))
