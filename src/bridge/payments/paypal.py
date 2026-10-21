"""PayPal sandbox client (Orders v2 AUTHORIZE, Payments v2 capture / void / refund, Payouts).

STATUS: written from PayPal's public REST documentation and tested only against a recording fake
transport (tests/payments/test_paypal_client.py). It has NOT been run against the live sandbox. Treat every
field name and flow below as unverified until `bridge paypal-check` and the contract tests have passed with
real sandbox credentials.

Safety: this client refuses any base URL other than the PayPal sandbox, so test money can never become real
money by a typo. Idempotency: every mutating call sends `PayPal-Request-Id`, which PayPal uses to return the
original result for a repeated request.

Flow notes. An AUTHORIZE order is created first; the buyer must approve it on PayPal's page (the `approve`
link). Only then does `confirm` call `/authorize` to obtain the authorization id used for capture and void.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from .provider import Auth, Capture, ProviderError

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
CURRENCY = "USD"


def _money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def load_paypal_credentials(env_file: Path | str = ".env") -> tuple[str, str]:
    try:
        lines = Path(env_file).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise ProviderError("no .env file with PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET") from e
    found = {}
    for line in lines:
        for name in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
            if line.startswith(name + "="):
                found[name] = line.split("=", 1)[1].strip()
    if not found.get("PAYPAL_CLIENT_ID") or not found.get("PAYPAL_CLIENT_SECRET"):
        raise ProviderError("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are not set in .env")
    return found["PAYPAL_CLIENT_ID"], found["PAYPAL_CLIENT_SECRET"]


def _http(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except ValueError:
            return e.code, {}


class PayPalSandbox:
    def __init__(self, client_id: str, secret: str, *, base_url: str = SANDBOX_BASE,
                 http: Callable[..., tuple[int, dict]] = _http,
                 return_url: str = "http://127.0.0.1:8787/paypal/return",
                 cancel_url: str = "http://127.0.0.1:8787/paypal/cancel"):
        if base_url.rstrip("/") != SANDBOX_BASE:
            raise ValueError("this client only talks to the PayPal sandbox")
        self._id, self._secret, self._base, self._http = client_id, secret, base_url.rstrip("/"), http
        self._return, self._cancel = return_url, cancel_url
        self._token: str | None = None

    # -- transport ---------------------------------------------------------------------------------
    def _auth_token(self) -> str:
        basic = base64.b64encode(f"{self._id}:{self._secret}".encode()).decode()
        status, out = self._http("POST", f"{self._base}/v1/oauth2/token",
                                 {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
                                 urllib.parse.urlencode({"grant_type": "client_credentials"}).encode())
        if status != 200 or "access_token" not in out:
            raise ProviderError("PayPal rejected the sandbox credentials")
        return out["access_token"]

    def _call(self, method: str, path: str, body: dict | None, request_id: str | None) -> dict:
        for attempt in (0, 1):
            if self._token is None:
                self._token = self._auth_token()
            headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
            if request_id:
                headers["PayPal-Request-Id"] = request_id
            try:
                status, out = self._http(method, f"{self._base}{path}", headers, json.dumps(body).encode() if body is not None else None)
            except Exception as e:  # network trouble: the call may or may not have happened, so it is retryable
                raise ProviderError(f"PayPal unreachable ({type(e).__name__})", retryable=True) from e
            if status == 401 and attempt == 0:
                self._token = None  # expired token: fetch a new one once
                continue
            if status >= 500 or status == 429:
                raise ProviderError(f"PayPal temporary error {status}", retryable=True)
            if status >= 400:
                detail = (out.get("details") or [{}])[0].get("issue") or out.get("name") or out.get("message") or str(status)
                raise ProviderError(f"PayPal refused: {str(detail)[:120]}")
            return out
        raise ProviderError("PayPal authentication failed")

    # -- PaymentProvider ---------------------------------------------------------------------------
    def authorize(self, amount: int, request_id: str, reference: str) -> Auth:
        out = self._call("POST", "/v2/checkout/orders", {
            "intent": "AUTHORIZE",
            "purchase_units": [{"reference_id": reference[:127], "amount": {"currency_code": CURRENCY, "value": _money(amount)}}],
            "application_context": {"return_url": self._return, "cancel_url": self._cancel, "user_action": "PAY_NOW",
                                    "shipping_preference": "NO_SHIPPING"},
        }, request_id)
        link = next((l["href"] for l in out.get("links", []) if l.get("rel") in ("approve", "payer-action")), None)
        if not out.get("id") or not link:
            raise ProviderError("PayPal did not return an order with an approval link")
        return Auth(out["id"], amount, link)

    def confirm(self, auth_id: str, request_id: str) -> Auth:
        out = self._call("POST", f"/v2/checkout/orders/{auth_id}/authorize", {}, request_id)
        try:
            a = out["purchase_units"][0]["payments"]["authorizations"][0]
            return Auth(a["id"], round(float(a["amount"]["value"]) * 100))
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise ProviderError("the buyer has not approved the hold yet") from e

    def capture(self, auth_id: str, amount: int, request_id: str) -> Capture:
        out = self._call("POST", f"/v2/payments/authorizations/{auth_id}/capture",
                         {"amount": {"currency_code": CURRENCY, "value": _money(amount)}, "final_capture": False}, request_id)
        if out.get("status") not in ("COMPLETED", "PENDING") or "id" not in out:
            raise ProviderError(f"capture not completed ({out.get('status')})")
        return Capture(out["id"], amount)

    def void(self, auth_id: str, request_id: str) -> None:
        self._call("POST", f"/v2/payments/authorizations/{auth_id}/void", None, request_id)

    def refund(self, capture_id: str, request_id: str) -> None:
        self._call("POST", f"/v2/payments/captures/{capture_id}/refund", {}, request_id)

    def payout(self, to: str, amount: int, request_id: str) -> str:
        if "@" not in to:
            raise ProviderError("a PayPal payout needs the author's PayPal email")
        out = self._call("POST", "/v1/payments/payouts", {
            "sender_batch_header": {"sender_batch_id": request_id[:100], "email_subject": "agent-bridge payout (sandbox)"},
            "items": [{"recipient_type": "EMAIL", "receiver": to, "sender_item_id": request_id[:100],
                       "amount": {"value": _money(amount), "currency": CURRENCY}}],
        }, request_id)
        batch = out.get("batch_header", {}).get("payout_batch_id")
        if not batch:
            raise ProviderError("PayPal did not return a payout batch id")
        return batch
