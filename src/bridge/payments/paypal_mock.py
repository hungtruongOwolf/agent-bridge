"""A local stand-in for the PayPal sandbox, so the whole payment flow can be run and shown without credentials.

It speaks the same REST calls that `PayPalSandbox` makes (OAuth token, Orders v2 AUTHORIZE, authorize, capture, void,
refund, Payouts) and serves a buyer approval page like PayPal's. Money here is a number in a file: nothing leaves this
computer and nothing is real. It is an emulator written from PayPal's public documentation, NOT the real sandbox, and every
page says so. Its job is to exercise the real client code (headers, idempotency, error handling) and the approval flow in the
console end to end; the real sandbox still has to be checked with `bridge paypal-check` once credentials exist.

    bridge paypal-mock --port 9797          # run it on its own
    bridge serve --payments paypal-mock     # or let the console start it
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MOCK_ID, MOCK_SECRET = "mock-client-id", "mock-client-secret"


def cents(value: str) -> int:
    whole, _, frac = str(value).partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def money(c: int) -> str:
    return f"{c // 100}.{c % 100:02d}"


class MockState:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.lock = threading.RLock()
        self.n = 0
        self.orders: dict[str, dict] = {}
        self.auths: dict[str, dict] = {}
        self.captures: dict[str, dict] = {}
        self.refunds: dict[str, dict] = {}
        self.payouts: dict[str, dict] = {}
        self.idem: dict[str, dict] = {}
        if self.path and self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.__dict__.update({k: raw[k] for k in ("n", "orders", "auths", "captures", "refunds", "payouts", "idem")})

    def save(self) -> None:
        if self.path:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({k: getattr(self, k) for k in ("n", "orders", "auths", "captures", "refunds", "payouts", "idem")}), encoding="utf-8")
            os.replace(tmp, self.path)

    def new_id(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}-{self.n:05d}"

    def totals(self) -> dict:
        captured = sum(c["amount"] for c in self.captures.values() if not c.get("refunded"))
        return {"held": sum(max(0, a["amount"] - sum(c["amount"] for c in self.captures.values() if c["auth"] == a["id"]))
                            for a in self.auths.values() if not a.get("voided")),
                "captured": captured, "refunded": sum(c["amount"] for c in self.captures.values() if c.get("refunded")),
                "paid_out": sum(p["amount"] for p in self.payouts.values())}


class MockPayPal:
    """The API. `call` returns (status, json) for one request; the HTTP wrapper below is thin."""

    def __init__(self, base_url: str, state: MockState | None = None, client_id: str = MOCK_ID, secret: str = MOCK_SECRET):
        self.base, self.s, self.client_id, self.secret = base_url.rstrip("/"), state or MockState(), client_id, secret
        self.tokens: set[str] = set()

    def _err(self, status: int, name: str, issue: str):
        return status, {"name": name, "message": issue.replace("_", " ").lower(), "details": [{"issue": issue}]}

    def call(self, method: str, path: str, headers: dict, body: dict | None):
        path = path.split("?")[0]
        if path == "/v1/oauth2/token":
            auth = headers.get("authorization", "")
            try:
                got = base64.b64decode(auth.split(" ", 1)[1]).decode()
            except Exception:
                got = ""
            if got != f"{self.client_id}:{self.secret}":
                return 401, {"error": "invalid_client", "error_description": "Client Authentication failed"}
            tok = "MOCK-" + secrets.token_hex(12)
            self.tokens.add(tok)
            return 200, {"access_token": tok, "token_type": "Bearer", "expires_in": 32400}
        if headers.get("authorization", "").removeprefix("Bearer ") not in self.tokens:
            return 401, {"name": "AUTHENTICATION_FAILURE", "message": "Authentication failed due to invalid authentication credentials"}
        rid = headers.get("paypal-request-id")
        with self.s.lock:
            key = f"{method} {path} {rid}" if rid else None
            if key and key in self.s.idem:
                return self.s.idem[key]["status"], self.s.idem[key]["body"]
            status, out = self._route(method, path, body or {})
            if key and status < 300:
                self.s.idem[key] = {"status": status, "body": out}
            self.s.save()
            return status, out

    def _route(self, method: str, path: str, body: dict):
        s = self.s
        if method == "POST" and path == "/v2/checkout/orders":
            units = body.get("purchase_units") or []
            if body.get("intent") != "AUTHORIZE" or not units:
                return self._err(400, "INVALID_REQUEST", "ONLY_AUTHORIZE_ORDERS_ARE_SUPPORTED")
            amount = cents(units[0]["amount"]["value"])
            if amount <= 0:
                return self._err(422, "UNPROCESSABLE_ENTITY", "INVALID_AMOUNT")
            oid = s.new_id("ORDER")
            ctx = body.get("application_context") or {}
            s.orders[oid] = {"id": oid, "amount": amount, "reference": units[0].get("reference_id", ""), "status": "CREATED",
                             "return_url": ctx.get("return_url", ""), "cancel_url": ctx.get("cancel_url", "")}
            return 201, {"id": oid, "status": "PAYER_ACTION_REQUIRED", "links": [
                {"rel": "self", "href": f"{self.base}/v2/checkout/orders/{oid}", "method": "GET"},
                {"rel": "payer-action", "href": f"{self.base}/checkoutnow?token={oid}", "method": "GET"}]}
        m = re.fullmatch(r"/v2/checkout/orders/([\w-]+)/authorize", path)
        if method == "POST" and m:
            o = s.orders.get(m.group(1))
            if o is None:
                return self._err(404, "RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID")
            if o["status"] not in ("APPROVED", "AUTHORIZED"):
                return self._err(422, "UNPROCESSABLE_ENTITY", "ORDER_NOT_APPROVED")
            if o["status"] == "APPROVED":
                aid = s.new_id("AUTH")
                s.auths[aid] = {"id": aid, "order": o["id"], "amount": o["amount"], "voided": False}
                o["status"], o["auth"] = "AUTHORIZED", aid
            a = s.auths[o["auth"]]
            return 201, {"id": o["id"], "status": "COMPLETED", "purchase_units": [{"payments": {"authorizations": [
                {"id": a["id"], "status": "CREATED", "amount": {"currency_code": "USD", "value": money(a["amount"])}}]}}]}
        m = re.fullmatch(r"/v2/payments/authorizations/([\w-]+)/capture", path)
        if method == "POST" and m:
            a = s.auths.get(m.group(1))
            if a is None:
                return self._err(404, "RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID")
            if a["voided"]:
                return self._err(422, "UNPROCESSABLE_ENTITY", "AUTHORIZATION_VOIDED")
            amount = cents(body["amount"]["value"])
            if amount <= 0 or sum(c["amount"] for c in s.captures.values() if c["auth"] == a["id"]) + amount > a["amount"]:
                return self._err(422, "UNPROCESSABLE_ENTITY", "AUTHORIZATION_AMOUNT_EXCEEDED")
            cid = s.new_id("CAPTURE")
            s.captures[cid] = {"id": cid, "auth": a["id"], "amount": amount, "refunded": False}
            return 201, {"id": cid, "status": "COMPLETED", "amount": {"currency_code": "USD", "value": money(amount)}}
        m = re.fullmatch(r"/v2/payments/authorizations/([\w-]+)/void", path)
        if method == "POST" and m:
            a = s.auths.get(m.group(1))
            if a is None:
                return self._err(404, "RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID")
            a["voided"] = True
            return 204, {}
        m = re.fullmatch(r"/v2/payments/captures/([\w-]+)/refund", path)
        if method == "POST" and m:
            c = s.captures.get(m.group(1))
            if c is None:
                return self._err(404, "RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID")
            if c["refunded"]:
                return self._err(422, "UNPROCESSABLE_ENTITY", "CAPTURE_FULLY_REFUNDED")
            c["refunded"] = True
            rid = s.new_id("REFUND")
            s.refunds[rid] = {"id": rid, "capture": c["id"], "amount": c["amount"]}
            return 201, {"id": rid, "status": "COMPLETED"}
        if method == "POST" and path == "/v1/payments/payouts":
            items = body.get("items") or []
            if not items or "@" not in str(items[0].get("receiver", "")):
                return self._err(400, "VALIDATION_ERROR", "RECEIVER_INVALID")
            pid = s.new_id("PAYOUT")
            s.payouts[pid] = {"id": pid, "to": items[0]["receiver"], "amount": cents(items[0]["amount"]["value"])}
            return 201, {"batch_header": {"payout_batch_id": pid, "batch_status": "PENDING"}}
        return self._err(404, "RESOURCE_NOT_FOUND", "NO_SUCH_ENDPOINT")

    # -- the buyer's side --------------------------------------------------------------------------
    def approve(self, token: str) -> str | None:
        with self.s.lock:
            o = self.s.orders.get(token)
            if o is None:
                return None
            if o["status"] == "CREATED":
                o["status"] = "APPROVED"
            self.s.save()
            sep = "&" if "?" in o["return_url"] else "?"
            return f"{o['return_url']}{sep}token={token}&PayerID=MOCKPAYER"

    def cancel(self, token: str) -> str | None:
        o = self.s.orders.get(token)
        return o["cancel_url"] if o else None


PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{title}</title>
<body style="font:16px system-ui,sans-serif;background:#f5f7fa;margin:0;display:grid;place-items:start center;min-height:100vh">
<main style="background:#fff;border:1px solid #cbd2d9;border-radius:12px;padding:28px;margin:40px 16px;max-width:520px;width:100%">
<div style="background:#fff3cd;border:1px solid #e0c36a;padding:8px 12px;border-radius:8px;font-size:14px;margin-bottom:18px">
Practice server. This imitates the PayPal sandbox. No real money, no real PayPal account.</div>{body}</main>"""


