import pytest

from bridge.memory.broker import Lens, MemoryBroker, Verdict
from bridge.memory.vault import Record, Vault


@pytest.fixture
def vault():
    return Vault([
        Record("n1", "note", "low", "Quarterly sales review notes for the team"),
        Record("n2", "note", "medium", "Sales pipeline: three big accounts at risk"),
        Record("n3", "note", "high", "Salary of every employee, confidential"),
        Record("c1", "contact", "low", "Maria Lopez, sales lead, maria@example.com"),
        Record("f1", "finance", "high", "Bank account 000111222, balance 91000"),
    ])


def broker(vault, **kw):
    lens = Lens(types=frozenset({"note", "contact"}), **kw)
    return MemoryBroker(vault, lens, run_seed="seed-1")


def test_stages_only_what_the_lens_allows(vault):
    b = broker(vault)
    assert set(b.manifest) == {"n1", "c1"}  # n2, n3 and f1 are secret or in a closed drawer
    assert b.describe()["by_type"] == {"note": 1, "contact": 1}


def test_search_returns_only_in_lens_records(vault):
    b = broker(vault)
    r = b.search("sales")
    assert r.verdict is Verdict.ALLOW
    assert {x["id"] for x in r.records} <= {"n1", "n2", "c1"}
    assert r.records


def test_cannot_read_record_outside_staged_set(vault):
    b = broker(vault)
    r = b.read("n3")  # real record, too sensitive
    assert r.verdict is Verdict.DENY and r.records == []
    assert b.events[-1].kind == "UNKNOWN_ID"
    assert not b.killed


def test_off_lens_query_serves_decoy_and_does_not_leak_real_data(vault):
    b = broker(vault)
    r = b.search("bank balance", type="finance")
    assert r.verdict is Verdict.DENY
    assert len(r.records) == 1 and "CANARY" in r.records[0]["text"]
    assert "000111222" not in r.records[0]["text"]
    assert [e.kind for e in b.events] == ["OFF_LENS_QUERY"]
    assert not b.killed  # asking is a strike; touching the bait is the kill


def test_reading_the_decoy_kills_the_run(vault):
    b = broker(vault)
    decoy_id = b.search("x", type="finance").records[0]["id"]
    r = b.read(decoy_id)
    assert r.verdict is Verdict.KILL and b.killed
    assert b.events[-1].kind == "CANARY_HIT"
    # once killed, everything is refused
    assert b.search("sales").verdict is Verdict.KILL
    assert b.read("n1").verdict is Verdict.KILL


def test_in_lens_results_never_contain_decoys(vault):
    b = broker(vault)
    b.search("x", type="finance")  # creates a decoy
    for q in ("sales", "salary", "confidential", "canary", "record"):
        for rec in b.search(q).records:
            assert "CANARY" not in rec["text"]


def test_read_budget_is_enforced_and_counted(vault):
    b = broker(vault, max_reads=2)
    first = b.search("sales")
    assert len(first.records) == 2
    r = b.read("c1")
    assert r.verdict is Verdict.DENY
    assert b.events[-1].kind == "READ_BUDGET"
    assert len(b.reads) == 2


def test_results_per_query_are_capped(vault):
    b = broker(vault, max_results_per_query=1)
    assert len(b.search("sales").records) == 1


def test_decoy_is_stable_within_a_run_and_differs_across_runs(vault):
    lens = Lens(types=frozenset({"note"}))
    a1 = MemoryBroker(vault, lens, run_seed="A")
    a2 = MemoryBroker(vault, lens, run_seed="A")
    b1 = MemoryBroker(vault, lens, run_seed="B")
    id_a = a1.search("x", type="finance").records[0]["id"]
    assert id_a == a1.search("y", type="finance").records[0]["id"]
    assert id_a == a2.search("x", type="finance").records[0]["id"]
    assert id_a != b1.search("x", type="finance").records[0]["id"]


def test_canary_values_exposed_for_the_result_guard(vault):
    b = broker(vault)
    assert b.canary_values == []
    b.search("x", type="finance")
    assert any(v.startswith("CANARY-") for v in b.canary_values)


def test_max_records_caps_staging(vault):
    b = broker(vault, max_records=2)
    assert len(b.manifest) == 2


def test_bad_sensitivity_rejected():
    with pytest.raises(ValueError):
        Lens(types=frozenset({"note"}), max_sensitivity="top-secret")


def test_search_ignores_filler_words_and_matches_word_stems(vault):
    b = broker(vault)
    ids = [r["id"] for r in b.search("What does Maria prefer?").records]
    assert ids[0] == "c1"  # 'prefer' finds 'prefers', and 'what does' count for nothing


def test_a_vague_question_gets_nothing_unless_fallback_is_asked_for(vault):
    b = broker(vault)
    assert b.search("anything new?").records == []
    got = b.search("anything new?", fallback=True)
    assert {r["id"] for r in got.records} <= {"n1", "n2", "c1"} and got.records  # the shared records, never the locked ones


def test_fallback_never_reaches_outside_the_lens(vault):
    b = broker(vault)
    ids = {r["id"] for r in b.search("zzz qqq", fallback=True).records}
    assert "n3" not in ids and "f1" not in ids


def test_fallback_still_counts_against_the_read_budget(vault):
    b = broker(vault, max_reads=1)
    first = b.search("nothing matches", fallback=True)
    assert len(first.records) == 1
    assert b.search("again nothing", fallback=True).verdict is Verdict.DENY


def test_a_single_file_can_be_shared_even_though_its_type_would_not_be():
    v = Vault([Record("n1", "note", "low", "a note"), Record("f1", "finance", "low", "Coffee budget is 40 a month")])
    lens = Lens(types=frozenset({"note"}), include=frozenset({"f1"}))  # the user opened just the one file
    b = MemoryBroker(v, lens, run_seed="s")
    assert set(b.manifest) == {"n1", "f1"}
    assert b.read("f1").verdict is Verdict.ALLOW


def test_a_secret_file_stays_home_even_if_someone_ticks_it(vault):
    lens = Lens(types=frozenset({"note"}), include=frozenset({"f1", "n3"}))
    b = MemoryBroker(vault, lens, run_seed="s")
    assert "f1" not in b.manifest and "n3" not in b.manifest
    assert b.read("f1").verdict is Verdict.DENY


def test_a_single_file_can_be_held_back_whatever_else_says_yes(vault):
    lens = Lens(types=frozenset({"note", "contact"}), exclude=frozenset({"n1"}))
    b = MemoryBroker(vault, lens, run_seed="s")
    assert "n1" not in b.manifest and b.read("n1").verdict is Verdict.DENY


def test_exclusion_beats_inclusion():
    v = Vault([Record("a", "note", "low", "x")])
    b = MemoryBroker(v, Lens(types=frozenset({"note"}), include=frozenset({"a"}), exclude=frozenset({"a"})), run_seed="s")
    assert b.manifest == {}
