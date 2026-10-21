"""Memory Broker: the only way a pack reads user memory.

The user approves a Lens (which record types, up to which sensitivity, how many records,
how many reads). At run start the broker stages a CLOSED set of records matching the lens.
The pack can only search and read inside that set; there is no "list everything" call.

Everything outside the lens is either denied (a real record) or a decoy:
  - asking about a type outside the lens returns decoy records (bait);
  - reading a decoy id is a canary hit and the run must be killed.
Decoys are never mixed into in-lens results, so an honest pack that stays in its lens
never sees one.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum

from .tree import MemoryTree
from .vault import SENSITIVITY, Record, Vault, under
from .words import tokens


class Verdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"  # blocked, counted as a strike
    KILL = "kill"  # deterministic evidence of theft: stop the run now


@dataclass(frozen=True)
class Lens:
    types: frozenset[str]  # whole drawers by kind of file (used by the command line and the tests)
    max_sensitivity: str = "low"  # only everyday files are ever shareable; there is no dial to raise it
    max_records: int = 50
    max_reads: int = 30  # total records returned over the whole run
    max_results_per_query: int = 5
    include: frozenset[str] = frozenset()  # record ids shared even though their shelf or type would not allow it (never a secret one)
    exclude: frozenset[str] = frozenset()  # record ids never shared, whatever else says yes
    shelves: frozenset[str] = frozenset()  # whole shelves of the memory tree that are opened, with everything below them

    def __post_init__(self):
        if self.max_sensitivity not in SENSITIVITY:
            raise ValueError(f"unknown sensitivity {self.max_sensitivity!r}")

    def allows(self, r: Record) -> bool:
        if r.id in self.exclude or SENSITIVITY[r.sensitivity] > SENSITIVITY[self.max_sensitivity]:
            return False  # a secret file stays home even if someone ticked it
        if r.id in self.include:
            return True
        return r.type in self.types or any(under(r.shelf, s) for s in self.shelves)


@dataclass(frozen=True)
class Event:
    kind: str  # OFF_LENS_QUERY | OFF_LENS_READ | CANARY_HIT | READ_BUDGET | UNKNOWN_ID
    verdict: Verdict
    detail: str


@dataclass
class Result:
    verdict: Verdict
    records: list[dict] = field(default_factory=list)


_tokens = tokens  # kept for older callers; the shared version lives in words.py


class MemoryBroker:
    def __init__(self, vault: Vault, lens: Lens, *, run_seed: str):
        self._lens = lens
        self._staged: dict[str, Record] = {}
        for r in vault.all():
            if lens.allows(r) and len(self._staged) < lens.max_records:
                self._staged[r.id] = r
        self._tree = MemoryTree(self._staged.values())  # the helper's tree holds only what it may see
        self.manifest = {rid: r.content_hash for rid, r in sorted(self._staged.items())}
        self._seed = run_seed
        self._decoys: dict[str, Record] = {}
        self._served = 0
        self._killed = False
        self.events: list[Event] = []
        self.reads: list[str] = []  # accounting: every record id handed to the pack
        self.walks: list[dict] = []  # every search: the shelves opened on the way down and the files it ended on

    # -- what the user sees on the approval card -------------------------------------------
    def describe(self) -> dict:
        by_type: dict[str, int] = {}
        for r in self._staged.values():
            by_type[r.type] = by_type.get(r.type, 0) + 1
        by_shelf: dict[str, int] = {}
        for r in self._staged.values():
            by_shelf[r.shelf] = by_shelf.get(r.shelf, 0) + 1
        return {"count": len(self._staged), "by_type": by_type, "by_shelf": by_shelf, "reads_left": self._lens.max_reads - self._served}

    def shelf_of(self, record_id: str) -> str | None:
        r = self._staged.get(record_id)
        return r.shelf if r else None

    # -- what the pack can call ------------------------------------------------------------
    def search(self, query: str, *, type: str | None = None, fallback: bool = False) -> Result:
        """Find shared records that match the words of `query`.

        With `fallback`, a question that matches nothing (a vague "anything new?") gets the shared records
        themselves, still capped per query and still only what the lens allows."""
        if self._killed:
            return Result(Verdict.KILL)
        if type is not None and type not in self._lens.types and not any(r.type == type for r in self._staged.values()):
            return self._bait(type)
        pool = self._tree if type is None else MemoryTree(r for r in self._staged.values() if r.type == type)
        hits, opened = pool.route(query, self._lens.max_results_per_query)
        if not hits and fallback:
            hits = pool.newest(self._lens.max_results_per_query)
        res = self._serve(hits)
        self.walks.append({"opened": opened, "files": [x["id"] for x in res.records]})
        return res

    def read(self, record_id: str) -> Result:
        if self._killed:
            return Result(Verdict.KILL)
        if record_id in self._decoys:
            return self._kill("CANARY_HIT", f"read of decoy record {record_id}")
        if record_id in self._staged:
            return self._serve([self._staged[record_id]])
        # not in the closed set and not a decoy: a guessed id, or a real record outside the lens
        self.events.append(Event("UNKNOWN_ID", Verdict.DENY, f"read of {record_id!r} outside the staged set"))
        return Result(Verdict.DENY)

    # -- internals -------------------------------------------------------------------------
    def _serve(self, records: list[Record]) -> Result:
        out = []
        for r in records:
            if self._served >= self._lens.max_reads:
                self.events.append(Event("READ_BUDGET", Verdict.DENY, "read budget exhausted"))
                return Result(Verdict.DENY, out)
            self._served += 1
            self.reads.append(r.id)
            out.append({"id": r.id, "type": r.type, "text": r.text,
                        "trust": "user" if r.trust_tier == 3 else "endorsed-foreign"})
        return Result(Verdict.ALLOW, out)

    def _bait(self, type: str) -> Result:
        self.events.append(Event("OFF_LENS_QUERY", Verdict.DENY, f"query for type {type!r} outside the lens"))
        decoy = self._decoys.setdefault(*self._make_decoy(type))
        return Result(Verdict.DENY, [{"id": decoy.id, "type": type, "text": decoy.text}])

    def _make_decoy(self, type: str) -> tuple[str, Record]:
        tag = hashlib.sha256(f"{self._seed}:{type}".encode()).hexdigest()[:12]
        rid = f"rec_{tag}"
        return rid, Record(rid, type, "high", f"CANARY-{tag} confidential {type} record")

    @property
    def canary_values(self) -> list[str]:
        """Strings that must never appear in anything leaving the run (used by the Result Guard)."""
        return [d.text for d in self._decoys.values()] + [d.id for d in self._decoys.values()]

    def _kill(self, kind: str, detail: str) -> Result:
        self._killed = True
        self.events.append(Event(kind, Verdict.KILL, detail))
        return Result(Verdict.KILL)

    @property
    def lens_texts(self) -> list[str]:
        """Text of every staged record (the Result Guard checks outputs for verbatim copies)."""
        return [r.text for r in self._staged.values()]

    @property
    def killed(self) -> bool:
        return self._killed
