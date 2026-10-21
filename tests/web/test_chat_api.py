import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from bridge.engine.flowd import ModelReply
from bridge.web import server
from bridge.world import open_world, seed

from conftest import FakeCell, FakeWeb

EX = Path(__file__).resolve().parent.parent.parent / "examples"


class Echo:
    """Answers with the question it was given, so a test can see what reached the helper."""

    def __init__(self):
        self.seen = []

    def complete(self, prompt, inputs):
        self.seen.append(json.dumps(inputs, ensure_ascii=False))
        return ModelReply({"summary": "Answer to: " + str(inputs.get("task", ""))[:60], "risk": "low"}, tokens=1)


@pytest.fixture
def srv(tmp_path):
    world = open_world(tmp_path)
    seed(world, EX / "packs", Echo(), "fixed", cell=FakeCell(), web=FakeWeb(), log=lambda *_: None)
    app = server.App(world, EX / "packs", EX / "vault.json", tmp_path / ".env", cell=FakeCell(), web=FakeWeb())
    model = Echo()
    app.model_factory = lambda: model
    httpd = server.serve(app, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{httpd.server_address[1]}", model
    httpd.shutdown()


def call(url, body=None, token=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None)
    if token:
        req.add_header("X-Bridge-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def key_of(app, pid):
    return next(k for k, r in app.world.registry.records.items() if r.id == pid)


def new_chat(app, url, pid="private-analyst", **kw):
    code, t = call(url + "/api/threads", {"agent_key": key_of(app, pid), **kw}, app.token)
    assert code == 200, t
    return t


def send(app, url, tid, text):
    return call(url + "/api/thread/send", {"id": tid, "text": text}, app.token)


def test_a_chat_keeps_going_over_several_messages_and_the_helper_sees_earlier_turns(srv):
    app, url, model = srv
    t = new_chat(app, url)
    for q in ("Which accounts are at risk?", "And what about Globex?"):
        code, out = send(app, url, t["id"], q)
        assert code == 200 and out["thread"]["messages"][-1]["role"] == "helper"
    msgs = call(url + "/api/thread?id=" + t["id"])[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "helper", "user", "helper"]
    assert "Which accounts are at risk?" in model.seen[-1] and "And what about Globex?" in model.seen[-1]


def test_history_window_of_zero_hides_earlier_turns(srv):
    app, url, model = srv
    t = new_chat(app, url)
    call(url + "/api/thread/settings", {"id": t["id"], "history_turns": 0}, app.token)
    send(app, url, t["id"], "first secret question")
    send(app, url, t["id"], "second question")
    assert "first secret question" not in model.seen[-1]


def test_sending_the_next_message_settles_the_previous_answer(srv):
    app, url, _ = srv
    t = new_chat(app, url)
    _, a = send(app, url, t["id"], "one")
    assert a["thread"]["messages"][-1]["payment"]["state"] == "RESULT_READY"
    _, b = send(app, url, t["id"], "two")
    assert b["thread"]["messages"][1]["payment"]["state"] == "SETTLED"


def test_marking_an_answer_not_helpful_refunds_it(srv):
    app, url, _ = srv
    t = new_chat(app, url)
    _, a = send(app, url, t["id"], "one")
    mid = a["thread"]["messages"][-1]["id"]
    code, v = call(url + "/api/thread/reject", {"id": t["id"], "message_id": mid}, app.token)
    assert code == 200 and v["messages"][-1]["payment"]["state"] == "SETTLED_REJECTED"
    assert call(url + "/api/thread/reject", {"id": t["id"], "message_id": mid}, app.token)[0] == 400


def test_spending_limit_stops_the_next_message_before_it_runs(srv):
    app, url, model = srv
    t = new_chat(app, url)
    price = app.chat._agent(app.threads.get(t["id"]))["price_cents"]
    call(url + "/api/thread/settings", {"id": t["id"], "budget_cents": price}, app.token)
    assert send(app, url, t["id"], "one")[0] == 200
    n = len(model.seen)
    code, out = send(app, url, t["id"], "two")
    assert code == 400 and "spending limit" in out["error"] and len(model.seen) == n
    assert app.threads.get(t["id"]).busy is False


def test_a_busy_chat_refuses_a_second_message_with_409(srv):
    app, url, _ = srv
    t = new_chat(app, url)
    app.threads.get(t["id"]).busy = True
    assert send(app, url, t["id"], "hi")[0] == 409
    app.threads.get(t["id"]).busy = False


def test_bad_messages_are_refused_and_do_not_leave_the_chat_stuck(srv):
    app, url, _ = srv
    t = new_chat(app, url)
    assert send(app, url, t["id"], "   ")[0] == 400
    assert send(app, url, t["id"], "x" * 1001)[0] == 400
    assert send(app, url, "t_nope", "hi")[0] == 400
    assert app.threads.get(t["id"]).busy is False


def test_a_snooping_helper_is_stopped_with_a_plain_message_and_no_charge(srv):
    app, url, _ = srv
    t = new_chat(app, url, pid="friendly-helper")
    code, out = call(url + "/api/thread/send", {"id": t["id"], "text": "anything new?", "simulate": True}, app.token)
    last = out["thread"]["messages"][-1]
    assert code == 200 and last["role"] == "system" and "guard stopped" in last["text"]
    assert last["payment"]["captured"] == 0 and "CANARY" not in json.dumps(out["thread"])


def test_context_preview_shows_shared_locked_files_and_why(srv):
    app, url, _ = srv
    t = new_chat(app, url)
    call(url + "/api/thread/settings", {"id": t["id"], "max_sensitivity": "low"}, app.token)
    vault = app.memory.list()
    held = vault[0]["id"]
    call(url + "/api/thread/settings", {"id": t["id"], "exclude": [held]}, app.token)
    code, ctx = call(url + "/api/thread/context?id=" + t["id"] + "&draft=Acme+renewal")
    assert code == 200
    ids = {s["id"] for s in ctx["shared"]}
    locked = {x["id"]: x["why"] for x in ctx["locked"]}
    assert held not in ids and locked[held] == "You held this one back."
    assert all("text" not in x for x in ctx["locked"]) and ids | set(locked) == {v["id"] for v in vault}


def test_files_used_in_an_answer_are_recorded_and_counted_in_memory(srv):
    app, url, _ = srv
    t = new_chat(app, url)
    _, out = send(app, url, t["id"], "Acme renewal risk")
    used = out["thread"]["messages"][-1]["files"]
    items = {i["id"]: i for i in call(url + "/api/memory")[1]["items"]}
    assert used and all(items[f]["used"]["answers"] == 1 for f in used)


def test_memory_can_be_added_changed_and_deleted_over_http(srv):
    app, url, _ = srv
    code, out = call(url + "/api/memory", {"action": "add", "type": "note", "text": "Prefers Friday calls", "sensitivity": "low"}, app.token)
    assert code == 200
    mid = out["id"]
    assert call(url + "/api/memory", {"action": "update", "id": mid, "text": "Prefers Thursday calls"}, app.token)[0] == 200
    assert call(url + "/api/memory", {"action": "add", "type": "note", "text": "", "sensitivity": "low"}, app.token)[0] == 400
    assert call(url + "/api/memory", {"action": "delete", "id": mid}, app.token)[0] == 200
    assert call(url + "/api/memory", {"action": "delete", "id": mid}, app.token)[0] == 400
    assert call(url + "/api/memory", {"action": "add", "type": "note", "text": "x", "sensitivity": "low"})[0] == 403


def test_deleting_and_clearing_chats(srv):
    app, url, _ = srv
    t = new_chat(app, url)
    send(app, url, t["id"], "hello")
    assert call(url + "/api/thread/clear", {"id": t["id"]}, app.token)[1]["messages"] == []
    assert call(url + "/api/thread/delete", {"id": t["id"]}, app.token)[0] == 200
    assert call(url + "/api/thread?id=" + t["id"])[0] == 404


def test_ipv6_host_forms_are_accepted_and_lookalikes_refused(srv):
    app, url, _ = srv
    for host, ok in (("[::1]:8787", True), ("[::1]", True), ("[::1]evil.com", False), ("[::2]:80", False), ("localhost:9", True)):
        req = urllib.request.Request(url + "/api/state")
        req.add_header("Host", host)
        try:
            code = urllib.request.urlopen(req, timeout=10).status
        except urllib.error.HTTPError as e:
            code = e.code
        assert (code == 200) == ok, host