def _page(title: str, body: str) -> bytes:
    return (PAGE.format(title=html.escape(title), body=body)).encode()


def checkout_page(api: MockPayPal, token: str, prefix: str = "") -> tuple[int, bytes]:
    """The buyer's approval page. `prefix` is where the practice server is mounted when it shares a port with the console ("/practice")."""
    o = api.s.orders.get(token)
    if o is None:
        return 404, _page("Not found", "<p>That payment was not found.</p>")
    tok = urllib.parse.quote(o["id"])
    body = (f"<h1 style='margin:0 0 6px'>Pay ${money(o['amount'])} USD</h1><p style='color:#52606d'>agent-bridge asks you to put a hold of "
            f"<b>${money(o['amount'])}</b> on your account. Nothing is charged until a helper has answered.</p>"
            f"<form method=post action='{prefix}/checkoutnow/approve?token={tok}' style='display:inline'><button style='background:#0070ba;color:#fff;border:0;"
            f"border-radius:20px;padding:12px 26px;font-size:16px;cursor:pointer'>Approve the hold</button></form> "
            f"<form method=post action='{prefix}/checkoutnow/cancel?token={tok}' style='display:inline'><button style='background:none;border:0;"
            f"color:#0070ba;font-size:15px;cursor:pointer;margin-left:10px'>Cancel</button></form>"
            f"<p style='font-size:13px;color:#7b8794;margin-top:22px'>Reference: {html.escape(o['reference'])} · Order {html.escape(o['id'])}</p>")
    return 200, _page("Approve the hold", body)


