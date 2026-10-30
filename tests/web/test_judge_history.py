"""Every judge-mode visitor starts with a sample past made by the real services from a fixed clock, and gets a private copy of it."""
import time

import pytest

from bridge.web.judge import JudgeConfig, JudgeHub
from bridge.web.routes.earnings import earnings

NOW = time.time()  # fixed once: the story is told relative to it, and its newest answer must still be inside its 48 hour window
DAY = 86400


@pytest.fixture(scope="module")
def hub(tmp_path_factory):
    return JudgeHub(JudgeConfig(root=tmp_path_factory.mktemp("hist"), clock=lambda: NOW))


def rows(app):
    e = earnings(app)
    return e["earned"]["rows"], e["spent"]["rows"]


def test_new_visitor_lands_in_a_lived_in_console(hub):
    _, v = hub.create("1.1.1.1")
    earned, spent = rows(v.app)
    assert [r["status"] for r in spent].count("Paid") == 7
    by = {s: [r for r in spent if r["status"] == s] for s in {r["status"] for r in spent}}
    assert len(by["Deposit only"]) == 1 and len(by["Refunded"]) == 1 and len(by["On hold"]) == 1
    assert {r["charged"] for r in spent if r["status"] == "Paid" and r["helper"] == "Meeting Digest"} == {10, 25}  # light and standard
    assert by["Refunded"][0]["charged"] == 0 and by["Refunded"][0]["helper"] == "Friendly Helper"
    assert len(spent) == 10 and len(v.app.threads.threads) == 6
    titles = {t.title for t in v.app.threads.threads.values()}
    assert {"Weekly account review", "What did I agree in meetings?", "Quick check on Globex"} <= titles
    # the Written-from-N-files data is there
    assert all(m.files for t in v.app.threads.threads.values() for m in t.messages if m.role == "helper")


def test_helpers_i_built_were_bought_by_other_buyers_with_different_outcomes(hub):
    _, v = hub.create("1.1.1.2")
    earned, _ = rows(v.app)
    assert {r["helper"] for r in earned} == {"Meeting Digest"} and {r["plan"] for r in earned} == {"By effort"}
    other = [v.app.ledger.rows[r["run_id"]] for r in earned if v.app.ledger.rows[r["run_id"]].requester != "you"]
    assert len({r.requester for r in other}) >= 3 and len(other) >= 5
    assert {"Paid", "Deposit only"} <= {r["status"] for r in earned}
    assert earned and all(r["author_payout"] > 0 for r in earned)
    days = {int((NOW - r["when"]) // DAY) for r in earned}
    assert len(days) >= 5  # spread over the last days, so the chart has several bars


def test_the_past_is_spread_over_ten_days_and_nothing_is_in_the_future(hub):
    _, v = hub.create("1.1.1.3")
    whens = [r["when"] for r in rows(v.app)[1]]
    assert max(whens) <= NOW and NOW - min(whens) < 10 * DAY and NOW - min(whens) > 8 * DAY


def test_it_is_the_same_every_time(tmp_path):
    a = JudgeHub(JudgeConfig(root=tmp_path / "a", clock=lambda: NOW))
    b = JudgeHub(JudgeConfig(root=tmp_path / "b", clock=lambda: NOW))
    shape = lambda h: [(r["helper"], r["status"], r["charged"], r["hold"]) for r in sorted(rows(h.create("2.2.2.2")[1].app)[1], key=lambda r: r["when"])]
    assert shape(a) == shape(b)


def test_visitors_get_independent_copies(hub):
    _, a = hub.create("3.3.3.1")
    _, b = hub.create("3.3.3.2")
    before = len(rows(b.app)[1])
    t = a.app.chat.create({"agent_key": next(r.key for r in a.app.world.registry.installable() if r.id == "quick-skim"), "title": "mine", "shelves": ["work/accounts/globex"]})
    assert len(a.app.threads.threads) == 7 and len(b.app.threads.threads) == 6
    a.app.ledger.rows[next(iter(a.app.ledger.rows))].price += 1
    assert len(rows(b.app)[1]) == before and a.dir != b.dir and t["id"] not in b.app.threads.threads
    assert a.app.world.registry.path != b.app.world.registry.path


def test_a_new_visitor_is_created_in_under_two_seconds(hub):
    start = time.perf_counter()
    hub.create("4.4.4.4")
    assert time.perf_counter() - start < 2.0


def test_the_template_is_rebuilt_when_old(tmp_path):
    clock = [NOW]
    hub = JudgeHub(JudgeConfig(root=tmp_path, clock=lambda: clock[0], history_max_age_s=3600))
    first = hub.seed_dir
    clock[0] += 2 * 3600
    hub.create("5.5.5.5")
    assert hub.seed_dir != first and not first.exists()


def test_history_can_be_switched_off(tmp_path):
    hub = JudgeHub(JudgeConfig(root=tmp_path, history=False))
    _, v = hub.create("6.6.6.6")
    assert rows(v.app) == ([], []) and not v.app.threads.threads


def test_the_wallet_counts_only_the_visitors_own_payments(hub):
    _, v = hub.create("7.7.7.7")
    spent = rows(v.app)[1]
    pay = v.app.payments.summary()
    assert pay["captured"] == sum(r["charged"] for r in spent)  # not what other buyers paid for the visitor's helper
    assert pay["on_hold"] == sum(r["price"] - r["charged"] for r in spent if r["status"] == "On hold")
    assert len(v.app.payments.receipts()["items"]) == len(spent)
