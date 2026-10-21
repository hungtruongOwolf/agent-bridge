"""Where the memory lives: one row per note, so editing one note writes one row, however big the memory is.
Also the things that sit beside the notes: the trash, earlier versions, and the short notes about shelves."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..memory.vault import Record, Vault
from .db import Database


class MemoryStore:
    def __init__(self, db: Database):
        self.db = db
        self.notes, self._trash = db.collection("notes"), db.collection("trash")
        self._history, self._labels = db.collection("history"), db.collection("labels")

    # -- the notes -------------------------------------------------------------------------------
    def is_empty(self) -> bool:
        return self.notes.count() == 0 and self.db.meta("seeded") != "1"

    def mark_seeded(self) -> None:
        self.db.set_meta("seeded", "1")  # an emptied memory stays empty: it is not filled again from the starter file

    def load_vault(self) -> Vault:
        return Vault([Record(**body) for _, body in self.notes.items()])

    def write_changes(self, before: dict, after: dict) -> int:
        """Store exactly what differs between two states of the vault (records are immutable, so identity is the test). Returns rows written."""
        puts = {i: asdict(r) for i, r in after.items() if before.get(i) is not r}
        gone = [i for i in before if i not in after]
        if puts or gone:
            self.notes.write(puts, gone, {i: r.created for i, r in after.items() if i in puts})
        return len(puts) + len(gone)

    # -- trash -----------------------------------------------------------------------------------
    def trash_entries(self) -> list[dict]:
        return [b for _, b in self._trash.items()]

    def trash_add(self, entry: dict, keep: int) -> None:
        self._trash.put(f"{entry['unit']}@{entry['deleted_at']}", entry, entry["deleted_at"])
        extra = self._trash.items()[:-keep] if keep else []
        self._trash.delete(*[i for i, _ in extra])

    def trash_remove(self, entry: dict) -> None:
        self._trash.delete(f"{entry['unit']}@{entry['deleted_at']}")

    def trash_purge(self, cutoff: float) -> None:
        self._trash.delete(*[i for i, b in self._trash.items() if b.get("deleted_at", 0) < cutoff])

    def trash_clear(self) -> int:
        n = self._trash.count()
        self._trash.clear()
        return n

    # -- earlier versions ------------------------------------------------------------------------
    def versions(self, unit: str) -> list[dict]:
        return self._history.get(unit, [])

    def push_version(self, unit: str, version: dict, keep: int) -> None:
        versions = self.versions(unit)
        if versions and versions[-1]["text"] == version["text"]:
            return
        self._history.put(unit, (versions + [version])[-keep:])

    def move_versions(self, old: str, new: str) -> None:
        versions = self._history.get(old)
        if versions is not None and old != new:
            with self.db.transaction():
                self._history.delete(old)
                self._history.put(new, versions)

    # -- the short notes about shelves -----------------------------------------------------------
    def labels(self) -> dict:
        return {i: b for i, b in self._labels.items() if isinstance(b, str)}

    def set_label(self, path: str, text: str) -> None:
        if text:
            self._labels.put(path, text)
        else:
            self._labels.delete(path)

    def replace_labels(self, labels: dict) -> None:
        with self.db.transaction():
            self._labels.clear()
            for k, v in labels.items():
                self._labels.put(k, v)

    # -- one-time import of the older JSON files ---------------------------------------------------
    def import_legacy(self, vault_json: Path | None, now: float) -> None:
        """First start after the move to a database: bring the old files in. They are left where they are as a backup."""
        if self.db.meta("imported") == "1":
            return
        with self.db.transaction():
            if vault_json is not None and Path(vault_json).exists() and self.notes.count() == 0:
                v = Vault.load(vault_json)
                self.write_changes({}, {r.id: r for r in v.all()})
            side = Path(vault_json).parent if vault_json is not None else None
            if side is not None:
                for name, load in (("memory-trash.json", self._import_trash), ("memory-history.json", self._import_history), ("shelves.json", self._import_labels)):
                    f = side / name
                    if f.exists():
                        try:
                            load(json.loads(f.read_text(encoding="utf-8")))
                        except (OSError, ValueError):
                            pass
            self.db.set_meta("imported", "1")

    def _import_trash(self, entries) -> None:
        for e in entries if isinstance(entries, list) else []:
            if isinstance(e, dict) and "unit" in e and "deleted_at" in e:
                self._trash.put(f"{e['unit']}@{e['deleted_at']}", e, e["deleted_at"])

    def _import_history(self, hist) -> None:
        for unit, versions in (hist.items() if isinstance(hist, dict) else []):
            if isinstance(versions, list):
                self._history.put(unit, versions)

    def _import_labels(self, labels) -> None:
        for k, v in (labels.items() if isinstance(labels, dict) else []):
            if isinstance(k, str) and isinstance(v, str):
                self._labels.put(k, v)
