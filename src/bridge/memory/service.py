"""Everything a person can do with their own memory: look at it, add to it, correct it, delete it.

All changes go through one lock and an atomic file write, so two requests at once cannot overwrite each other.
Each item reports where it came from (written by you, or suggested by a helper and accepted by you) and
how many answers it has been used in, so nothing in memory is a mystery.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from .quarantine import Quarantine, QuarantineError
from .vault import Record, Vault


class MemoryChangeError(ValueError):
    """The change cannot be made; the message says why in plain words."""


class MemoryService:
    def __init__(self, vault_file: Path, quarantine: Quarantine, *, threads=None, registry=None,
                 clock: Callable[[], float], lock: threading.RLock | None = None):
        self.file, self.quarantine, self.threads, self.registry, self.clock = Path(vault_file), quarantine, threads, registry, clock
        self.lock = lock or threading.RLock()

    # -- reading ---------------------------------------------------------------------------------
    def vault(self) -> Vault:
        with self.lock:
            return Vault.load(self.file)

    def _helper_name(self, digest: str) -> str:
        if self.registry is not None:
            for r in self.registry.records.values():
                if r.digest == digest:
                    return r.id.replace("-", " ").title()
        return "a helper"

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

    def list(self) -> list[dict]:
        use = self._usage()
        out = []
        for r in self.vault().all():
            origin = r.origin or {}
            helper = self._helper_name(origin["pack_digest"]) if origin.get("pack_digest") else None
            out.append({
                "id": r.id, "type": r.type, "sensitivity": r.sensitivity, "text": r.text, "created": r.created, "updated": r.updated,
                "edited": r.edited, "trust": r.trust_tier,
                "source": "helper" if helper else "you", "helper": helper,
                "from_run": origin.get("run_id"),
                "used": use.get(r.id, {"answers": 0, "last_chat": "", "last_at": 0.0}),
            })
        return out

    # -- changing --------------------------------------------------------------------------------
    def _mutate(self, fn):
        with self.lock:
            v = Vault.load(self.file)
            out = fn(v)
            v.save(self.file)
            return out

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

    def add(self, type: str, text: str, sensitivity: str) -> dict:
        now = self.clock()

        def go(v: Vault):
            rid = v.next_id("m")
            while rid in self._referenced():
                rid = "m" + str(int(rid[1:]) + 1)
            try:
                rec = Record(rid, type, sensitivity, (text or "").strip(), created=now)
            except ValueError as e:
                raise MemoryChangeError(str(e)) from e
            v.add(rec)
            return rec
        rec = self._mutate(go)
        return {"id": rec.id}

    def add_many(self, items: list, sensitivity: str, type: str) -> dict:
        """Save several notes at once (for example from an imported file), all or nothing."""
        if not isinstance(items, list) or not items or len(items) > 50:
            raise MemoryChangeError("add between 1 and 50 notes at a time")
        now = self.clock()

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
                    v.add(Record(rid, type, sensitivity, text.strip(), created=now))
                except ValueError as e:
                    raise MemoryChangeError(str(e)) from e
                ids.append(rid)
            return ids
        return {"ids": self._mutate(go)}

    def update(self, record_id: str, *, text=None, sensitivity=None, type=None) -> dict:
        now = self.clock()

        for name, val in (("text", text), ("sensitivity", sensitivity), ("type", type)):
            if val is not None and not isinstance(val, str):
                raise MemoryChangeError(f"{name} must be text")

        def go(v: Vault):
            if v.get(record_id) is None:
                raise MemoryChangeError("that file is no longer in your memory")
            try:
                return v.update(record_id, now=now, text=None if text is None else text.strip(), sensitivity=sensitivity, type=type)
            except ValueError as e:
                raise MemoryChangeError(str(e)) from e
        rec = self._mutate(go)
        return {"id": rec.id, "edited": rec.edited}

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
