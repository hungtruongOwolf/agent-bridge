"""Quarantine tier Q: where anything a foreign pack wants remembered waits for the user.

A pack never writes memory. After a run it may return a few typed proposals. They are validated
against a platform schema (small, typed, no links), stored here with their origin, and shown to the
user. Nothing in Q is ever served to a pack. Only the user can accept a proposal; an accepted item
enters the vault at trust tier 1 (endorsed foreign) with sensitivity "low" and an immutable origin.
Reverting a run removes its quarantined items and every vault record whose origin is that run, and
leaves the user's own records alone.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

from .vault import Record, Vault

ALLOWED_TYPES = ("note", "fact", "preference")
MAX_PROPOSALS = 3
MAX_TEXT = 200
_LINK = re.compile(r"(https?://|www\.|\]\(|!\[|data:|<[a-z/])", re.I)
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class QuarantineError(Exception):
    pass


@dataclass
class Proposal:
    id: str
    type: str
    text: str
    run_id: str
    pack_digest: str
    created: float
    status: str = "pending"  # pending | accepted | rejected | expired | reverted
    record_id: str | None = None


def validate(raw) -> tuple[list[dict], list[str]]:
    """Return (valid proposals, problems). Invalid items are dropped, never repaired."""
    if raw in (None, []):
        return [], []
    if not isinstance(raw, list):
        return [], ["proposals must be a list"]
    good, problems = [], []
    if len(raw) > MAX_PROPOSALS:
        problems.append(f"more than {MAX_PROPOSALS} proposals; extra ones dropped")
    for i, item in enumerate(raw[:MAX_PROPOSALS]):
        if not (isinstance(item, dict) and set(item) == {"type", "text"}):
            problems.append(f"proposal {i}: must have exactly type and text")
        elif item["type"] not in ALLOWED_TYPES:
            problems.append(f"proposal {i}: type must be one of {', '.join(ALLOWED_TYPES)}")
        elif not isinstance(item["text"], str) or not (1 <= len(item["text"].strip()) <= MAX_TEXT):
            problems.append(f"proposal {i}: text must be 1-{MAX_TEXT} characters")
        elif _LINK.search(item["text"]) or _CTRL.search(item["text"]):
            problems.append(f"proposal {i}: links, markup and control characters are not allowed")
        else:
            good.append({"type": item["type"], "text": item["text"].strip()})
    return good, problems


@dataclass
class Quarantine:
    ttl_s: float = 14 * 24 * 3600
    clock: Callable[[], float] = time.time
    max_pending: int = 20
    items: dict[str, Proposal] = field(default_factory=dict)
    _n: int = 0
    docs: object = None  # a collection in the memory database: suggestions waiting for an answer survive a restart

    def attach(self, docs) -> None:
        """Keep suggestions in the database: load what is there and store every change from now on."""
        self.docs = docs
        for _, raw in docs.items():
            p = Proposal(**raw)
            self.items[p.id] = p
            self._n = max(self._n, int(p.id[1:]) if p.id[1:].isdigit() else 0)

    def _persist(self, *ps: Proposal) -> None:
        if self.docs is not None and ps:
            self.docs.write({p.id: asdict(p) for p in ps})

    def add(self, run_id: str, pack_digest: str, raw) -> tuple[list[Proposal], list[str]]:
        good, problems = validate(raw)
        added = []
        for g in good:
            if len(self.pending()) >= self.max_pending:
                problems.append("quarantine is full; proposal dropped")
                break
            self._n += 1
            p = Proposal(f"p{self._n}", g["type"], g["text"], run_id, pack_digest, self.clock())
            self.items[p.id] = p
            added.append(p)
        self._persist(*added)
        return added, problems

    def pending(self) -> list[Proposal]:
        self._expire()
        return [p for p in self.items.values() if p.status == "pending"]

    def _expire(self) -> None:
        now = self.clock()
        gone = [p for p in self.items.values() if p.status == "pending" and now - p.created > self.ttl_s]
        for p in gone:
            p.status = "expired"
        self._persist(*gone)

    def accept(self, proposal_id: str, vault: Vault) -> Record:
        p = self._get_pending(proposal_id)
        rec = Record(
            id=f"q_{p.id}_{p.run_id[-6:]}", type=p.type, sensitivity="low", text=p.text, trust_tier=1, path="from helpers",
            origin={"pack_digest": p.pack_digest, "run_id": p.run_id, "proposal_id": p.id}, created=self.clock(),
        )
        vault.add(rec)
        p.status, p.record_id = "accepted", rec.id
        self._persist(p)
        return rec

    def reject(self, proposal_id: str) -> None:
        p = self._get_pending(proposal_id)
        p.status = "rejected"
        self._persist(p)

    def revert_run(self, run_id: str, vault: Vault) -> dict:
        """Undo one run: drop its pending items and remove vault records that came from it."""
        dropped = removed = kept = 0
        touched = []
        for p in self.items.values():
            if p.run_id == run_id and p.status in ("pending", "accepted"):
                rec = vault.get(p.record_id) if p.record_id else None
                if p.status == "accepted" and rec is not None and rec.edited:
                    kept += 1  # a person rewrote it, so it is theirs now: undoing the run must not delete their work
                elif p.status == "accepted" and p.record_id and vault.remove(p.record_id):
                    removed += 1
                elif p.status == "pending":
                    dropped += 1
                p.status = "reverted"
                touched.append(p)
        self._persist(*touched)
        return {"dropped_pending": dropped, "removed_from_vault": removed, "kept_because_edited": kept}

    def _get_pending(self, proposal_id: str) -> Proposal:
        self._expire()
        p = self.items.get(proposal_id)
        if p is None or p.status != "pending":
            raise QuarantineError("no such pending proposal")
        return p
