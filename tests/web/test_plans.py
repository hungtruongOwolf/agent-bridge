"""Every way a helper can charge, end to end: publish with a plan, chat, and check what was held and what was paid."""
import pytest

from test_chat_api import call, new_chat, send
from test_studio import make, post, srv, wait_tested  # noqa: F401  (srv is the fixture)


def publish(app, url, hid, **plan):
    code, out = post(app, url, "/api/studio/publish", {"id": hid, **plan})
    assert code == 200, out
    return wait_tested(app, url, hid)


def budget(app, url, tid, cents=2000):
    assert call(url + "/api/thread/settings", {"id": tid, "budget_cents": cents}, app.token)[0] == 200


def last(out):
    return out["thread"]["messages"][-1]


def test_a_token_plan_charges_for_the_tokens_the_run_used(srv):
    app, url = srv
    make(app, url, "tokens")
    v = publish(app, url, "tokens", plan="per_token", price_usd=0.4, base_usd=0.02, per_1k_tokens_cents=3)
    assert v["plan"] == "per_token" and v["price_text"] == "2¢ + 3¢ per 1,000 tokens, at most 40¢"
    t = new_chat(app, url, pid="tokens", shelves=["note"])
    m = last(send(app, url, t["id"], "Which accounts are at risk?")[1])
    row = app.ledger.rows[m["run_id"]]
    assert row.hold == 40 and 2 <= row.price <= 4  # the model used a handful of tokens: the start plus a cent
    ev = next(x for x in call(url + "/api/payments")[1]["items"] if x["run_id"] == m["run_id"])["events"]
    assert any("it used" in e["why"] and "tokens" in e["why"] and "hold" in e["why"] for e in ev)


def test_a_complexity_plan_prices_the_question_by_what_the_run_did(srv):
    app, url = srv
    make(app, url, "light-bot")
    make(app, url, "web-bot", "web-first")
    plan = dict(plan="complexity", light_cents=10, standard_cents=25, deep_cents=60)
    publish(app, url, "light-bot", **plan)
    publish(app, url, "web-bot", **plan)
    one = new_chat(app, url, pid="light-bot", shelves=["note"])  # a blank chat is replaced by the next new one, so use each before making another
    a = last(send(app, url, one["id"], "Which accounts are at risk?")[1])
    two = new_chat(app, url, pid="web-bot", shelves=["note"])
    b = last(send(app, url, two["id"], "Which accounts are at risk?")[1])
    ra, rb = app.ledger.rows[a["run_id"]], app.ledger.rows[b["run_id"]]
    assert ra.hold == rb.hold == 60  # both held the deepest price
    assert ra.price == 10 and rb.price == 25  # one thought once; the other also looked something up on the web
    ev = next(x for x in call(url + "/api/payments")[1]["items"] if x["run_id"] == b["run_id"])["events"]
    assert any("Standard: 1 thinking step, 1 web lookup" in e["why"] for e in ev)


def test_a_monthly_plan_is_paid_once_and_the_next_answers_are_included(srv):
    app, url = srv
    make(app, url, "monthly")
    v = publish(app, url, "monthly", plan="monthly", monthly_usd=5, included_answers=2)
    assert v["price_text"] == "$5.00 a month, up to 2 answers, no automatic renewal"
    t = new_chat(app, url, pid="monthly", shelves=["note"])
    budget(app, url, t["id"])
    first = last(send(app, url, t["id"], "Which accounts are at risk?")[1])
    assert app.ledger.rows[first["run_id"]].price == 500 and first["payment"]["state"] == "RESULT_READY"
    assert call(url + "/api/thread?id=" + t["id"])[1]["agent"]["plan_status"] is None  # not started yet: the payment is not settled
    second = last(send(app, url, t["id"], "And which one is the biggest?")[1])  # sending again accepts the first answer and starts the plan
    assert second["payment"]["state"] == "COVERED" and second["price"] == 0 and second["run_id"] not in app.ledger.rows
    assert len(app.ledger.rows) == 1 and app.ledger.rows[first["run_id"]].state == "SETTLED"
    status = call(url + "/api/thread?id=" + t["id"])[1]["agent"]["plan_status"]
    assert status["left"] == 1 and status["included"] == 2
    third = last(send(app, url, t["id"], "What about Hooli?")[1])
    assert third["payment"]["state"] == "COVERED" and len(app.ledger.rows) == 1
    assert call(url + "/api/thread?id=" + t["id"])[1]["agent"]["plan_status"] is None  # the two answers are used up
    plans = call(url + "/api/payments")[1]["plans"]
    assert plans[0]["helper"] == "Monthly" and plans[0]["left"] == 0 and plans[0]["running"] is False
    fourth = send(app, url, t["id"], "One more?")[1]  # the plan has run out, so this is a new purchase and needs a hold
    assert len(app.ledger.rows) == 2 and last(fourth)["payment"]["state"] == "RESULT_READY"
    assert app.ledger.provider.captured_total() == 500 + 125  # the first month paid in full, the second purchase only its deposit so far


