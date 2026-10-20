"""Run journal: append-only JSON lines, each entry hash-chained to the one before.

The engine's state is a pure function of this journal, so a crash can be resumed by replay
and any edit to a past entry is detectable. A torn last line (crash mid-write) is dropped
with a recovery marker; a hash mismatch anywhere before the tail is tampering.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

GENESIS = "0" * 64


class JournalTampered(Exception):
    pass


def _hash(prev: str, seq: int, kind: str, data: dict) -> str:
    body = json.dumps({"prev": prev, "seq": seq, "kind": kind, "data": data}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


class Journal:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.entries: list[dict] = []
        self.recovered_torn_tail = False
        if self.path and self.path.exists():
            self._load()

    @property
    def head(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def append(self, kind: str, data: dict | None = None) -> dict:
        data = data or {}
        entry = {"seq": len(self.entries), "kind": kind, "data": data, "prev": self.head}
        entry["hash"] = _hash(entry["prev"], entry["seq"], kind, data)
        self.entries.append(entry)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
        return entry

    def verify(self) -> None:
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e["seq"] != i or e["prev"] != prev or e["hash"] != _hash(prev, i, e["kind"], e["data"]):
                raise JournalTampered(f"chain broken at entry {i}")
            prev = e["hash"]

    def _load(self) -> None:
        lines = self.path.read_text(encoding="utf-8").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        for i, line in enumerate(lines):
            try:
                self.entries.append(json.loads(line))
            except json.JSONDecodeError:
                if i == len(lines) - 1:  # torn tail from a crash: drop it, remember we did
                    self.recovered_torn_tail = True
                    break
                raise JournalTampered(f"unreadable entry {i} before the tail")
        self.verify()
        if self.recovered_torn_tail:
            good = "".join(json.dumps(e, sort_keys=True) + "\n" for e in self.entries)
            self.path.write_text(good, encoding="utf-8")
            self.append("recovered", {"reason": "torn tail dropped"})
