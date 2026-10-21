import threading

import pytest

from bridge.payments.ledger import Ledger, PendingError, StateError
from bridge.payments.provider import FakeProvider, ProviderError

PRICE, FLOOR = 100, 25  # cents; floor is 25% of the price (a proposal)


def ledger(**kw):
    p = kw.pop("provider", None) or FakeProvider()
    return Ledger(p, **kw), p


def hire(l, run="run-1", now=0.0, **kw):
    return l.hire(run, "pack@1", "author-1", "req-1", PRICE, now, **kw)


def ready(l, run="run-1"):
    hire(l, run)
    l.start(run, 1)
    return l.result_ready(run, 2)


def test_happy_path_captures_floor_then_outcome_and_pays_once():
    l, p = ledger()
    ready(l)
    assert l.rows["run-1"].state == "RESULT_READY" and p.captured_total() == FLOOR
    l.accept("run-1", 3)
    assert l.rows["run-1"].state == "SETTLED" and p.captured_total() == PRICE
    assert l.release_payouts(4) == 1 and l.release_payouts(5) == 0
    assert p.paid_total() == 90  # 100 minus a 10% platform fee
    assert l.summary() == {"captured": 100, "paid_out": 90, "pending_payout": 0, "held": 0}


def test_reject_keeps_only_the_floor_and_releases_the_rest():
    l, p = ledger()
    ready(l)
    l.reject("run-1", 3, "wrong answer")
    row = l.rows["run-1"]
    assert row.state == "SETTLED_REJECTED" and p.captured_total() == FLOOR and row.voided
    l.release_payouts(4)
    assert p.paid_total() == 23  # 25 minus 10% fee, integer cents


def test_kill_during_the_run_holds_the_money_and_pays_nobody():
    l, p = ledger()
    hire(l)
    l.start("run-1", 1)
    l.kill("run-1", 2, "SANDBOX_NETWORK")
    assert l.rows["run-1"].state == "DISPUTE_HOLD" and p.captured_total() == 0
    assert l.summary()["held"] == 100 and l.release_payouts(99) == 0


def test_claim_upheld_refunds_everything_and_pays_the_author_nothing():
    l, p = ledger()
    ready(l)  # floor already captured when the late detector fires
    l.kill("run-1", 3, "CANARY_HIT")
    l.adjudicate("run-1", upheld=True, now=4)
    row = l.rows["run-1"]
    assert row.state == "DISPUTE_UPHELD" and p.captured_total() == 0 and row.voided
    assert l.release_payouts(5) == 0 and p.paid_total() == 0


def test_claim_rejected_pays_the_author_the_floor():
    l, p = ledger()
    hire(l)
    l.start("run-1", 1)
    l.kill("run-1", 2, "forged claim")
    l.adjudicate("run-1", upheld=False, now=3)
    assert l.rows["run-1"].state == "SETTLED_REJECTED" and p.captured_total() == FLOOR
    l.release_payouts(4)
    assert p.paid_total() == 23


def test_infrastructure_failure_voids_with_no_charge():
    l, p = ledger()
    hire(l)
    l.start("run-1", 1)
    l.fail_infra("run-1", 2)
    assert l.rows["run-1"].state == "VOIDED" and p.captured_total() == 0 and l.rows["run-1"].voided


def test_silence_after_start_captures_the_floor_then_auto_accepts():
    l, p = ledger()
    hire(l, accept_window_s=100)
    l.start("run-1", 0, run_deadline_s=50)
    assert l.tick(49) == []
    assert l.tick(50) == [("run-1", "silence: floor captured")]
    assert l.rows["run-1"].state == "RESULT_READY" and p.captured_total() == FLOOR
    assert l.tick(149) == []
    assert l.tick(150) == [("run-1", "auto-accepted")]
    assert l.rows["run-1"].state == "SETTLED" and p.captured_total() == PRICE


def test_no_decision_before_the_deadline_auto_accepts():
    l, p = ledger()
    hire(l, accept_window_s=10)
    l.start("run-1", 0)
    l.result_ready("run-1", 1)
    l.tick(11)
    assert l.rows["run-1"].state == "SETTLED" and "auto-accept" in l.rows["run-1"].events[-1]["why"]


