"""Tests against a recording fake transport.

These prove the client builds the requests we INTEND from PayPal's documentation. They do not prove PayPal
accepts them: that needs the live sandbox (`bridge paypal-check`), which has not been run yet."""
import base64
import json

import pytest

from bridge.payments.paypal import PayPalSandbox, SANDBOX_BASE, load_paypal_credentials, _money
from bridge.payments.provider import ProviderError


class Recorder:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url, "headers": headers,
                           "body": json.loads(body) if body and headers.get("Content-Type") == "application/json" else body})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


TOKEN = (200, {"access_token": "TOK1"})


def client(*replies, **kw):
    rec = Recorder(TOKEN, *replies)
    return PayPalSandbox("CID", "SECRET", http=rec, **kw), rec


def test_money_formatting():
    assert [_money(c) for c in (1, 40, 100, 1234, 5)] == ["0.01", "0.40", "1.00", "12.34", "0.05"]


def test_refuses_any_host_but_the_sandbox():
    with pytest.raises(ValueError, match="sandbox"):
        PayPalSandbox("a", "b", base_url="https://api-m.paypal.com")
    PayPalSandbox("a", "b", base_url=SANDBOX_BASE + "/")  # trailing slash is fine


def test_token_request_uses_basic_auth_and_is_cached():
    c, rec = client((201, {"id": "O1", "links": [{"rel": "approve", "href": "https://sb/approve/O1"}]}),
                    (201, {"id": "O2", "links": [{"rel": "payer-action", "href": "https://sb/approve/O2"}]}))
    c.authorize(40, "r1", "run-1")
    c.authorize(40, "r2", "run-2")
    tokens = [x for x in rec.calls if x["url"].endswith("/v1/oauth2/token")]
    assert len(tokens) == 1
    assert tokens[0]["headers"]["Authorization"] == "Basic " + base64.b64encode(b"CID:SECRET").decode()
    assert "client_credentials" in tokens[0]["body"].decode()


def test_authorize_creates_an_authorize_order_and_returns_the_approval_link():
    c, rec = client((201, {"id": "ORD9", "links": [{"rel": "self", "href": "x"}, {"rel": "approve", "href": "https://sb/approve/ORD9"}]}))
    a = c.authorize(40, "run-1:authorize", "run-1")
    call = rec.calls[-1]
    assert call["url"] == SANDBOX_BASE + "/v2/checkout/orders" and call["headers"]["PayPal-Request-Id"] == "run-1:authorize"
    assert call["headers"]["Authorization"] == "Bearer TOK1"
    assert call["body"]["intent"] == "AUTHORIZE"
    assert call["body"]["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "0.40"}
    assert (a.auth_id, a.amount, a.approve_url) == ("ORD9", 40, "https://sb/approve/ORD9")


def test_order_without_an_approval_link_is_an_error():
    c, _ = client((201, {"id": "O", "links": []}))
    with pytest.raises(ProviderError, match="approval link"):
        c.authorize(40, "r", "run")


def test_confirm_returns_the_real_authorization_id():
    c, rec = client((201, {"purchase_units": [{"payments": {"authorizations": [{"id": "AUTH7", "amount": {"value": "0.40"}}]}}]}))
    a = c.confirm("ORD9", "run-1:confirm")
    assert rec.calls[-1]["url"].endswith("/v2/checkout/orders/ORD9/authorize") and a.auth_id == "AUTH7" and a.amount == 40


def test_confirm_before_approval_is_a_refusal_not_a_crash():
    c, _ = client((422, {"details": [{"issue": "ORDER_NOT_APPROVED"}]}))
    with pytest.raises(ProviderError, match="ORDER_NOT_APPROVED") as e:
        c.confirm("ORD9", "x")
    assert not e.value.retryable


def test_capture_sends_amount_and_request_id():
    c, rec = client((201, {"id": "CAP1", "status": "COMPLETED"}))
    cap = c.capture("AUTH7", 10, "run-1:capture:floor")
    call = rec.calls[-1]
    assert call["url"].endswith("/v2/payments/authorizations/AUTH7/capture")
    assert call["body"]["amount"]["value"] == "0.10" and call["headers"]["PayPal-Request-Id"] == "run-1:capture:floor"
    assert (cap.capture_id, cap.amount) == ("CAP1", 10)


def test_capture_that_is_not_completed_is_an_error():
    c, _ = client((201, {"id": "CAP1", "status": "DECLINED"}))
    with pytest.raises(ProviderError, match="not completed"):
        c.capture("AUTH7", 10, "r")


def test_void_refund_and_payout_endpoints():
    c, rec = client((204, {}), (201, {}), (201, {"batch_header": {"payout_batch_id": "BATCH1"}}))
    c.void("AUTH7", "v1")
    c.refund("CAP1", "f1")
    assert c.payout("author@example.com", 54, "p1") == "BATCH1"
    urls = [x["url"].replace(SANDBOX_BASE, "") for x in rec.calls[1:]]
    assert urls == ["/v2/payments/authorizations/AUTH7/void", "/v2/payments/captures/CAP1/refund", "/v1/payments/payouts"]
    payout = rec.calls[-1]["body"]
    assert payout["items"][0]["receiver"] == "author@example.com" and payout["items"][0]["amount"] == {"value": "0.54", "currency": "USD"}


def test_payout_needs_an_email():
    c, _ = client()
    with pytest.raises(ProviderError, match="email"):
        c.payout("author-1", 10, "p")


def test_client_errors_are_not_retryable_and_server_errors_are():
    c, _ = client((400, {"name": "INVALID_REQUEST"}), (503, {}), (429, {}))
    with pytest.raises(ProviderError) as e1:
        c.void("A", "1")
    assert not e1.value.retryable
    for _ in range(2):
        with pytest.raises(ProviderError) as e:
            c.void("A", "2")
        assert e.value.retryable


def test_a_network_failure_is_retryable():
    c, _ = client(TimeoutError("slow"))
    with pytest.raises(ProviderError) as e:
        c.void("A", "1")
    assert e.value.retryable


def test_an_expired_token_is_refreshed_once():
    rec = Recorder(TOKEN, (401, {}), (200, {"access_token": "TOK2"}), (204, {}))
    c = PayPalSandbox("CID", "SECRET", http=rec)
    c.void("A", "1")
    assert rec.calls[-1]["headers"]["Authorization"] == "Bearer TOK2"


def test_bad_credentials_are_reported_without_echoing_them():
    c = PayPalSandbox("CID", "TOPSECRET", http=Recorder((401, {"error": "invalid_client"})))
    with pytest.raises(ProviderError) as e:
        c.void("A", "1")
    assert "TOPSECRET" not in str(e.value)


def test_credentials_loader(tmp_path):
    f = tmp_path / ".env"
    f.write_text("PAYPAL_CLIENT_ID=abc\nPAYPAL_CLIENT_SECRET=def\n", encoding="utf-8")
    assert load_paypal_credentials(f) == ("abc", "def")
    f.write_text("PAYPAL_CLIENT_ID=abc\n", encoding="utf-8")
    with pytest.raises(ProviderError):
        load_paypal_credentials(f)
    with pytest.raises(ProviderError):
        load_paypal_credentials(tmp_path / "none.env")
