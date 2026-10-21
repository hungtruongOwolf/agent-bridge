import time

import pytest

from bridge.memory.broker import Lens, MemoryBroker, Verdict
from bridge.memory.tree import MemoryTree, pretty
from bridge.memory.vault import Record, Vault, clean_path, under


def rec(i, shelf, text, sens="low", type="note"):
    return Record(i, type, sens, text, path=shelf)


@pytest.fixture
def records():
    return [
        rec("a1", "work/clients/acme", "Acme renewal is at risk, budget cut"),
        rec("a2", "work/clients/acme", "Acme prefers email on Mondays"),
        rec("g1", "work/clients/globex", "Globex renewal slipped to December"),
        rec("m1", "work/meetings", "Priya books the offsite venue by Friday"),
        rec("p1", "personal/health", "Dentist appointment on Tuesday"),
        rec("s1", "personal", "Passport number", sens="high"),
    ]


def test_clean_path_normalises_and_refuses_odd_names():
    assert clean_path(" Work / Clients  ") == "work/clients"
    assert clean_path("") == ""
    for bad in ("a/" * 7 + "b", "x" * 31, "../etc", "semi;colon"):
        with pytest.raises(ValueError):
            clean_path(bad)
    assert under("work/clients", "work") and under("work", "work") and not under("workshop", "work")


def test_a_record_without_a_path_sits_on_the_shelf_named_after_its_type():
    assert Record("x", "contact", "low", "Maria").shelf == "contact"
    assert Record("x", "contact", "low", "Maria", path="people").shelf == "people"
    with pytest.raises(ValueError):
        Record("x", "note", "low", "hi", path="Not Clean")


def test_the_index_pages_count_everything_below(records):
    t = MemoryTree(records)
    top = {o["path"]: o for o in t.outline("")}
    assert top["work"]["count"] == 4 and top["personal"]["count"] == 2
    assert [o["path"] for o in t.outline("work")] == ["work/clients", "work/meetings"]
    assert t.nodes["work/clients"].count == 3
    assert "renewal" in t.keywords("work/clients")
    assert pretty("work/clients") == "Work › Clients"


def test_walking_down_opens_only_shelves_that_fit(records):
    t = MemoryTree(records)
    hits, opened = t.route("Which accounts renewal is at risk")
    assert hits[0].id == "a1"
    assert "work/clients/acme" in opened and "personal/health" not in opened
    hits, opened = t.route("dentist")
    assert [h.id for h in hits] == ["p1"] and "work" not in opened


def test_the_helper_tree_only_holds_shared_shelves(records):
    lens = Lens(types=frozenset(), shelves=frozenset({"work/clients"}))
    b = MemoryBroker(Vault(records), lens, run_seed="s")
    assert set(b.manifest) == {"a1", "a2", "g1"}
    r = b.search("dentist appointment")
    assert r.records == [] and b.walks[-1]["opened"] == [""]  # the other shelves are not even in its tree


def test_a_shelf_opens_everything_below_it_but_never_a_secret_file(records):
    lens = Lens(types=frozenset(), shelves=frozenset({"personal"}), include=frozenset({"s1"}))
    b = MemoryBroker(Vault(records), lens, run_seed="s")
    assert set(b.manifest) == {"p1"}
    assert b.read("s1").verdict is Verdict.DENY


def test_searching_records_the_walk(records):
    lens = Lens(types=frozenset(), shelves=frozenset({"work"}))
    b = MemoryBroker(Vault(records), lens, run_seed="s")
    r = b.search("Acme email")
    assert [x["id"] for x in r.records][0] == "a2"
    assert b.walks[0]["files"] and "work/clients" in b.walks[0]["opened"]
    assert b.shelf_of("a2") == "work/clients/acme"


def test_a_vague_question_gets_the_newest_files():
    old = Record("o", "note", "low", "old thing", created=10, path="a")
    new = Record("n", "note", "low", "new thing", created=99, path="b")
    b = MemoryBroker(Vault([old, new]), Lens(types=frozenset(), shelves=frozenset({"a", "b"})), run_seed="s")
    assert [x["id"] for x in b.search("zzz", fallback=True).records][0] == "n"


def test_asking_for_a_kind_nobody_shared_is_still_a_trap(records):
    lens = Lens(types=frozenset(), shelves=frozenset({"work"}))
    b = MemoryBroker(Vault(records + [Record("f9", "finance", "low", "Budget", path="money")]), lens, run_seed="s")
    r = b.search("budget", type="finance")
    assert r.verdict is Verdict.DENY and b.events[-1].kind == "OFF_LENS_QUERY"


def test_a_huge_memory_is_searched_by_deciding_not_scanning():
    big = [rec(f"r{i}", f"area{i % 40}/topic{i % 7}", f"entry {i} about subject{i % 40} detail{i % 997}") for i in range(20000)]
    big.append(rec("needle", "area7/topic3", "The zebra contract renews in March"))
    t0 = time.time()
    t = MemoryTree(big)
    built = time.time() - t0
    t0 = time.time()
    hits, opened = t.route("zebra contract")
    searched = time.time() - t0
    assert hits[0].id == "needle"
    assert len(opened) < 40, "only a few shelves are opened out of 280"
    assert searched < 0.2 and built < 10


def test_a_plural_and_its_ing_form_find_each_other():
    from bridge.memory.words import stem
    assert stem("meetings") == stem("meeting") == stem("meets")
    assert stem("prefers") == "prefer" and stem("accounts") == "account" and stem("budgets") == "budget"
    t = MemoryTree([rec("m1", "work/meetings", "Meeting notes, Monday: Priya will book the venue.")])
    assert [r.id for r in t.route("what are the action items from my meetings")[0]] == ["m1"]