def test_accept_versus_kill_race_has_exactly_one_winner():
    for i in range(40):
        l, p = ledger()
        ready(l)
        results = {}

        def go(name, fn):
            try:
                fn()
                results[name] = "ok"
            except StateError:
                results[name] = "refused"

        ts = [threading.Thread(target=go, args=("accept", lambda: l.accept("run-1", 3))),
              threading.Thread(target=go, args=("kill", lambda: l.kill("run-1", 3, "claim")))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert sorted(results.values()) == ["ok", "refused"], results
        state = l.rows["run-1"].state
        assert (state, p.captured_total()) in {("SETTLED", PRICE), ("DISPUTE_HOLD", FLOOR)}


def test_hiring_twice_is_one_hire():
    l, p = ledger()
    a, b = hire(l), hire(l)
    assert a is b and len(p.auths) == 1


def test_guards_on_hire():
    l, _ = ledger()
    with pytest.raises(StateError, match="own pack"):
        l.hire("r", "pack", "same", "same", 100, 0)
    with pytest.raises(StateError, match="positive"):
        l.hire("r", "pack", "a", "b", 0, 0)


def test_transitions_are_only_allowed_from_the_right_state():
    l, _ = ledger()
    hire(l)
    with pytest.raises(StateError):
        l.accept("run-1", 1)  # nothing to accept yet
    l.start("run-1", 1)
    with pytest.raises(StateError):
        l.start("run-1", 2)
    l.result_ready("run-1", 3)
    l.accept("run-1", 4)
    for op in (lambda: l.accept("run-1", 5), lambda: l.reject("run-1", 5), lambda: l.kill("run-1", 5, "x"),
               lambda: l.fail_infra("run-1", 5)):
        with pytest.raises(StateError):
            op()
    with pytest.raises(StateError, match="unknown"):
        l.accept("nope", 1)


def test_declined_floor_capture_leaves_the_run_running():
    l, p = ledger()
    hire(l)
    l.start("run-1", 1)
    p.decline_capture = True
    with pytest.raises(ProviderError):
        l.result_ready("run-1", 2)
    assert l.rows["run-1"].state == "RUNNING" and p.captured_total() == 0


def test_declined_outcome_capture_leaves_the_result_waiting():
    l, p = ledger()
    ready(l)
    p.decline_capture = True
    with pytest.raises(ProviderError):
        l.accept("run-1", 3)
    assert l.rows["run-1"].state == "RESULT_READY" and p.captured_total() == FLOOR
    p.decline_capture = False
    l.accept("run-1", 4)
    assert p.captured_total() == PRICE


def test_a_lost_capture_reply_is_recovered_with_exactly_one_charge():
    p = FakeProvider(lose_response_once={"capture"})
    l = Ledger(p, retries=1)
    hire(l)
    l.start("run-1", 1)
    with pytest.raises(PendingError):
        l.result_ready("run-1", 2)
    row = l.rows["run-1"]
    assert row.state == "RESULT_READY" and row.intent and row.accept_by is not None
    assert l.recover(3) == ["run-1:capture:floor"]
    assert p.captured_total() == FLOOR and row.intent is None and len(row.captures) == 1


def test_automatic_retry_hides_a_single_lost_reply():
    p = FakeProvider(lose_response_once={"capture"})
    l = Ledger(p, retries=3)
    hire(l)
    l.start("run-1", 1)
    l.result_ready("run-1", 2)
    assert p.captured_total() == FLOOR and len(l.rows["run-1"].captures) == 1


def test_a_lost_outcome_reply_still_settles_once_after_recovery():
    p = FakeProvider()
    l = Ledger(p, retries=1)
    ready(l)
    p.lose_response_once.add("capture")
    with pytest.raises(PendingError):
        l.accept("run-1", 3)
    assert l.rows["run-1"].state == "SETTLED"
    l.recover(4)
    l.release_payouts(5)
    assert p.captured_total() == PRICE and p.paid_total() == 90 and l.rows["run-1"].voided is False


def test_restart_mid_payout_pays_exactly_once(tmp_path):
    path = tmp_path / "ledger.json"
    p = FakeProvider()
    l = Ledger(p, path=path, retries=1)
    ready(l)
    l.accept("run-1", 3)
    p.lose_response_once.add("payout")
    with pytest.raises(PendingError):
        l.release_payouts(4)  # the provider paid, the reply was lost, the process "dies" here
    l2 = Ledger(p, path=path, retries=3)  # a restarted hub reloads the saved row
    assert l2.rows["run-1"].intent == {"op": "payout"}
    l2.recover(5)
    l2.release_payouts(6)
    l2.release_payouts(7)
    assert p.paid_total() == 90 and len(p.payouts) == 1


def test_holdback_delays_the_payout():
    l, p = ledger(holdback_s=100)
    ready(l)
    l.accept("run-1", 10)
    assert l.release_payouts(50) == 0 and p.paid_total() == 0
    assert l.release_payouts(110) == 1 and p.paid_total() == 90


def test_dispute_overdue_is_noted_once_and_money_stays_held():
    l, p = ledger()
    hire(l)
    l.start("run-1", 0)
    l.kill("run-1", 1, "claim", dispute_window_s=10)
    assert l.tick(11) == [("run-1", "dispute overdue")] and l.tick(12) == []
    assert l.rows["run-1"].state == "DISPUTE_HOLD" and l.summary()["held"] == 100


def test_state_survives_a_restart(tmp_path):
    path = tmp_path / "ledger.json"
    l = Ledger(FakeProvider(), path=path)
    ready(l)
    again = Ledger(l.provider, path=path)
    assert again.rows["run-1"].state == "RESULT_READY" and again.rows["run-1"].captures[0]["amount"] == FLOOR
    again.accept("run-1", 3)
    assert again.rows["run-1"].state == "SETTLED"


def test_money_conservation_across_many_outcomes():
    l, p = ledger()
    for i, outcome in enumerate(["accept", "reject", "kill-up", "kill-rej", "infra"]):
        run = f"r{i}"
        hire(l, run)
        l.start(run, 1)
        if outcome == "infra":
            l.fail_infra(run, 2)
            continue
        if outcome.startswith("kill"):
            l.kill(run, 2, "claim")
            l.adjudicate(run, upheld=outcome == "kill-up", now=3)
        else:
            l.result_ready(run, 2)
            l.accept(run, 3) if outcome == "accept" else l.reject(run, 3)
    l.release_payouts(10)
    s = l.summary()
    assert s["captured"] == p.captured_total() == 100 + 25 + 25  # accept + reject + kill-rej floors
    assert p.paid_total() == 90 + 23 + 23 and s["paid_out"] == p.paid_total()
    assert p.paid_total() <= s["captured"]


# ---- buyer approval (PayPal-style: no hold exists until the buyer approves on the provider's page) ----

def approving_ledger(**kw):
    p = FakeProvider(require_approval=True)
    return Ledger(p, **kw), p


def test_hire_waits_for_the_buyer_and_starts_nothing_until_approved():
    l, p = approving_ledger()
    row = hire(l)
    assert row.state == "AWAITING_APPROVAL" and row.approve_url.startswith("https://sandbox.fake/approve/")
    with pytest.raises(StateError):
        l.start("run-1", 1)
    assert p.captured_total() == 0


def test_confirming_before_the_buyer_approves_is_refused_and_leaves_the_state_alone():
    l, p = approving_ledger()
    hire(l)
    with pytest.raises(ProviderError, match="not approved"):
        l.confirm_approval("run-1", 1)
    assert l.rows["run-1"].state == "AWAITING_APPROVAL"


def test_after_approval_the_normal_flow_runs():
    l, p = approving_ledger()
    row = hire(l)
    p.buyer_approves(row.auth_id)
    assert l.confirm_approval("run-1", 1).state == "AUTHORIZED"
    l.start("run-1", 2)
    l.result_ready("run-1", 3)
    l.accept("run-1", 4)
    assert p.captured_total() == PRICE


def test_an_unapproved_hold_can_never_be_captured():
    l, p = approving_ledger()
    row = hire(l)
    with pytest.raises(ProviderError, match="never approved"):
        p.capture(row.auth_id, 10, "c")


def test_approval_expires_and_nothing_is_charged_or_voided():
    l, p = approving_ledger()
    hire(l, now=0)
    assert l.tick(899) == [] and l.tick(900) == [("run-1", "approval expired")]
    assert l.rows["run-1"].state == "VOIDED" and p.captured_total() == 0 and not l.rows["run-1"].voided


def test_giving_up_before_approving_is_free():
    l, p = approving_ledger()
    hire(l)
    l.fail_infra("run-1", 1, "buyer closed the page")
    assert l.rows["run-1"].state == "VOIDED" and ("void", "run-1:void") not in p.calls


def test_a_refused_payout_stays_owed_and_is_retried_later():
    class Refusing(FakeProvider):
        refuse = True

        def payout(self, to, amount, request_id):
            if self.refuse:
                raise ProviderError("receiver cannot be paid")
            return super().payout(to, amount, request_id)

    p = Refusing()
    l = Ledger(p)
    ready(l)
    l.accept("run-1", 3)
    assert l.release_payouts(4) == 0
    pay = l.rows["run-1"].payout
    assert pay["status"] == "failed" and "cannot be paid" in pay["error"]
    p.refuse = False
    pay["status"] = "pending"  # an operator re-queues it after fixing the destination
    assert l.release_payouts(5) == 1 and p.paid_total() == 90


# ---- metered helpers: the hold is the most it can cost, the price is what was read ---------------------------

def test_a_run_can_be_priced_below_the_hold_and_the_rest_goes_back():
    l, p = ledger()
    hire(l)
    l.start("run-1", 1)
    row = l.reprice("run-1", 40, 1.5)
    assert row.price == 40 and row.floor == 10 and row.hold == PRICE
    l.result_ready("run-1", 2)
    assert p.captured_total() == 10
    l.accept("run-1", 3)
    assert p.captured_total() == 40 and l.rows["run-1"].state == "SETTLED"
    assert any(op == "void" for op, _ in p.calls)  # the unused part of the hold was released
    l.release_payouts(4)
    assert p.paid_total() == 36  # 40 less the 10% platform fee
    assert "40¢ of the 100¢ hold" in l.rows["run-1"].events[-3]["why"] or any("40¢ of the 100¢ hold" in e["why"] for e in l.rows["run-1"].events)


def test_a_rejected_metered_run_still_releases_the_whole_unused_hold():
    l, p = ledger()
    hire(l)
    l.start("run-1", 1)
    l.reprice("run-1", 40, 1.5)
    l.result_ready("run-1", 2)
    l.reject("run-1", 3)
    assert p.captured_total() == 10 and any(op == "void" for op, _ in p.calls)


@pytest.mark.parametrize("amount", [0, -5, 101, 1.5, True, "40"])
def test_a_run_cannot_be_priced_above_its_hold_or_nonsensically(amount):
    l, _ = ledger()
    hire(l)
    l.start("run-1", 1)
    with pytest.raises(StateError):
        l.reprice("run-1", amount, 2)


def test_only_a_run_that_is_under_way_can_be_repriced():
    l, _ = ledger()
    hire(l)
    with pytest.raises(StateError, match="AUTHORIZED"):
        l.reprice("run-1", 40, 1)
    l.start("run-1", 1)
    l.result_ready("run-1", 2)
    with pytest.raises(StateError, match="RESULT_READY"):
        l.reprice("run-1", 40, 3)


def test_old_ledger_rows_without_a_hold_still_settle(tmp_path):
    l, p = ledger(path=tmp_path / "l.json")
    ready(l)
    import json
    raw = json.loads((tmp_path / "l.json").read_text())
    for r in raw:
        r.pop("hold")
    (tmp_path / "l.json").write_text(json.dumps(raw))
    l2 = Ledger(p, path=tmp_path / "l.json")
    l2.accept("run-1", 3)
    assert p.captured_total() == PRICE
