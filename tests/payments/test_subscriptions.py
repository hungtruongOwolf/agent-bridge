import pytest

from bridge.payments.ledger import Ledger
from bridge.payments.provider import FakeProvider
from bridge.payments.subscriptions import Subscriptions, plan_key


class Rec:
    id, publisher_key = "deal-brief", "ABCDEFGHIJKL"

    class listing:
        included_answers, max_cents = 3, 500


DAY = 86400


@pytest.fixture
def world(tmp_path):
    led = Ledger(FakeProvider(), path=tmp_path / "l.json", holdback_s=0)
    subs = Subscriptions(tmp_path / "s.json")
    return led, subs


def buy(led, subs, run="run-1", now=0.0):
    led.hire(run, "k/deal-brief@1", "author", "you", 500, now)
    subs.register(run, Rec, "you")
    led.start(run, now + 1)
    led.result_ready(run, now + 2)


def test_a_plan_does_not_start_until_the_payment_has_settled(world):
    led, subs = world
    buy(led, subs)
    assert subs.current("you", Rec, led, 10) is None  # the answer is delivered but not yet accepted
    assert subs.listing("you", led, 10)[0]["pending"] is True
    led.accept("run-1", 20)
    a = subs.current("you", Rec, led, 30)
    assert a["left"] == 3 and a["until"] == 20 + 30 * DAY and plan_key(Rec) == "ABCDEFGH/deal-brief"
    assert subs.listing("you", led, 30)[0].get("pending") is None


def test_a_plan_marked_not_helpful_never_starts(world):
    led, subs = world
    buy(led, subs)
    led.reject("run-1", 20)
    assert subs.current("you", Rec, led, 30) is None and subs.listing("you", led, 30) == []


def test_a_plan_is_used_up_by_its_answers_and_then_stops(world):
    led, subs = world
    buy(led, subs)
    led.accept("run-1", 20)
    for left in (3, 2, 1):
        assert subs.current("you", Rec, led, 30)["left"] == left
        subs.use("you", Rec)
    assert subs.current("you", Rec, led, 30) is None  # the allowance is gone
    assert subs.listing("you", led, 30)[0]["running"] is False


def test_a_plan_ends_after_thirty_days_and_never_renews_by_itself(world):
    led, subs = world
    buy(led, subs)
    led.accept("run-1", 20)
    assert subs.current("you", Rec, led, 20 + 30 * DAY - 1) is not None
    assert subs.current("you", Rec, led, 20 + 30 * DAY) is None
    assert led.provider.captured_total() == 500  # one payment, and nothing more was ever taken


def test_a_plan_belongs_to_one_buyer_and_can_be_stopped(world):
    led, subs = world
    buy(led, subs)
    led.accept("run-1", 20)
    assert subs.current("someone-else", Rec, led, 30) is None
    assert subs.cancel("you", plan_key(Rec)) is True and subs.cancel("you", plan_key(Rec)) is False
    assert subs.current("you", Rec, led, 30) is None


def test_plans_survive_a_restart(world, tmp_path):
    led, subs = world
    buy(led, subs)
    led.accept("run-1", 20)
    subs.current("you", Rec, led, 30)
    subs.use("you", Rec)
    again = Subscriptions(tmp_path / "s.json")
    assert again.current("you", Rec, led, 40)["left"] == 2
