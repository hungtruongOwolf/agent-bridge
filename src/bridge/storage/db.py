"""One small SQLite database per kind of data, instead of a JSON file rewritten whole on every change.

A change writes only the rows it touched, inside one transaction, so a crash never leaves half a change and a big memory
costs the same to edit as a small one. The files are WAL-mode SQLite: readers never block the writer.
Every part keeps its own data in a named collection of documents (id -> JSON body), with an optional number to sort by.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS docs ("
    " coll TEXT NOT NULL, id TEXT NOT NULL, sort REAL NOT NULL DEFAULT 0, body TEXT NOT NULL,"
    " PRIMARY KEY (coll, id)) WITHOUT ROWID",
    "CREATE INDEX IF NOT EXISTS docs_sort ON docs (coll, sort)",
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
)


class Database:
    """One connection shared by every thread and guarded by one lock: a request thread never opens a connection of its own (they would pile up)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, timeout=15, isolation_level=None, check_same_thread=False)  # we begin and commit ourselves
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self.transaction() as c:
            for stmt in SCHEMA:
                c.execute(stmt)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def query(self, sql: str, args=()) -> list:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    @contextmanager
    def transaction(self):
        """Everything inside happens together or not at all. Nested use joins the outer transaction."""
        with self._lock:
            c = self._conn
            if c.in_transaction:
                yield c
                return
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
            except BaseException:
                c.execute("ROLLBACK")
                raise
            else:
                c.execute("COMMIT")

    def collection(self, name: str) -> "Collection":
        return Collection(self, name)

    def meta(self, key: str, default: str = "") -> str:
        rows = self.query("SELECT value FROM meta WHERE key=?", (key,))
        return rows[0][0] if rows else default

    def set_meta(self, key: str, value: str) -> None:
        with self.transaction() as c:
            c.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


class Collection:
    """Documents of one kind: put/get/delete by id, list in order, and apply many changes in one transaction."""

    def __init__(self, db: Database, name: str):
        self.db, self.name = db, name

    def put(self, id: str, body, sort: float = 0.0) -> None:
        with self.db.transaction() as c:
            self._put(c, id, body, sort)

    def _put(self, c, id: str, body, sort: float = 0.0) -> None:
        c.execute("INSERT INTO docs(coll, id, sort, body) VALUES(?, ?, ?, ?) ON CONFLICT(coll, id) DO UPDATE SET sort=excluded.sort, body=excluded.body",
                  (self.name, id, sort, json.dumps(body, ensure_ascii=False)))

    def get(self, id: str, default=None):
        rows = self.db.query("SELECT body FROM docs WHERE coll=? AND id=?", (self.name, id))
        return json.loads(rows[0][0]) if rows else default

    def delete(self, *ids: str) -> None:
        if ids:
            with self.db.transaction() as c:
                c.executemany("DELETE FROM docs WHERE coll=? AND id=?", [(self.name, i) for i in ids])

    def clear(self) -> None:
        with self.db.transaction() as c:
            c.execute("DELETE FROM docs WHERE coll=?", (self.name,))

    def write(self, puts: dict | None = None, deletes=(), sorts: dict | None = None) -> None:
        """Apply many changes as one transaction: nothing is half written if one of them fails."""
        with self.db.transaction() as c:
            for i in deletes:
                c.execute("DELETE FROM docs WHERE coll=? AND id=?", (self.name, i))
            for i, body in (puts or {}).items():
                self._put(c, i, body, (sorts or {}).get(i, 0.0))

    def items(self, *, newest_first: bool = False) -> list[tuple[str, object]]:
        order = "DESC" if newest_first else "ASC"
        rows = self.db.query(f"SELECT id, body FROM docs WHERE coll=? ORDER BY sort {order}, id", (self.name,))
        return [(i, json.loads(b)) for i, b in rows]

    def count(self) -> int:
        return self.db.query("SELECT COUNT(*) FROM docs WHERE coll=?", (self.name,))[0][0]
