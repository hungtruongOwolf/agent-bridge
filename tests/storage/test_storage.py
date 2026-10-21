"""The database layer: a change writes only the rows it touched, all or nothing, and older JSON files come in once."""
import json
import threading
import time

import pytest

from bridge.memory.quarantine import Quarantine
from bridge.memory.service import MemoryService
from bridge.memory.vault import Record, Vault
from bridge.storage.db import Database
from bridge.storage.memory_store import MemoryStore


class Clock:
    def __call__(self):
        return 1_000_000.0


def test_documents_round_trip_and_keep_their_order(tmp_path):
    c = Database(tmp_path / "x.db").collection("things")
    c.put("b", {"n": 2}, sort=2)
    c.put("a", {"n": 1}, sort=1)
    assert c.get("a") == {"n": 1} and [i for i, _ in c.items()] == ["a", "b"] and [i for i, _ in c.items(newest_first=True)] == ["b", "a"]
    c.delete("a")
    assert c.get("a") is None and c.count() == 1


def test_a_transaction_that_fails_changes_nothing(tmp_path):
    db = Database(tmp_path / "x.db")
    c = db.collection("things")
    with pytest.raises(RuntimeError):
        with db.transaction():
            c.put("a", {"n": 1})
            raise RuntimeError("boom")
    assert c.get("a") is None


def test_many_threads_can_write_at_once(tmp_path):
    c = Database(tmp_path / "x.db").collection("things")
    def work(k):
        for i in range(25):
            c.put(f"{k}-{i}", {"k": k, "i": i})
    ts = [threading.Thread(target=work, args=(k,)) for k in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert c.count() == 200


def test_changing_one_note_writes_one_row(tmp_path):
    store = MemoryStore(Database(tmp_path / "m.db"))
    before = {f"n{i}": Record(f"n{i}", "note", "low", f"note number {i}") for i in range(500)}
    assert store.write_changes({}, before) == 500
    after = dict(before)
    after["n7"] = Record("n7", "note", "low", "changed")
    del after["n9"]
    assert store.write_changes(before, after) == 2
    v = store.load_vault()
    assert len(v.all()) == 499 and v.get("n7").text == "changed" and v.get("n9") is None


def test_a_starter_file_is_used_once_and_an_emptied_memory_stays_empty(tmp_path):
    seed = tmp_path / "seed.json"
    Vault([Record("n1", "note", "low", "first")]).save(seed)
    svc = MemoryService(tmp_path / "vault.json", Quarantine(clock=Clock()), clock=Clock(), seed=seed)
    assert [r.id for r in svc.vault().all()] == ["n1"]
    svc.delete("n1")
    again = MemoryService(tmp_path / "vault.json", Quarantine(clock=Clock()), clock=Clock(), seed=seed)
    assert again.vault().all() == []


def test_an_older_vault_file_is_imported_once_and_left_in_place(tmp_path):
    old = tmp_path / "vault.json"
    Vault([Record("n1", "note", "low", "from the old file")]).save(old)
    (tmp_path / "shelves.json").write_text(json.dumps({"note": "my notes"}))
    svc = MemoryService(old, Quarantine(clock=Clock()), clock=Clock())
    assert svc.vault().get("n1").text == "from the old file" and svc.labels() == {"note": "my notes"}
    svc.add("note", "added later", "low", "")
    again = MemoryService(old, Quarantine(clock=Clock()), clock=Clock())
    assert len(again.vault().all()) == 2 and old.exists()  # not imported twice, not deleted


def test_a_failed_change_leaves_memory_as_it_was(tmp_path):
    svc = MemoryService(tmp_path / "vault.json", Quarantine(clock=Clock()), clock=Clock())
    svc.add("note", "keep me", "low", "")
    with pytest.raises(RuntimeError):
        svc._mutate(lambda v: (v.add(Record("x1", "note", "low", "half")), (_ for _ in ()).throw(RuntimeError("boom"))))
    assert [r.text for r in svc.vault().all()] == ["keep me"]
    assert [r.text for r in MemoryService(tmp_path / "vault.json", Quarantine(clock=Clock()), clock=Clock()).vault().all()] == ["keep me"]


def test_editing_a_note_stays_fast_in_a_large_memory(tmp_path):
    svc = MemoryService(tmp_path / "vault.json", Quarantine(clock=Clock()), clock=Clock())
    svc.store.write_changes({}, {f"n{i}": Record(f"n{i}", "note", "low", f"note {i} about topic {i % 50}") for i in range(20000)})
    svc._vault = svc.store.load_vault()
    t = time.perf_counter()
    for i in range(20):
        svc.update(f"n{i}", text=f"edited {i}")
    per_edit = (time.perf_counter() - t) / 20
    assert per_edit < 0.15, per_edit  # the old way rewrote the whole file each time
