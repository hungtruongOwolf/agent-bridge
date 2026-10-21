"""User vault: typed records with a sensitivity level, an origin and a trust tier.

Trust tiers: 3 = written or edited by the user, 1 = accepted from a foreign pack ("endorsed foreign").
Origin is immutable once set and says where a foreign record came from (pack digest, run id), so a
run's effects can be found and reverted later without touching records the user wrote.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path

SENSITIVITY = {"low": 0, "medium": 1, "high": 2}
TYPE_RE = re.compile(r"^[a-z][a-z0-9-]{1,19}$")
MAX_TEXT = 2000


@dataclass(frozen=True)
class Record:
    id: str
    type: str  # e.g. "note", "contact", "finance", "code"
    sensitivity: str  # "low" | "medium" | "high"
    text: str
    trust_tier: int = 3
    origin: dict | None = None  # {"pack_digest": ..., "run_id": ..., "proposal_id": ...} for foreign records
    created: float = 0.0  # when the record entered the vault (epoch seconds; 0 = unknown, e.g. seed data)
    updated: float = 0.0
    edited: bool = False  # a person changed the text after it was saved

    def __post_init__(self):
        if not TYPE_RE.match(self.type or ""):
            raise ValueError("type must be 2 to 20 lowercase letters, digits or dashes")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("a record needs some text")
        if len(self.text) > MAX_TEXT:
            raise ValueError(f"a record can hold at most {MAX_TEXT} characters")
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

    def update(self, record_id: str, *, now: float, text: str | None = None, sensitivity: str | None = None,
               type: str | None = None) -> Record:
        """Change a record. A foreign record that a person edits becomes theirs (tier 3) but keeps its origin."""
        old = self._records.get(record_id)
        if old is None:
            raise KeyError(record_id)
        changes = {k: v for k, v in (("text", text), ("sensitivity", sensitivity), ("type", type)) if v is not None}
        if not changes:
            return old
        new = replace(old, **changes, updated=now, edited=old.edited or "text" in changes, trust_tier=3 if "text" in changes else old.trust_tier)
        self._records[record_id] = new
        return new

    def next_id(self, prefix: str = "m") -> str:
        n = 1 + max([int(m.group(1)) for r in self._records for m in [re.fullmatch(prefix + r"(\d+)", r)] if m] or [0])
        return f"{prefix}{n}"

    def all(self) -> list[Record]:
        return list(self._records.values())

    def save(self, path: Path) -> None:
        path = Path(path)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(r) for r in self._records.values()], indent=2), encoding="utf-8")
        os.replace(tmp, path)  # readers never see a half-written file

    @classmethod
    def load(cls, path: Path) -> "Vault":
        return cls([Record(**raw) for raw in json.loads(Path(path).read_text(encoding="utf-8"))])