def test_a_plan_whose_first_answer_was_not_helpful_never_starts(srv):
    app, url = srv
    make(app, url, "monthly2")
    publish(app, url, "monthly2", plan="monthly", monthly_usd=5, included_answers=5)
    t = new_chat(app, url, pid="monthly2", shelves=["note"])
    budget(app, url, t["id"])
    first = last(send(app, url, t["id"], "Which accounts are at risk?")[1])
    assert call(url + "/api/thread/reject", {"id": t["id"], "message_id": first["id"]}, app.token)[0] == 200
    second = last(send(app, url, t["id"], "Try again please")[1])
    assert second["payment"]["state"] == "RESULT_READY" and len(app.ledger.rows) == 2  # a fresh purchase, not an included answer
    assert call(url + "/api/payments")[1]["plans"][0]["pending"] is True


def test_a_plan_can_be_stopped_by_the_buyer(srv):
    app, url = srv
    make(app, url, "monthly3")
    publish(app, url, "monthly3", plan="monthly", monthly_usd=5, included_answers=5)
    t = new_chat(app, url, pid="monthly3", shelves=["note"])
    budget(app, url, t["id"])
    send(app, url, t["id"], "Which accounts are at risk?")
    send(app, url, t["id"], "And Globex?")
    plan = call(url + "/api/payments")[1]["plans"][0]
    assert plan["running"] and plan["left"] == 4
    assert call(url + "/api/subscription/cancel", {"key": plan["key"]}, app.token)[1] == {"cancelled": True}
    assert call(url + "/api/subscription/cancel", {"key": plan["key"]}, app.token)[1] == {"cancelled": False}
    assert call(url + "/api/payments")[1]["plans"] == []
    assert call(url + "/api/subscription/cancel", {"key": plan["key"]})[0] == 403  # needs the page's token


def test_changing_the_plan_of_a_published_version(srv):
    app, url = srv
    make(app, url, "switch")
    v = publish(app, url, "switch", plan="flat", price_usd=0.2)
    assert v["price_text"] == "20¢ per answer"
    for body, text in (({"plan": "per_file", "price_usd": 0.5, "base_usd": 0.05, "per_file_cents": 5}, "5¢ + 5¢ per file it reads, at most 50¢"),
                       ({"plan": "complexity", "light_cents": 5, "standard_cents": 10, "deep_cents": 30}, "5¢ light, 10¢ standard, 30¢ deep"),
                       ({"plan": "monthly", "monthly_usd": 3, "included_answers": 20}, "$3.00 a month, up to 20 answers, no automatic renewal")):
        assert post(app, url, "/api/studio/price", {"key": v["key"], **body})[0] == 200
        assert call(url + "/api/studio/helper?id=switch")[1]["versions"][0]["price_text"] == text
    assert post(app, url, "/api/studio/price", {"key": v["key"], "plan": "complexity", "light_cents": 9, "standard_cents": 5, "deep_cents": 30})[0] == 400
