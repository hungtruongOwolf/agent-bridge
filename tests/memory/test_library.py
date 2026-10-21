"""The demo library is a test bed: a lived-in memory with many cases. These are the questions a person would really ask."""
from pathlib import Path

import pytest

from bridge.memory.broker import Lens, MemoryBroker, Verdict
from bridge.memory.tree import MemoryTree
from bridge.memory.vault import Vault

PATH = Path(__file__).resolve().parent.parent.parent / "examples" / "vault-library.json"
ALL = frozenset({"work", "people", "personal", "family", "projects", "money", "reading", "recipes", "ideas"})


@pytest.fixture(scope="module")
def vault():
    return Vault.load(PATH)


def broker(vault, shelves=ALL):
    return MemoryBroker(vault, Lens(types=frozenset(), shelves=frozenset(shelves)), run_seed="lib")


def test_the_library_has_the_shape_of_a_real_memory(vault):
    recs = vault.all()
    tree = MemoryTree(recs)
    units = {r.unit for r in recs}
    assert len(units) >= 130 and len(tree.shelves()) >= 40
    assert max(p.count("/") for p in tree.shelves()) >= 2  # shelves inside shelves inside shelves
    assert len({r.doc for r in recs if r.doc}) >= 8  # long notes
    assert len({r.unit for r in recs if r.sensitivity != "low"}) >= 12  # secret notes
    assert max(len(r.text) for r in recs) <= 1200 and any(len(vault.parts(d)) >= 3 for d in {r.doc for r in recs if r.doc})
    assert {"note", "contact", "finance"} <= {r.type for r in recs}
    times = sorted({r.created for r in recs})
    assert times[-1] - times[0] > 200 * 86400  # written across most of a year


@pytest.mark.parametrize("question,expect", [
    ("Which accounts are at risk?", {"n1", "m101", "doc1.3", "doc2.1"}),
    ("when is my dentist appointment", {"m161"}),
    ("who owns the security questionnaire", {"m121", "m105"}),
    ("what is Maria's email preference", {"c1"}),
    ("hackathon deadline", {"m183", "m184"}),
    ("when is mum's birthday", {"c115", "m148"}),
    ("where does grandma live", {"m157", "c117"}),
    ("how do I make bun cha", {"m190"}),
    ("tomas lisbon hiking", {"c112"}),
    ("Globex renewal", {"m110", "m108", "doc2.1"}),
])
def test_everyday_questions_find_the_right_notes(vault, question, expect):
    got = {x["id"] for x in broker(vault).search(question).records}
    assert got & expect, (question, got)


def test_the_best_note_comes_first_when_a_short_note_says_it_plainly(vault):
    assert broker(vault).search("when is my dentist appointment").records[0]["id"] == "m161"  # not the trip note that mentions it
    assert broker(vault).search("what is Maria's email preference").records[0]["id"] == "c1"


def test_secret_notes_never_reach_a_helper_even_with_every_shelf_open(vault):
    b = broker(vault, ALL)
    secret_ids = {r.id for r in vault.all() if r.sensitivity != "low"}
    assert not secret_ids & set(b.manifest)
    for q in ("bank balance", "salary table", "passport number", "therapy thursday", "performance review", "journal worried company"):
        assert not {x["id"] for x in b.search(q).records} & secret_ids, q
    assert b.read("f1").verdict is Verdict.DENY


def test_a_closed_shelf_stays_closed(vault):
    b = broker(vault, {"people"})
    assert b.search("dentist appointment").records == [] and b.search("hackathon deadline").records == []
    assert {x["id"] for x in b.search("Maria").records} <= {r.id for r in vault.all() if r.shelf.startswith("people")}


def test_two_people_with_the_same_name_can_be_told_apart(vault):
    ids = {x["id"]: x["text"] for x in broker(vault).search("Lee Chen procurement Wayne").records}
    assert any("Lee Chen" in t for t in ids.values())
    texts = [x["text"] for x in broker(vault).search("Lee Park support").records]
    assert any("Lee Park" in t for t in texts)


def test_the_newer_fact_is_findable_next_to_the_old_one(vault):
    texts = [x["text"] for x in broker(vault).search("Acme billing contact invoices").records]
    assert any("Tom Reyes" in t and "left in August" in t for t in texts)  # the note says who replaced him


def test_a_vague_question_gets_the_newest_notes(vault):
    newest = broker(vault).search("zzzz nothing matches", fallback=True).records
    created = {r.id: r.created for r in vault.all()}
    assert newest and created[newest[0]["id"]] >= sorted(created.values())[-12]


def test_a_long_note_is_found_by_a_passage_and_by_its_title(vault):
    b = broker(vault)
    hit = b.search("vendor review penetration test SOC 2").records[0]
    assert hit["note"] == "Wayne Corp vendor review, November" and hit["part"] >= 1
    assert len(b.search("Wayne Corp vendor review November").records) >= 3
