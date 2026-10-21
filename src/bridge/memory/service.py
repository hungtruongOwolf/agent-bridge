"""Everything a person can do with their own memory: look at it, add to it, correct it, delete it.

All changes go through one lock and one database transaction, so two requests at once cannot overwrite each other
and a change is stored whole or not at all.
Each item reports where it came from (written by you, or suggested by a helper and accepted by you) and
how many answers it has been used in, so nothing in memory is a mystery.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from .chunking import MAX_DOC, MAX_PARTS, SHORT, guess_title, join_document, split_document
from .quarantine import Quarantine, QuarantineError
from .safety_net import SafetyNet
from .tree import MemoryTree, pretty
from .vault import Record, Vault, clean_path, under
from .words import tokens
from ..storage.db import Database
from ..storage.memory_store import MemoryStore

PAGE = 30
MAX_LABEL = 120


class MemoryChangeError(ValueError):
    """The change cannot be made; the message says why in plain words."""


class MemoryService(SafetyNet):
    Error = MemoryChangeError

    def __init__(self, vault_file: Path, quarantine: Quarantine, *, threads=None, registry=None,
                 clock: Callable[[], float], lock: threading.RLock | None = None, seed: Path | None = None):
        """`vault_file` names where the memory lives (the database sits beside it, same name); an older JSON file of that name is
        imported once. `seed` is a starter set of notes, used only the very first time, when there is nothing yet."""
        self.file, self.quarantine, self.threads, self.registry, self.clock = Path(vault_file), quarantine, threads, registry, clock
        self.lock = lock or threading.RLock()
        self.store = MemoryStore(Database(self.file.with_suffix(".db")))
        self.store.import_legacy(self.file, clock())
        if self.store.is_empty() and seed is not None and Path(seed).exists():
            self.store.write_changes({}, {r.id: r for r in Vault.load(seed).all()})
        self.store.mark_seeded()
        self.quarantine.attach(self.store.proposals)
        self._vault, self._overview = self.store.load_vault(), None  # the notes stay in memory; a change writes only the rows it touches

    # -- the shelf notes -------------------------------------------------------------------------
    def labels(self) -> dict:
        return self.store.labels()

    def set_label(self, path: str, text: str) -> dict:
        path = self._path(path)
        if not isinstance(text, str) or len(text.strip()) > MAX_LABEL:
            raise MemoryChangeError(f"a note about a shelf can be at most {MAX_LABEL} characters")
        text = text.strip()
        with self.lock:
            if path not in MemoryTree(self.vault().all()).nodes:
                raise MemoryChangeError("that shelf does not exist")
            self.store.set_label(path, text)
            self._overview = None
        return {"path": path, "label": text}

    # -- reading ---------------------------------------------------------------------------------
    def vault(self) -> Vault:
        """The memory as it is now. Never re-read from disk: this service is the only writer, so the copy in memory is the truth."""
        return self._vault

    def _helper_names(self) -> dict:
        names = {}
        if self.registry is not None:
            for r in self.registry.records.values():
                names[r.digest] = r.id.replace("-", " ").title()
        return names

    def _usage(self, unit_of: dict) -> dict[str, dict]:
        """How many answers each note helped write. A long note counts once per answer, however many passages were used."""
        use: dict[str, dict] = {}
        if self.threads is None:
            return use
        with self.threads.lock:
            for t in self.threads.threads.values():
                for m in t.messages:
                    for unit in {unit_of.get(fid, fid) for fid in m.files}:
                        u = use.setdefault(unit, {"answers": 0, "last_chat": "", "last_at": 0.0})
                        u["answers"] += 1
                        if m.at >= u["last_at"]:
                            u["last_at"], u["last_chat"] = m.at, t.title
        return use

    def _item(self, parts: list[Record], use: dict, names: dict) -> dict:
        r = parts[0]
        origin = r.origin or {}
        text = join_document([p.text for p in parts]) if r.doc else r.text
        return {
            "id": r.unit, "type": r.type, "sensitivity": "low" if r.sensitivity == "low" else "high", "text": text,
            "long": bool(r.doc), "title": r.title if r.doc else "", "parts": len(parts) if r.doc else 1, "chars": len(text),
            "shelf": r.shelf, "shelf_name": pretty(r.shelf), "created": r.created, "updated": max(p.updated for p in parts),
            "edited": any(p.edited for p in parts), "trust": r.trust_tier,
            "source": "helper" if origin.get("pack_digest") else "you",
            "helper": names.get(origin.get("pack_digest"), "a helper") if origin.get("pack_digest") else None,
            "from_run": origin.get("run_id"),
            "used": use.get(r.unit, {"answers": 0, "last_chat": "", "last_at": 0.0}),
        }

    def list(self, *, shelf: str | None = None, ids=None, q: str = "", offset: int = 0, limit: int = PAGE) -> list[dict]:
        """Notes for the manager screen, one page at a time. A long note is one item. `shelf` includes everything below it."""
        v = self.vault()
        names = self._helper_names()
        recs = v.all()
        use = self._usage({r.id: r.unit for r in recs})
        if ids is not None:
            want = set(ids)
            recs = [r for r in recs if r.id in want or r.doc in want]
        if shelf:
            recs = [r for r in recs if under(r.shelf, shelf)]
        groups: dict[str, list[Record]] = {}
        for r in recs:
            groups.setdefault(r.unit, []).append(r)
        if q.strip():
            qt = tokens(q)
            groups = {u: ps for u, ps in groups.items() if any(qt & tokens(p.text + " " + p.shelf + " " + p.title) for p in ps)}
        units = sorted(groups.values(), key=lambda ps: (-max((p.updated or p.created) for p in ps), ps[0].unit))
        start = max(0, offset)
        return [self._item(sorted(ps, key=lambda p: p.part), use, names) for ps in units[start:start + max(1, min(limit, 200))]]

    def overview(self) -> dict:
        """The whole tree without any file text: what the manager and the chat panels draw."""
        vault = self.vault()
        if self._overview is not None:
            return self._overview
        recs = vault.all()
        tree = MemoryTree(recs, self.labels())
        secret: dict[str, int] = {}
        seen_secret: set = set()
        for r in recs:
            if r.sensitivity != "low" and r.unit not in seen_secret:
                seen_secret.add(r.unit)
                p = r.shelf
                while True:
                    secret[p] = secret.get(p, 0) + 1
                    if "/" not in p:
                        break
                    p = p.rsplit("/", 1)[0]
        shelves = []
        recs_by_id = {r.id: r for r in recs}

        def walk(path: str, depth: int):
            for o in tree.outline(path):
                shelves.append({**o, "depth": depth, "secret": secret.get(o["path"], 0), "parent": path,
                                "own": len({recs_by_id[i].unit for i in tree.nodes[o["path"]].own})})
                walk(o["path"], depth + 1)
        walk("", 0)
        units = {r.unit for r in recs}
        stamps = [r.created for r in recs if r.created]
        out = {"total": len(units), "secret": len(seen_secret), "long": len({r.doc for r in recs if r.doc}),
               "contacts": len({r.unit for r in recs if r.type == "contact"}),
               "oldest": min(stamps) if stamps else 0, "newest": max(max((r.updated or r.created) for r in recs), 0) if recs else 0,
               "shelves": shelves}
        self._overview = out
        return out

    # -- changing --------------------------------------------------------------------------------
    def _mutate(self, fn):
        with self.lock:
            work = self._vault.clone()  # a change that fails halfway leaves the real memory untouched
            out = fn(work)
            self.store.write_changes(self._vault._records, work._records)
            self._vault, self._overview = work, None
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

    def _fresh_doc(self, v: Vault, taken: set) -> str:
        n = int(v.next_doc()[3:])
        while f"doc{n}" in taken:
            n += 1
        return f"doc{n}"

    def _make(self, v: Vault, type: str, text, sensitivity: str, path: str, title: str, now: float, taken: set, *, doc: str = "",
              created: float | None = None, edited: bool = False, origin=None, trust: int = 3) -> str:
        """Save one note. A short one is one record; a long one is kept whole and stored as passages. Returns the note's id."""
        if not isinstance(text, str):
            raise MemoryChangeError("each note must be text")
        text = text.strip()
        if len(text) > MAX_DOC:
            raise MemoryChangeError(f"a note can be up to {MAX_DOC:,} characters; this one is {len(text):,}")
        base = dict(sensitivity=sensitivity, path=path, created=now if created is None else created, updated=now, edited=edited, origin=origin, trust_tier=trust)
        try:
            if len(text) <= SHORT and not doc:
                rid = v.next_id("m")
                while rid in taken:
                    rid = "m" + str(int(rid[1:]) + 1)
                v.add(Record(rid, type, text=text, **base))
                return rid
            parts = split_document(text)
            if not parts:
                raise MemoryChangeError("a record needs some text")
            if len(parts) > MAX_PARTS:
                raise MemoryChangeError("that note is too long to keep as one piece; split it into two notes")
            doc = doc or self._fresh_doc(v, taken)
            name = (title or "").strip()[:120] or guess_title(text)
            for n, chunk in enumerate(parts, 1):
                v.add(Record(f"{doc}.{n}", type, text=chunk, doc=doc, title=name, part=n, **base))
            return doc
        except ValueError as e:
            raise MemoryChangeError(str(e)) from e

    def add(self, type: str, text: str, sensitivity: str, path: str = "", title: str = "") -> dict:
        now = self.clock()
        sensitivity, path = self._level(sensitivity), self._path(path)
        taken = self._referenced()
        twins = self.similar(text) if isinstance(text, str) else []  # looked for before saving, so the new note does not match itself
        return {"id": self._mutate(lambda v: self._make(v, type, text, sensitivity, path, title, now, taken)), "similar": twins}

    def add_many(self, items: list, sensitivity: str, type: str, path: str = "") -> dict:
        """Save several notes at once (for example from an imported file), all or nothing."""
        if not isinstance(items, list) or not items or len(items) > 50:
            raise MemoryChangeError("add between 1 and 50 notes at a time")
        now = self.clock()
        sensitivity, path = self._level(sensitivity), self._path(path)
        taken = self._referenced()

        def go(v: Vault):
            ids = []
            for item in items:
                title = ""
                if isinstance(item, dict):  # {"title": ..., "text": ...}: a long note brought in whole
                    title, item = str(item.get("title", "")), item.get("text")
                ids.append(self._make(v, type, item, sensitivity, path, title, now, taken))
                taken.add(ids[-1])
            return ids
        return {"ids": self._mutate(go)}

    def update(self, record_id: str, *, text=None, sensitivity=None, type=None, path=None, title=None) -> dict:
        now = self.clock()
        for name, val in (("text", text), ("sensitivity", sensitivity), ("type", type), ("shelf", path), ("title", title)):
            if val is not None and not isinstance(val, str):
                raise MemoryChangeError(f"{name} must be text")
        sensitivity = None if sensitivity is None else self._level(sensitivity)
        path = None if path is None else self._path(path)
        taken = self._referenced()

        def go(v: Vault):
            unit = v.unit_of(record_id)
            parts = v.parts(unit) if unit and unit.startswith("doc") and v.parts(unit) else ([v.get(unit)] if unit and v.get(unit) else [])
            if not parts:
                raise MemoryChangeError("that file is no longer in your memory")
            first = parts[0]
            if text is not None:
                old = join_document([p.text for p in parts]) if first.doc else first.text
                if old != text.strip():
                    self._push_history(first.unit, old, first.title, now)
            try:
                if text is not None and (first.doc or len(text.strip()) > SHORT):
                    for p in parts:  # the note is written again from the new text, keeping who wrote it and when
                        v.remove(p.id)
                    new = self._make(v, type or first.type, text, sensitivity or first.sensitivity, first.path if path is None else path,
                               (title if title is not None else first.title), now, taken - {first.doc, first.id}, doc=first.doc,
                               created=first.created, edited=True, origin=first.origin, trust=3)
                    self._move_history(first.unit, new)
                    return new, True
                for p in parts:
                    v.update(p.id, now=now, text=None if text is None else text.strip(), sensitivity=sensitivity, type=type, path=path)
                    if title is not None and p.doc:
                        v._records[p.id] = replace(v._records[p.id], title=title.strip()[:120])
                return first.unit, text is not None or any(p.edited for p in parts)
            except ValueError as e:
                raise MemoryChangeError(str(e)) from e
        unit, edited = self._mutate(go)
        return {"id": unit, "edited": edited}

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
            self.store.replace_labels({(target + k[len(source):] if under(k, source) else k): v for k, v in labels.items()})
            if self.threads is not None:
                with self.threads.lock:
                    for t in self.threads.threads.values():
                        t.lens.shelves = sorted({(target + x[len(source):]) if under(x, source) else x for x in t.lens.shelves})
                    self.threads.save()
        return {"moved": n}

    def _forget_in_chats(self, gone: set) -> None:
        if self.threads is not None:  # it can no longer be shared, so every chat forgets it was ever picked
            with self.threads.lock:
                for t in self.threads.threads.values():
                    t.lens.include = [i for i in t.lens.include if i not in gone]
                    t.lens.exclude = [i for i in t.lens.exclude if i not in gone]
                self.threads.save()

    def delete(self, record_id: str) -> dict:
        """Delete a note. It goes to the trash for 30 days first, so a slip can be undone."""
        gone: set = set()
        now = self.clock()

        def go(v: Vault):
            unit = v.unit_of(record_id)
            members = v.parts(unit) if unit and v.parts(unit) else ([v.get(unit)] if unit and v.get(unit) else [])
            if not members:
                raise MemoryChangeError("that file is no longer in your memory")
            self._to_trash(members, now)
            for p in members:
                v.remove(p.id)
                gone.add(p.id)
            gone.add(unit)
        self._mutate(go)
        self._forget_in_chats(gone)
        return {"deleted": record_id, "undo": True}

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
