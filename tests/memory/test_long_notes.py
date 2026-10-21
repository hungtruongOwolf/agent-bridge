"""Long notes: a note of any realistic length is kept whole and stored as passages."""
import pytest

from bridge.memory.broker import Lens, MemoryBroker
from bridge.memory.service import MemoryChangeError

from test_service import svc  # noqa: F401  (the fixture)

from longtext import LONG  # noqa: E402


def test_a_long_note_is_kept_whole_and_shown_as_one_item(svc):
    out = svc.add("note", LONG, "low", "work/accounts")
    assert out["id"].startswith("doc")
    items = [i for i in svc.list() if i["id"] == out["id"]]
    assert len(items) == 1
    it = items[0]
    assert it["long"] and it["title"] == "Acme account plan" and it["parts"] > 3 and "zebra compliance" in it["text"] and it["chars"] > 3000
    assert len([r for r in svc.vault().all() if r.doc == out["id"]]) == it["parts"]
    assert svc.overview()["total"] == 3 and svc.overview()["long"] == 1


def test_a_helper_is_handed_the_passage_that_matters_not_the_whole_note(svc):
    svc.add("note", LONG, "low", "work/accounts")
    b = MemoryBroker(svc.vault(), Lens(types=frozenset(), shelves=frozenset({"work"})), run_seed="s")
    got = b.search("security review zebra").records
    assert got and "zebra" in got[0]["text"] and len(got[0]["text"]) <= 1300 and got[0]["note"] == "Acme account plan" and got[0]["part"] > 1
    assert len(b.search("acme account plan").records) >= 3


def test_a_long_note_can_be_edited_moved_and_made_secret_as_one_piece(svc):
    doc = svc.add("note", LONG, "low", "work")["id"]
    svc.update(doc, sensitivity="high", path="work/private")
    recs = [r for r in svc.vault().all() if r.doc == doc]
    assert {r.sensitivity for r in recs} == {"high"} and {r.shelf for r in recs} == {"work/private"}
    assert svc.update(doc, text="# Acme account plan v2\n\n" + "Everything changed. " * 200)["edited"]
    it = next(i for i in svc.list() if i["id"] == doc)
    assert it["text"].startswith("# Acme account plan v2") and it["edited"] and it["created"] > 0


def test_deleting_a_long_note_removes_every_passage_and_forgets_it_in_chats(svc):
    doc = svc.add("note", LONG, "low")["id"]
    t = svc.threads.create("k1")
    svc.threads.settings(t.id, include=[doc], exclude=[doc + ".2"])
    svc.delete(doc)
    assert not [r for r in svc.vault().all() if r.doc == doc]
    assert svc.threads.get(t.id).lens.include == [] and svc.threads.get(t.id).lens.exclude == []
    with pytest.raises(MemoryChangeError):
        svc.delete(doc)


def test_a_short_note_that_grows_long_becomes_a_long_note(svc):
    out = svc.update("n1", text="Sales pipeline review. " + "More detail about every account. " * 80)
    assert out["id"].startswith("doc") and svc.vault().get("n1") is None
    assert svc.list(ids=[out["id"]])[0]["long"]


def test_a_chat_can_hold_back_one_long_note_by_its_id(svc):
    doc = svc.add("note", LONG, "low", "work")["id"]
    b = MemoryBroker(svc.vault(), Lens(types=frozenset(), shelves=frozenset({"work"}), exclude=frozenset({doc})), run_seed="s")
    assert b.manifest == {}
    b = MemoryBroker(svc.vault(), Lens(types=frozenset(), include=frozenset({doc})), run_seed="s")
    assert len(b.manifest) > 3


def test_a_too_long_note_is_refused_and_a_batch_with_one_is_all_or_nothing(svc):
    before = len(svc.vault().all())
    with pytest.raises(MemoryChangeError, match="80,000"):
        svc.add_many(["fine note", "y" * 90000], "low", "note")
    assert len(svc.vault().all()) == before
    out = svc.add_many([{"title": "Imported log", "text": LONG}, "a short one"], "low", "note", "imports")
    assert out["ids"][0].startswith("doc") and out["ids"][1].startswith("m")
    assert next(i for i in svc.list(ids=out["ids"][:1]))["title"] == "Imported log"
