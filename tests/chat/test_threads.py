import pytest

from bridge.chat.threads import MAX_MESSAGES, ThreadError, ThreadStore, clean_lens


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        self.t += 1
        return self.t


@pytest.fixture
def store(tmp_path):
    return ThreadStore(tmp_path / "threads.json", clock=Clock())


def test_a_new_chat_has_sensible_defaults(store):
    t = store.create("k1")
    assert t.title == "New chat" and t.lens.shelves == [] and not t.lens.include
    assert t.history_turns == 4 and t.budget_cents == 200 and t.messages == [] and not t.busy


def test_messages_are_kept_in_order_and_survive_a_restart(store, tmp_path):
    t = store.create("k1", "Sales chat")
    store.add(t.id, "user", "Which accounts are at risk?")
    store.add(t.id, "helper", "Acme.", run_id="r1", files=["n1"], risk="high", price=40)
    again = ThreadStore(tmp_path / "threads.json")
    got = again.get(t.id)
    assert [m.role for m in got.messages] == ["user", "helper"] and got.messages[1].files == ["n1"] and got.messages[1].price == 40


def test_busy_is_not_remembered_across_a_restart(store, tmp_path):
    t = store.create("k1")
    store.begin(t.id, "hello")
    assert store.get(t.id).busy
    assert ThreadStore(tmp_path / "threads.json").get(t.id).busy is False


def test_only_one_message_at_a_time_and_it_must_be_a_real_message(store):
    t = store.create("k1")
    store.begin(t.id, "first")
    with pytest.raises(ThreadError, match="still working"):
        store.begin(t.id, "second")
    store.end(t.id)
    for bad in ("", "   ", None, 5):
        with pytest.raises(ThreadError, match="write a message"):
            store.begin(t.id, bad)
    with pytest.raises(ThreadError, match="up to 1000 characters"):
        store.begin(t.id, "x" * 1001)


def test_a_full_chat_says_so(store):
    t = store.create("k1")
    for i in range(MAX_MESSAGES):
        store.add(t.id, "user", f"m{i}")
    with pytest.raises(ThreadError, match="full"):
        store.begin(t.id, "one more")


def test_the_helper_is_shown_only_the_last_turns_and_never_system_notes(store):
    t = store.create("k1")
    store.settings(t.id, history_turns=3)
    for i in range(5):
        store.add(t.id, "user", f"q{i}")
        store.add(t.id, "helper", f"a{i}")
        store.add(t.id, "system", "note")
    assert [h["text"] for h in store.history_for(t.id)] == ["a3", "q4", "a4"]
    store.settings(t.id, history_turns=0)
    assert store.history_for(t.id) == []


def test_settings_are_validated_with_plain_messages(store):
    t = store.create("k1")
    for kw, msg in (({"title": "  "}, "needs a name"), ({"history_turns": 11}, "between 0 and 10"), ({"history_turns": True}, "between 0 and 10"),
                    ({"budget_cents": -1}, "spending limit"), ({"budget_cents": 10_001}, "spending limit"),
                    ({"shelves": ["Not/A/../Shelf!"]}, "shelf name"), ({"shelves": "note"}, "choose shelves"), ({"include": "n1"}, "not valid")):
        with pytest.raises(ThreadError, match=msg):
            store.settings(t.id, **kw)
    assert store.get(t.id).history_turns == 4  # nothing half-applied


def test_saying_no_to_a_file_beats_saying_yes():
    lens = clean_lens(["note"], ["n1", "n2"], ["n2", "n3"])
    assert lens.include == ["n1"] and lens.exclude == ["n2", "n3"]


def test_forgetting_one_message_removes_only_that_message(store):
    t = store.create("k1")
    a = store.add(t.id, "user", "keep")
    b = store.add(t.id, "user", "forget me")
    store.forget(t.id, b.id)
    assert [m.id for m in store.get(t.id).messages] == [a.id]
    with pytest.raises(ThreadError, match="not in this chat"):
        store.forget(t.id, b.id)


def test_clearing_and_deleting(store):
    t = store.create("k1")
    store.add(t.id, "user", "x")
    store.clear(t.id)
    assert store.get(t.id).messages == []
    store.delete(t.id)
    with pytest.raises(ThreadError, match="does not exist"):
        store.get(t.id)
    with pytest.raises(ThreadError):
        store.delete(t.id)


def test_summaries_list_the_most_recent_chat_first(store):
    a = store.create("k1", "older")
    store.add(a.id, "user", "hello from older")
    b = store.create("k2", "newer")
    store.add(b.id, "user", "later")
    store.add(a.id, "user", "hello from older")
    rows = store.summaries()
    assert [r["title"] for r in rows] == ["older", "newer"] and rows[0]["last"] == "hello from older"


def test_titles_are_trimmed_and_capped(store):
    t = store.create("k1", "  " + "x" * 100)
    assert len(t.title) == 60 and not t.title.startswith(" ")


def test_starting_a_new_chat_removes_blank_ones_but_keeps_chats_with_messages(tmp_path):
    store = ThreadStore(tmp_path / "t.json", clock=lambda: 1.0)
    blank = store.create("k1")
    used = store.create("k1")
    store.add(used.id, "user", "hello")
    fresh = store.create("k2")
    assert blank.id not in store.threads and used.id in store.threads and fresh.id in store.threads
