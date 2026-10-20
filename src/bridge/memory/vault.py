"""User vault: typed records with a sensitivity level, an origin and a trust tier.

Trust tiers: 3 = written or edited by the user, 1 = accepted from a foreign pack ("endorsed foreign").
Origin is immutable once set and says where a foreign record came from (pack digest, run id), so a
run's effects can be found and reverted later without touching records the user wrote.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

SENSITIVITY = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class Record:
    id: str
    type: str  # e.g. "note", "contact", "finance", "code"
    sensitivity: str  # "low" | "medium" | "high"
    text: str
    trust_tier: int = 3
    origin: dict | None = None  # {"pack_digest": ..., "run_id": ..., "proposal_id": ...} for foreign records

    def __post_init__(self):
        if self.sensitivity not in SENSITIVITY:
            raise ValueError(f"unknown sensitivity {self.sensitivity!r}")
        if self.trust_tier not in (0, 1, 2, 3):
            raise ValueError("trust_tier must be 0..3")
        if self.trust_tier < 3 and not self.origin:
            raise ValueError("a record below trust tier 3 must say where it came from")

    @property
    def content_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.text.encode()).hexdigest()


class Vault:
    def __init__(self, records: list[Record] | None = None):
        self._records: dict[str, Record] = {}
        for r in records or []:
            self.add(r)

    def add(self, record: Record) -> None:
        if record.id in self._records:
            raise ValueError(f"duplicate record id {record.id!r}")
        self._records[record.id] = record

    def get(self, record_id: str) -> Record | None:
        return self._records.get(record_id)

    def remove(self, record_id: str) -> Record | None:
        return self._records.pop(record_id, None)

    def all(self) -> list[Record]:
        return list(self._records.values())

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps([asdict(r) for r in self._records.values()], indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Vault":
        return cls([Record(**raw) for raw in json.loads(Path(path).read_text(encoding="utf-8"))])
