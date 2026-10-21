import threading

import pytest

from bridge.chat.threads import ThreadStore
from bridge.memory.quarantine import Quarantine
from bridge.memory.service import MemoryChangeError, MemoryService
from bridge.memory.vault import Record, Vault


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        self.t += 1
        return self.t


class FakeRegistry:
    class R:
        def __init__(self, i, d):
            self.id, self.digest = i, d

    def __init__(self):
        self.records = {"k": self.R("deal-brief", "sha256:d1")}


@pytest.fixture
def svc(tmp_path):
    Vault([Record("n1", "note", "low", "Sales pipeline review"), Record("c1", "contact", "low", "Maria Lopez")]).save(tmp_path / "vault.json")
    threads = ThreadStore(tmp_path / "threads.json", clock=Clock())
    return MemoryService(tmp_path / "vault.json", Quarantine(clock=Clock()), threads=threads, registry=FakeRegistry(), clock=Clock())


def test_listing_says_where_each_item_came_from(svc):
    items = {i["id"]: i for i in svc.list()}
    assert items["n1"]["source"] == "you" and items["n1"]["helper"] is None and items["n1"]["used"]["answers"] == 0


def test_adding_a_note_gets_a_fresh_id_and_a_timestamp(svc):
    out = svc.add("note", "  Renewal call on Friday  ", "low")
    item = next(i for i in svc.list() if i["id"] == out["id"])
    assert item["text"] == "Renewal call on Friday" and item["created"] > 0 and item["source"] == "you"
    assert svc.add("note", "another", "low")["id"] != out["id"]


@pytest.mark.parametrize("args,msg", [(("note", "", "low"), "some text"), (("note", "x", "top"), "everyday or secret"),
                                      (("Bad Type", "x", "low"), "type must be"), (("note", "x" * 80001, "low"), "up to 80,000")])
def test_bad_notes_are_refused_with_a_plain_reason(svc, args, msg):
    with pytest.raises(MemoryChangeError, match=msg):
        svc.add(*args)
    assert len(svc.list()) == 2  # nothing was saved


def test_correcting_a_note_marks_it_edited_and_keeps_the_rest(svc):
    svc.update("n1", text="Sales pipeline review (corrected)")
    item = next(i for i in svc.list() if i["id"] == "n1")
    assert item["edited"] and item["text"].endswith("(corrected)") and item["updated"] > 0


def test_changing_how_private_a_note_is(svc):
    svc.update("c1", sensitivity="high")
    assert next(i for i in svc.list() if i["id"] == "c1")["sensitivity"] == "high"
    with pytest.raises(MemoryChangeError, match="everyday or secret"):
        svc.update("c1", sensitivity="top")


def test_changing_or_deleting_something_that_is_gone_is_a_clear_error(svc):
    with pytest.raises(MemoryChangeError, match="no longer in your memory"):
        svc.update("zzz", text="x")
    svc.delete("n1")
    with pytest.raises(MemoryChangeError, match="no longer in your memory"):
        svc.delete("n1")
    assert [i["id"] for i in svc.list()] == ["c1"]


def test_deleting_a_file_removes_it_from_every_chat_that_picked_it(svc):
    t = svc.threads.create("k1")
    svc.threads.settings(t.id, include=["n1", "c1"], exclude=["c1x"])
    svc.threads.settings(t.id, exclude=["n1"])
    svc.delete("n1")
    lens = svc.threads.get(t.id).lens
    assert "n1" not in lens.include and "n1" not in lens.exclude


def test_usage_counts_the_answers_a_file_helped_write(svc):
    t = svc.threads.create("k1", "Sales chat")
    svc.threads.add(t.id, "helper", "Acme is at risk", files=["n1"])
    svc.threads.add(t.id, "helper", "Maria prefers email", files=["n1", "c1"])
    used = {i["id"]: i["used"] for i in svc.list()}
    assert used["n1"]["answers"] == 2 and used["n1"]["last_chat"] == "Sales chat" and used["c1"]["answers"] == 1


def test_an_accepted_suggestion_names_the_helper_and_the_run(svc):
    (p,), _ = svc.quarantine.add("run-abc123", "sha256:d1", [{"type": "note", "text": "Acme renewal at risk"}])
    out = svc.accept_proposal(p.id)
    item = next(i for i in svc.list() if i["id"] == out["accepted"])
    assert item["source"] == "helper" and item["helper"] == "Deal Brief" and item["from_run"] == "run-abc123" and item["created"] > 0
    with pytest.raises(MemoryChangeError, match="no such pending"):
        svc.accept_proposal(p.id)


def test_discarding_a_suggestion_and_undoing_a_run(svc):
    (a, b), _ = svc.quarantine.add("run-r1", "sha256:d1", [{"type": "note", "text": "one"}, {"type": "note", "text": "two"}])
    svc.reject_proposal(a.id)
    svc.accept_proposal(b.id)
    out = svc.revert_run("run-r1")
    assert out["removed_from_vault"] == 1 and len(svc.list()) == 2
    with pytest.raises(MemoryChangeError):
        svc.reject_proposal("nope")


