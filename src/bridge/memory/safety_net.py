"""The safety net around memory: nothing a person does here is final by accident.

  trash     a deleted note waits 30 days and can be put back, with its shelf and its passages;
  history   every time the text of a note is changed, the old text is kept (the last 10 versions) and can be restored;
  similar   saving something that nearly repeats an existing note says so, without blocking it;
  bulk      move, re-label or delete many notes in one step, all or nothing;
  backup    the whole memory as one file you can keep, and put back later.

These live in the same database as the notes, in their own tables, so a note's history never slows the notes down.
"""
from __future__ import annotations

from dataclasses import asdict

from .chunking import join_document
from .tree import pretty
from .vault import Record, Vault, clean_path
from .words import surface

TRASH_DAYS = 30
MAX_TRASH = 200
MAX_VERSIONS = 10
BACKUP_FORMAT = "agent-bridge-memory"
MAX_BACKUP_RECORDS = 5000


class SafetyNet:
    """Mixed into MemoryService. Needs: self.store, self.clock, self.lock, self._mutate, self.vault, self.threads, self._path,
    self._level and MemoryChangeError (passed as self.Error)."""

    # -- trash -----------------------------------------------------------------------------------
    def _to_trash(self, members: list[Record], now: float) -> None:
        first = members[0]
        text = join_document([m.text for m in sorted(members, key=lambda m: m.part)]) if first.doc else first.text
        self.store.trash_purge(now - TRASH_DAYS * 86400)
        self.store.trash_add({"unit": first.unit, "title": first.title if first.doc else "", "preview": text[:160], "shelf": first.shelf,
                              "level": "low" if first.sensitivity == "low" else "high", "long": bool(first.doc), "deleted_at": now,
                              "records": [asdict(m) for m in members]}, MAX_TRASH)

    def trash(self) -> list[dict]:
        now = self.clock()
        self.store.trash_purge(now - TRASH_DAYS * 86400)
        entries = self.store.trash_entries()
        return [{"unit": e["unit"], "title": e["title"], "preview": e["preview"], "shelf": e["shelf"], "shelf_name": pretty(e["shelf"]),
                 "level": e["level"], "long": e["long"], "deleted_at": e["deleted_at"],
                 "days_left": max(0, TRASH_DAYS - int((now - e["deleted_at"]) // 86400))} for e in reversed(entries)]

    def restore(self, unit: str) -> dict:
        now = self.clock()
        self.store.trash_purge(now - TRASH_DAYS * 86400)
        entry = next((e for e in reversed(self.store.trash_entries()) if e["unit"] == unit), None)
        if entry is None:
            raise self.Error("that note is no longer in the trash")

        def go(v: Vault):
            recs = [Record(**r) for r in entry["records"]]
            taken = self._referenced() | {r.id for r in v.all()}
            if recs[0].doc:
                doc = recs[0].doc
                if v.parts(doc) or doc in taken:  # the number was reused while the note was in the trash
                    doc = self._fresh_doc(v, taken)
                from dataclasses import replace
                recs = [replace(r, doc=doc, id=f"{doc}.{r.part}") for r in recs]
            elif recs[0].id in taken:
                rid = v.next_id("m")
                while rid in taken:
                    rid = "m" + str(int(rid[1:]) + 1)
                from dataclasses import replace
                recs = [replace(recs[0], id=rid)]
            for r in recs:
                v.add(r)
            return recs[0].unit
        new_unit = self._mutate(go)
        self.store.trash_remove(entry)
        return {"id": new_unit}

    def empty_trash(self) -> dict:
        return {"emptied": self.store.trash_clear()}

    # -- history ---------------------------------------------------------------------------------
    def _push_history(self, unit: str, text: str, title: str, now: float) -> None:
        self.store.push_version(unit, {"text": text, "title": title, "at": now}, MAX_VERSIONS)

    def _move_history(self, old: str, new: str) -> None:
        self.store.move_versions(old, new)

    def history(self, record_id: str) -> list[dict]:
        unit = self.vault().unit_of(record_id)
        versions = self.store.versions(unit or "")
        return [{"index": i, "text": v["text"], "title": v.get("title", ""), "at": v["at"], "chars": len(v["text"])} for i, v in reversed(list(enumerate(versions)))]

    def restore_version(self, record_id: str, index) -> dict:
        unit = self.vault().unit_of(record_id)
        versions = self.store.versions(unit or "")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(versions):
            raise self.Error("that earlier version is not available any more")
        return self.update(unit, text=versions[index]["text"])

    # -- near duplicates ---------------------------------------------------------------------------
    def similar(self, text: str, limit: int = 3) -> list[dict]:
        mine = set(surface(text))
        if len(mine) < 4:
            return []
        out = []
        for r in self.vault().all():
            if r.doc:
                continue
            theirs = set(surface(r.text))
            if len(theirs) >= 4 and len(mine & theirs) / len(mine | theirs) >= 0.7:
                out.append({"id": r.id, "text": r.text, "shelf_name": pretty(r.shelf)})
        return out[:limit]

    # -- many at once ------------------------------------------------------------------------------
    def bulk(self, ids, op: str, *, shelf=None, level=None) -> dict:
        if not isinstance(ids, list) or not ids or len(ids) > 200 or not all(isinstance(i, str) for i in ids):
            raise self.Error("choose between 1 and 200 notes")
        if op not in ("move", "level", "delete"):
            raise self.Error("choose what to do with them: move, change everyday or secret, or delete")
        path = self._path(shelf) if op == "move" else ""
        if op == "move" and not path:
            raise self.Error("say which shelf they should go to")
        lvl = self._level(level) if op == "level" else None
        now = self.clock()
        gone: set = set()

        def go(v: Vault):
            units = []
            for i in ids:
                u = v.unit_of(i)
                if u is None:
                    raise self.Error("one of those notes is no longer in your memory")
                if u not in units:
                    units.append(u)
            for u in units:
                members = v.parts(u) if v.parts(u) else [v.get(u)]
                if op == "delete":
                    self._to_trash(members, now)
                    for m in members:
                        v.remove(m.id)
                        gone.add(m.id)
                    gone.add(u)
                else:
                    for m in members:
                        v.update(m.id, now=now, **({"path": path} if op == "move" else {"sensitivity": lvl}))
            return len(units)
        n = self._mutate(go)
        if gone:
            self._forget_in_chats(gone)
        return {"changed": n}

    # -- backup ----------------------------------------------------------------------------------------
    def export_backup(self) -> dict:
        v = self.vault()
        return {"format": BACKUP_FORMAT, "version": 1, "exported": self.clock(), "notes": len({r.unit for r in v.all()}),
                "records": [asdict(r) for r in v.all()], "shelf_notes": self.labels()}

    def restore_backup(self, data) -> dict:
        if not isinstance(data, dict) or data.get("format") != BACKUP_FORMAT or not isinstance(data.get("records"), list):
            raise self.Error("that file is not a memory backup from this app")
        if len(data["records"]) > MAX_BACKUP_RECORDS:
            raise self.Error(f"a backup can hold at most {MAX_BACKUP_RECORDS} records here")
        try:
            recs = [Record(**{k: v for k, v in raw.items()}) for raw in data["records"]]
        except (TypeError, ValueError, AttributeError) as e:
            raise self.Error("the backup is damaged: " + str(e)[:80]) from e
        groups: dict[str, list[Record]] = {}
        for r in recs:
            groups.setdefault(r.unit, []).append(r)
        added = skipped = 0

        def go(v: Vault):
            nonlocal added, skipped
            for unit, members in groups.items():
                if any(v.get(m.id) is not None for m in members) or (members[0].doc and v.parts(members[0].doc)):
                    skipped += 1  # a note with this id is already here: the backup never overwrites what you have now
                    continue
                for m in members:
                    v.add(m)
                added += 1
        self._mutate(go)
        labels = self.labels()
        for k, text in (data.get("shelf_notes") or {}).items():
            try:
                k = clean_path(k)
            except ValueError:
                continue
            if isinstance(text, str) and k and k not in labels:
                labels[k] = text[:120]
        self.store.replace_labels(labels)
        return {"added": added, "skipped": skipped}
