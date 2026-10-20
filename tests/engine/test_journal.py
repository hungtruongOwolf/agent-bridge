import json

import pytest

from bridge.engine.journal import GENESIS, Journal, JournalTampered


def test_chain_links_and_verifies():
    j = Journal()
    a = j.append("run_started", {"run": "r1"})
    b = j.append("step_committed", {"step": "read"})
    assert a["prev"] == GENESIS and b["prev"] == a["hash"] and j.head == b["hash"]
    j.verify()


def test_edit_of_past_entry_detected():
    j = Journal()
    j.append("a", {"x": 1})
    j.append("b", {"x": 2})
    j.entries[0]["data"]["x"] = 99
    with pytest.raises(JournalTampered):
        j.verify()


def test_deleted_entry_detected():
    j = Journal()
    for i in range(3):
        j.append("k", {"i": i})
    del j.entries[1]
    with pytest.raises(JournalTampered):
        j.verify()


def test_persists_and_reloads(tmp_path):
    p = tmp_path / "run.jsonl"
    j = Journal(p)
    j.append("a", {"x": 1})
    j.append("b", {"x": 2})
    again = Journal(p)
    assert [e["kind"] for e in again.entries] == ["a", "b"] and again.head == j.head
    again.append("c")
    assert len(Journal(p).entries) == 3


def test_torn_tail_is_dropped_with_marker(tmp_path):
    p = tmp_path / "run.jsonl"
    j = Journal(p)
    j.append("a", {"x": 1})
    j.append("b", {"x": 2})
    with open(p, "a", encoding="utf-8") as f:
        f.write('{"seq": 2, "kind": "c", "da')  # crash mid-write, no newline
    r = Journal(p)
    assert r.recovered_torn_tail
    assert [e["kind"] for e in r.entries] == ["a", "b", "recovered"]
    Journal(p).verify()


def test_tamper_in_the_middle_of_file_is_not_forgiven(tmp_path):
    p = tmp_path / "run.jsonl"
    j = Journal(p)
    for i in range(3):
        j.append("k", {"i": i})
    lines = p.read_text(encoding="utf-8").split("\n")
    e = json.loads(lines[1])
    e["data"]["i"] = 42
    lines[1] = json.dumps(e, sort_keys=True)
    p.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(JournalTampered):
        Journal(p)


def test_garbage_before_the_tail_is_tamper(tmp_path):
    p = tmp_path / "run.jsonl"
    Journal(p).append("a")
    p.write_text("garbage\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(JournalTampered):
        Journal(p)
