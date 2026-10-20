"""Minimal user vault: typed records with a sensitivity level.

This is the in-memory model the broker works against. The durable vault (journal, CAS,
quarantine tier, shred) is a later feature; the broker only needs this read interface.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

SENSITIVITY = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class Record:
    id: str
    type: str  # e.g. "note", "contact", "finance", "code"
    sensitivity: str  # "low" | "medium" | "high"
    text: str

    def __post_init__(self):
        if self.sensitivity not in SENSITIVITY:
            raise ValueError(f"unknown sensitivity {self.sensitivity!r}")

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

    def all(self) -> list[Record]:
        return list(self._records.values())
