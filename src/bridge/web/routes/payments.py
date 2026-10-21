"""Receipts, the accept/reject decision, and monthly plans."""
from __future__ import annotations

from ..api.router import Router


def register(router: Router, app) -> None:
    pay = app.payments
    router.add("GET", "/api/payments", lambda r: pay.receipts())
    router.add("POST", "/api/settle", lambda r: pay.settle(r.body))
    router.add("POST", "/api/subscription/cancel", lambda r: pay.cancel_plan(r.body))
