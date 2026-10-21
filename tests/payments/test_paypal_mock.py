"""The real PayPal client, run against the local practice server. This checks our client code and the approval flow end to end.
It says nothing about whether the live sandbox agrees: that needs `bridge paypal-check` with real credentials."""
import threading
import urllib.request

import pytest

from bridge.payments.ledger import Ledger
from bridge.payments.paypal import PayPalSandbox
from bridge.payments.paypal_mock import MOCK_ID, MOCK_SECRET, serve_mock
from bridge.payments.provider import ProviderError


@pytest.fixture
def mock(tmp_path):
    httpd, api = serve_mock(0, tmp_path / "mock.json")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield api
    httpd.shutdown()


def client(api, **kw):
    return PayPalSandbox(MOCK_ID, MOCK_SECRET, base_url=api.base, return_url="http://127.0.0.1:8787/paypal/return",
                         cancel_url="http://127.0.0.1:8787/paypal/cancel", **kw)


def approve(api, auth):
    return api.approve(auth.auth_id)


def test_the_client_only_talks_to_the_sandbox_or_this_computer():
    for bad in ("https://api-m.paypal.com", "http://example.com:8000", "http://127.0.0.1.evil.com:80", "http://127.0.0.1"):
        with pytest.raises(ValueError):
            PayPalSandbox("a", "b", base_url=bad)
    PayPalSandbox("a", "b", base_url="http://127.0.0.1:9797")


def test_wrong_credentials_are_refused_in_plain_words(mock):
    with pytest.raises(ProviderError, match="rejected the sandbox credentials"):
        PayPalSandbox("nope", "nope", base_url=mock.base).authorize(100, "r1", "run-1")


def test_a_hold_needs_the_buyer_before_it_exists(mock):
    c = client(mock)
    a = c.authorize(100, "r1", "run-1")
    assert a.approve_url.startswith(mock.base + "/checkoutnow?token=") and a.amount == 100
    with pytest.raises(ProviderError, match="not approved"):
        c.confirm(a.auth_id, "c1")
    back = approve(mock, a)
    assert back.startswith("http://127.0.0.1:8787/paypal/return?token=")
    hold = c.confirm(a.auth_id, "c1")
    assert hold.auth_id.startswith("AUTH-") and hold.amount == 100
    assert c.confirm(a.auth_id, "c1") == hold  # the same request id gives the same answer


def test_the_whole_life_of_a_payment(mock):
    c = client(mock)
    a = c.authorize(60, "r1", "run-1")
    approve(mock, a)
    hold = c.confirm(a.auth_id, "c1")
    floor = c.capture(hold.auth_id, 15, "cap1")
    assert c.capture(hold.auth_id, 15, "cap1") == floor  # a lost reply can be retried without charging twice
    rest = c.capture(hold.auth_id, 45, "cap2")
    with pytest.raises(ProviderError, match="AUTHORIZATION_AMOUNT_EXCEEDED"):
        c.capture(hold.auth_id, 1, "cap3")
    c.refund(rest.capture_id, "ref1")
    with pytest.raises(ProviderError, match="CAPTURE_FULLY_REFUNDED"):
        c.refund(rest.capture_id, "ref2")
    batch = c.payout("author@example.com", 13, "pay1")
    assert c.payout("author@example.com", 13, "pay1") == batch
    t = mock.s.totals()
    assert t == {"held": 0, "captured": 15, "refunded": 45, "paid_out": 13}


def test_a_voided_hold_cannot_be_captured(mock):
    c = client(mock)
    a = c.authorize(40, "r1", "run-1")
    approve(mock, a)
    hold = c.confirm(a.auth_id, "c1")
    c.void(hold.auth_id, "v1")
    with pytest.raises(ProviderError, match="AUTHORIZATION_VOIDED"):
        c.capture(hold.auth_id, 10, "cap1")


def test_a_payout_needs_an_email(mock):
    with pytest.raises(ProviderError, match="email"):
        client(mock).payout("not-an-email", 10, "p1")


def test_a_cancelled_hold_is_never_confirmed(mock):
    c = client(mock)
    a = c.authorize(40, "r1", "run-1")
    assert mock.cancel(a.auth_id) == "http://127.0.0.1:8787/paypal/cancel"
    with pytest.raises(ProviderError, match="not approved"):
        c.confirm(a.auth_id, "c1")


def test_the_approval_page_and_the_dashboard_are_labelled_as_practice(mock):
    a = client(mock).authorize(125, "r1", "run-1")
    page = urllib.request.urlopen(a.approve_url).read().decode()
    assert "Practice server" in page and "$1.25" in page and "No real money" in page
    assert "Practice PayPal" in urllib.request.urlopen(mock.base + "/mock/state").read().decode()


def test_state_survives_a_restart_of_the_practice_server(mock, tmp_path):
    c = client(mock)
    a = c.authorize(50, "r1", "run-1")
    approve(mock, a)
    hold = c.confirm(a.auth_id, "c1")
    c.capture(hold.auth_id, 20, "cap1")
    httpd2, api2 = serve_mock(0, tmp_path / "mock.json")
    assert api2.s.totals()["captured"] == 20 and api2.s.new_id("X") not in api2.s.orders


def test_the_ledger_pays_an_author_through_the_practice_server(mock, tmp_path):
    ledger = Ledger(client(mock), path=tmp_path / "ledger.json", holdback_s=0)
    row = ledger.hire("run-1", "k/pack@1", "author@example.com", "you", 60, 1000.0)
    assert row.state == "AWAITING_APPROVAL" and row.approve_url.startswith(mock.base)
    approve(mock, type("A", (), {"auth_id": row.auth_id}))
    ledger.confirm_approval("run-1", 1001.0)
    ledger.start("run-1", 1002.0)
    ledger.result_ready("run-1", 1003.0)
    ledger.accept("run-1", 1004.0)
    ledger.release_payouts(1005.0)
    t = mock.s.totals()
    assert t["captured"] == 60 and t["paid_out"] == 54 and t["held"] == 0  # the author gets the price less the 10 percent fee
    assert ledger.rows["run-1"].payout["status"] == "paid"
