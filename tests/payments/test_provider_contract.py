"""Contract every payment provider must satisfy. Runs against the fake now; the PayPal sandbox client
is added to the `provider` fixture params when sandbox credentials exist."""
import pytest

from bridge.payments.provider import FakeProvider, ProviderError


@pytest.fixture(params=["fake"])
def provider(request):
    return FakeProvider()


def test_authorize_is_idempotent_by_request_id(provider):
    a = provider.authorize(100, "r1", "run-1")
    assert provider.authorize(100, "r1", "run-1") == a
    assert provider.authorize(100, "r2", "run-2").auth_id != a.auth_id


def test_capture_moves_money_once_per_request_id(provider):
    a = provider.authorize(100, "a", "run")
    c1 = provider.capture(a.auth_id, 25, "c1")
    assert provider.capture(a.auth_id, 25, "c1") == c1
    assert provider.captured_total() == 25


def test_capture_cannot_exceed_the_authorization(provider):
    a = provider.authorize(100, "a", "run")
    provider.capture(a.auth_id, 60, "c1")
    with pytest.raises(ProviderError, match="exceeds"):
        provider.capture(a.auth_id, 50, "c2")


def test_capture_after_void_is_refused(provider):
    a = provider.authorize(100, "a", "run")
    provider.void(a.auth_id, "v1")
    provider.void(a.auth_id, "v1")  # idempotent
    with pytest.raises(ProviderError, match="voided"):
        provider.capture(a.auth_id, 10, "c1")


def test_unknown_authorization_is_refused(provider):
    with pytest.raises(ProviderError):
        provider.capture("nope", 10, "c1")
    with pytest.raises(ProviderError):
        provider.void("nope", "v1")


def test_refund_reverses_a_capture(provider):
    a = provider.authorize(100, "a", "run")
    c = provider.capture(a.auth_id, 40, "c1")
    provider.refund(c.capture_id, "f1")
    assert provider.captured_total() == 0


def test_payout_is_idempotent(provider):
    p1 = provider.payout("author-1", 30, "p1")
    assert provider.payout("author-1", 30, "p1") == p1 and provider.paid_total() == 30


def test_a_lost_response_can_be_retried_without_charging_twice():
    p = FakeProvider(lose_response_once={"capture"})
    a = p.authorize(100, "a", "run")
    with pytest.raises(ProviderError) as e:
        p.capture(a.auth_id, 25, "c1")
    assert e.value.retryable
    c = p.capture(a.auth_id, 25, "c1")  # same request id after the lost reply
    assert c.amount == 25 and p.captured_total() == 25


def test_fake_provider_state_survives_a_restart(tmp_path):
    path = tmp_path / "provider.json"
    p1 = FakeProvider(path=path)
    a = p1.authorize(100, "a", "run")
    c = p1.capture(a.auth_id, 25, "c1")
    p1.payout("author", 20, "p1")
    p2 = FakeProvider(path=path)
    assert p2.captured_total() == 25 and p2.paid_total() == 20
    assert p2.capture(a.auth_id, 25, "c1") == c and p2.captured_total() == 25  # same request id, same result
    assert p2.authorize(100, "a", "run") == a
    new = p2.authorize(50, "b", "run2")
    assert new.auth_id not in (a.auth_id,)  # ids keep counting where they left off
