"""The earnings view's read-only API: rows for helpers you built, rows for what you bought, totals, plain-word statuses."""
from test_chat_api import call, new_chat, send
from test_chat_api import srv as chat_srv  # noqa: F401  (the fixture, under another name so it can be wrapped)

import pytest


@pytest.fixture
def srv(chat_srv):
    app, url, _model = chat_srv
    return app, url


def ask(app, url, tid, text="Which accounts are at risk?"):
    code, out = send(app, url, tid, text)
    assert code == 200, out
    m = out["thread"]["messages"][-1]
    return m["run_id"], m["id"]


def test_it_is_empty_before_anyone_pays(srv):
    app, url = srv
    code, out = call(url + "/api/earnings")
    assert code == 200 and out["earned"]["rows"] == [] and out["spent"]["rows"] == []
    assert out["earned"]["totals"]["charged"] == 0 and out["test_money"] is True


def test_an_answer_waiting_for_you_is_on_hold_then_paid_when_you_move_on(srv):
    app, url = srv
    t = new_chat(app, url, pid="private-analyst")
    first, _ = ask(app, url, t["id"])
    row = call(url + "/api/earnings")[1]["spent"]["rows"][0]
    assert row["run_id"] == first and row["status"] == "On hold" and row["charged"] == app.ledger.rows[first].floor and row["released"] == 0
    ask(app, url, t["id"], "And what about Globex?")  # sending the next message accepts the previous answer
    out = call(url + "/api/earnings")[1]
    row = next(r for r in out["earned"]["rows"] if r["run_id"] == first)  # the seeded helpers are published with your own key, so they are yours
    assert row["status"] == "Paid" and row["charged"] == row["price"] > 0
    assert row["author_payout"] + row["platform_fee"] == row["charged"] and row["platform_fee"] > 0
    assert row["released"] == row["hold"] - row["charged"] and row["plan"] and row["helper"] == "Private Analyst"
    totals = out["earned"]["totals"]
    assert totals["runs"] == 2 and totals["charged"] == sum(r["charged"] for r in out["earned"]["rows"])


def test_not_helpful_means_deposit_only(srv):
    app, url = srv
    t = new_chat(app, url, pid="private-analyst")
    run, mid = ask(app, url, t["id"])
    assert call(url + "/api/thread/reject", {"id": t["id"], "message_id": mid}, app.token)[0] == 200
    row = call(url + "/api/earnings")[1]["spent"]["rows"][0]
    assert row["status"] == "Deposit only" and row["charged"] == app.ledger.rows[run].floor and row["author_payout"] > 0


def test_it_only_reads(srv):
    app, url = srv
    assert call(url + "/api/earnings", {}, app.token)[0] in (404, 405)