def state_page(api: MockPayPal) -> bytes:
    t = api.s.totals()
    rows = "".join(f"<tr><td>{html.escape(o['id'])}</td><td>{html.escape(o['reference'])}</td><td>${money(o['amount'])}</td><td>{o['status']}</td></tr>" for o in api.s.orders.values())
    pay = "".join(f"<tr><td>{html.escape(p['to'])}</td><td>${money(p['amount'])}</td></tr>" for p in api.s.payouts.values())
    body = (f"<h1 style='margin:0 0 12px'>Practice PayPal</h1><p>On hold ${money(t['held'])} · Captured ${money(t['captured'])} · "
            f"Refunded ${money(t['refunded'])} · Paid out ${money(t['paid_out'])}</p><h3>Orders</h3><table cellpadding=6>{rows}</table>"
            f"<h3>Payouts to authors</h3><table cellpadding=6>{pay}</table>")
    return _page("Practice PayPal", body)


def buyer_decision(api: MockPayPal, action: str, token: str) -> str | None:
    """The buyer pressed Approve or Cancel: the address to send them back to, or None when there is no such payment."""
    return api.approve(token) if action == "approve" else api.cancel(token)


def make_handler(api: MockPayPal):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status: int, body: bytes, ctype: str = "application/json", extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _api(self, method: str):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            ctype = self.headers.get("Content-Type", "")
            body = None
            if raw and "json" in ctype:
                try:
                    body = json.loads(raw)
                except ValueError:
                    return self._send(400, b'{"name":"INVALID_REQUEST"}')
            status, out = api.call(method, self.path, {k.lower(): v for k, v in self.headers.items()}, body)  # header names are case-insensitive
            self._send(status, json.dumps(out).encode() if status != 204 else b"")

        def do_POST(self):
            u = urllib.parse.urlsplit(self.path)
            if u.path in ("/checkoutnow/approve", "/checkoutnow/cancel"):
                token = urllib.parse.parse_qs(u.query).get("token", [""])[0]
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                target = buyer_decision(api, "approve" if u.path.endswith("approve") else "cancel", token)
                if not target:
                    return self._send(404, _page("Not found", "<p>That payment was not found.</p>"), "text/html; charset=utf-8")
                return self._send(303, b"", "text/plain", {"Location": target})
            self._api("POST")

        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path == "/checkoutnow":
                status, page = checkout_page(api, q.get("token", [""])[0])
                return self._send(status, page, "text/html; charset=utf-8")
            if u.path == "/mock/state.json":
                return self._send(200, json.dumps({"totals": api.s.totals(), "orders": api.s.orders, "auths": api.s.auths, "captures": api.s.captures,
                                                   "refunds": api.s.refunds, "payouts": api.s.payouts}).encode())
            if u.path == "/mock/state":
                return self._send(200, state_page(api), "text/html; charset=utf-8")
            self._api("GET")

    return H


def serve_mock(port: int = 0, state_path: Path | None = None) -> tuple[ThreadingHTTPServer, MockPayPal]:
    """Start the emulator on 127.0.0.1. Returns the server (call serve_forever in a thread) and the API object."""
    httpd = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    api = MockPayPal(f"http://127.0.0.1:{httpd.server_address[1]}", MockState(state_path))
    httpd.RequestHandlerClass = make_handler(api)
    return httpd, api