def test_two_requests_at_once_cannot_overwrite_each_other(svc):
    def add(i):
        svc.add("note", f"note {i}", "low")
    ts = [threading.Thread(target=add, args=(i,)) for i in range(25)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    items = svc.list()
    assert len(items) == 27 and len({i["id"] for i in items}) == 27  # nothing lost, no duplicate ids


from longtext import LONG  # noqa: E402

# ---- the safety net: trash, history, near duplicates, many at once, backup ----------------------------------

def test_a_deleted_note_waits_in_the_trash_and_can_be_put_back(svc):
    svc.delete("n1")
    assert svc.vault().get("n1") is None
    t = svc.trash()
    assert [x["unit"] for x in t] == ["n1"] and t[0]["preview"].startswith("Sales pipeline") and t[0]["days_left"] == 30
    assert svc.restore("n1")["id"] == "n1" and svc.vault().get("n1").text == "Sales pipeline review"
    assert svc.trash() == []
    with pytest.raises(MemoryChangeError, match="no longer in the trash"):
        svc.restore("n1")


def test_a_long_note_comes_back_whole_and_ids_taken_meanwhile_are_not_stolen(svc):
    doc = svc.add("note", LONG, "low", "work")["id"]
    svc.delete(doc)
    other = svc.add("note", LONG.replace("Acme", "Zeta"), "low", "work")["id"]  # takes the freed doc number
    back = svc.restore(doc)["id"]
    assert back != other and len(svc.vault().parts(back)) == len(svc.vault().parts(other))
    assert svc.list(ids=[back])[0]["title"] == "Acme account plan"
    svc.delete("n1")
    n = svc.add("note", "A brand new note about something else entirely", "low")["id"]
    assert svc.restore("n1")["id"] != n


def test_the_trash_forgets_after_thirty_days_and_can_be_emptied(svc):
    svc.delete("n1")
    svc.clock.t += 31 * 86400
    assert svc.trash() == []
    svc.delete("c1")
    assert svc.empty_trash()["emptied"] == 1 and svc.trash() == []


def test_every_change_of_text_keeps_the_old_text_and_can_be_undone(svc):
    svc.update("n1", text="Sales pipeline review, second draft")
    svc.update("n1", text="Sales pipeline review, third draft")
    h = svc.history("n1")
    assert [v["text"] for v in h] == ["Sales pipeline review, second draft", "Sales pipeline review"]
    svc.restore_version("n1", h[1]["index"])
    assert svc.vault().get("n1").text == "Sales pipeline review"
    assert svc.history("n1")[0]["text"] == "Sales pipeline review, third draft"  # undoing is itself kept
    with pytest.raises(MemoryChangeError):
        svc.restore_version("n1", 99)
    for i in range(15):
        svc.update("n1", text=f"version {i}")
    assert len(svc.history("n1")) == 10


def test_history_follows_a_note_that_grows_into_a_long_note(svc):
    out = svc.update("n1", text="Sales pipeline review. " + "More detail about every account. " * 80)
    assert out["id"].startswith("doc") and [v["text"] for v in svc.history(out["id"])] == ["Sales pipeline review"]


def test_saving_something_that_repeats_a_note_says_so_but_still_saves(svc):
    out = svc.add("note", "Sales pipeline review", "low")
    assert out["similar"] == [] and out["id"]  # the same words as n1 but too short to compare
    svc.add("note", "Acme wants invoices on the first of every month in euros", "low")
    twin = svc.add("note", "Acme wants invoices on the first of every month, in euros.", "low")
    assert len(twin["similar"]) == 1 and "euros" in twin["similar"][0]["text"] and twin["id"]
    assert svc.add("note", "A completely different idea about the weekly digest email", "low")["similar"] == []


def test_many_notes_can_be_moved_made_secret_or_deleted_in_one_step(svc):
    a = svc.add("note", "First note about the offsite budget for the whole team", "low", "work")["id"]
    b = svc.add("note", "Second note about the offsite venue in Santa Fe", "low", "work")["id"]
    assert svc.bulk([a, b], "move", shelf="work/offsite") == {"changed": 2}
    assert {svc.vault().get(i).shelf for i in (a, b)} == {"work/offsite"}
    svc.bulk([a, b], "level", level="high")
    assert {svc.vault().get(i).sensitivity for i in (a, b)} == {"high"}
    with pytest.raises(MemoryChangeError, match="no longer"):
        svc.bulk([a, "nope"], "delete")
    assert svc.vault().get(a) is not None  # all or nothing
    assert svc.bulk([a, b], "delete") == {"changed": 2}
    assert {x["unit"] for x in svc.trash()} == {a, b}
    for bad in (([], "move"), (["n1"], "burn"), (["n1"], "move"), (["x"] * 201, "delete")):
        with pytest.raises(MemoryChangeError):
            svc.bulk(*bad)


def test_a_backup_round_trips_and_never_overwrites_what_is_there_now(svc, tmp_path):
    doc = svc.add("note", LONG, "low", "work")["id"]
    svc.set_label("work", "Everything about the job")
    backup = svc.export_backup()
    assert backup["format"] == "agent-bridge-memory" and backup["notes"] == 3 and backup["shelf_notes"] == {"work": "Everything about the job"}
    Vault([Record("n1", "note", "low", "A different note that owns the id n1")]).save(tmp_path / "other.json")  # an older file is imported at start
    other = MemoryService(tmp_path / "other.json", Quarantine(clock=Clock()), clock=Clock())
    out = other.restore_backup(backup)
    assert out == {"added": 2, "skipped": 1}  # n1 was already taken, so it was left alone
    assert other.vault().get("n1").text.startswith("A different") and other.vault().parts(doc) and other.labels() == {"work": "Everything about the job"}
    for bad in (None, {"format": "x"}, {"format": "agent-bridge-memory", "records": [{"id": "z"}]}, {"format": "agent-bridge-memory", "records": "no"}):
        with pytest.raises(MemoryChangeError):
            other.restore_backup(bad)
