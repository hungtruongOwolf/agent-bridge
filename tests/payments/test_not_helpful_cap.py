from bridge.payments.ledger import NOT_HELPFUL_LIMIT_MESSAGE, NOT_HELPFUL_MAX, NOT_HELPFUL_WINDOW_S, Ledger, NotHelpfulLimit, StateError
from bridge.payments.provider import FakeProvider


def run_to_ready(l, n, now, pack="deal-brief@1.0", req="req-1"):
    rid = f"run-{n}"
    l.hire(rid, pack, "author-1", req, 100, now)
    l.start(rid, now + 1)
    l.result_ready(rid, now + 2)
    return rid


def use_up(l, now=1000.0):
    for i in range(NOT_HELPFUL_MAX):
        l.reject(run_to_ready(l, i, now), now + 3)


def test_sixth_press_is_refused_and_the_run_stays_open():
    l = Ledger(FakeProvider())
    use_up(l)
    rid = run_to_ready(l, 99, 1100.0)
    try:
        l.reject(rid, 1103.0)
        assert False
    except NotHelpfulLimit as e:
        assert str(e) == NOT_HELPFUL_LIMIT_MESSAGE and isinstance(e, StateError)
    assert l.rows[rid].state == "RESULT_READY"
    l.accept(rid, 1104.0)  # the buyer can still keep the answer; the author is paid in full
    assert l.rows[rid].state == "SETTLED"


def test_other_helper_and_other_buyer_are_not_limited():
    l = Ledger(FakeProvider())
    use_up(l)
    l.reject(run_to_ready(l, 50, 1100.0, pack="other@1.0"), 1105.0)
    l.reject(run_to_ready(l, 51, 1100.0, req="req-2"), 1105.0)


def test_version_of_same_helper_counts_together():
    l = Ledger(FakeProvider())
    use_up(l)
    rid = run_to_ready(l, 60, 1100.0, pack="deal-brief@2.0")
    try:
        l.reject(rid, 1105.0)
        assert False
    except NotHelpfulLimit:
        pass


def test_window_slides_with_the_injected_clock():
    l = Ledger(FakeProvider())
    use_up(l, now=1000.0)
    later = 1003.0 + NOT_HELPFUL_WINDOW_S + 1
    rid = run_to_ready(l, 70, later)
    l.reject(rid, later + 3)
    assert l.rows[rid].state == "SETTLED_REJECTED"


def test_limit_survives_a_restart(tmp_path):
    p = tmp_path / "ledger.json"
    l = Ledger(FakeProvider(), path=p)
    use_up(l)
    l2 = Ledger(FakeProvider(), path=p)
    rid = run_to_ready(l2, 80, 1100.0)
    try:
        l2.reject(rid, 1105.0)
        assert False
    except NotHelpfulLimit:
        pass


def test_a_rejected_dispute_does_not_count_as_a_press():
    l = Ledger(FakeProvider())
    rid = run_to_ready(l, 1, 1000.0)
    l.kill(rid, 1003.0, "claim")
    l.adjudicate(rid, False, 1004.0)
    assert l.not_helpful_count("req-1", "deal-brief@1.0", 1005.0) == 0
