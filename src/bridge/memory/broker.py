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

from .vault import SENSITIVITY, Record, Vault


class Verdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"  # blocked, counted as a strike
    KILL = "kill"  # deterministic evidence of theft: stop the run now


@dataclass(frozen=True)
class Lens:
    types: frozenset[str]
    max_sensitivity: str = "medium"
    max_records: int = 50
    max_reads: int = 30  # total records returned over the whole run
    max_results_per_query: int = 5

    def __post_init__(self):
        if self.max_sensitivity not in SENSITIVITY:
            raise ValueError(f"unknown sensitivity {self.max_sensitivity!r}")

    def allows(self, r: Record) -> bool:
        return r.type in self.types and SENSITIVITY[r.sensitivity] <= SENSITIVITY[self.max_sensitivity]


@dataclass(frozen=True)
class Event:
    kind: str  # OFF_LENS_QUERY | OFF_LENS_READ | CANARY_HIT | READ_BUDGET | UNKNOWN_ID
    verdict: Verdict
    detail: str


@dataclass
class Result:
    verdict: Verdict
    records: list[dict] = field(default_factory=list)


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


class MemoryBroker:
    def __init__(self, vault: Vault, lens: Lens, *, run_seed: str):
        self._lens = lens
        self._staged: dict[str, Record] = {}
        for r in vault.all():
            if lens.allows(r) and len(self._staged) < lens.max_records:
                self._staged[r.id] = r
        self.manifest = {rid: r.content_hash for rid, r in sorted(self._staged.items())}
        self._seed = run_seed
        self._decoys: dict[str, Record] = {}
        self._served = 0
        self._killed = False
        self.events: list[Event] = []
        self.reads: list[str] = []  # accounting: every record id handed to the pack

    # -- what the user sees on the approval card -------------------------------------------
    def describe(self) -> dict:
        by_type: dict[str, int] = {}
        for r in self._staged.values():
            by_type[r.type] = by_type.get(r.type, 0) + 1
        return {"count": len(self._staged), "by_type": by_type, "reads_left": self._lens.max_reads - self._served}

    # -- what the pack can call ------------------------------------------------------------
    def search(self, query: str, *, type: str | None = None) -> Result:
        if self._killed:
            return Result(Verdict.KILL)
        if type is not None and type not in self._lens.types:
            return self._bait(type)
        q = _tokens(query)
        pool = [r for r in self._staged.values() if type is None or r.type == type]
        scored = sorted(((len(q & _tokens(r.text + " " + r.type)), r.id, r) for r in pool), key=lambda t: (-t[0], t[1]))
        hits = [r for score, _, r in scored if score > 0][: self._lens.max_results_per_query]
        return self._serve(hits)

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
            out.append({"id": r.id, "type": r.type, "text": r.text})
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
    def killed(self) -> bool:
        return self._killed
