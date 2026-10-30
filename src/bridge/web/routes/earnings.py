"""Earnings: what the helpers you built earned, and what you spent on other helpers. Read-only; every amount is whole cents of test money."""
from __future__ import annotations

from ...hub import pricing
from ...pack import signing
from ..api.router import Router

STATUS = {"SETTLED": "Paid", "SETTLED_REJECTED": "Deposit only", "DISPUTE_UPHELD": "Refunded", "VOIDED": "Refunded",
          "AWAITING_APPROVAL": "Waiting", "AUTHORIZED": "On hold", "RUNNING": "On hold", "RESULT_READY": "On hold", "DISPUTE_HOLD": "On hold"}
PLAN_WORDS = {"flat": "One price", "per_file": "Per file", "per_token": "Per token", "complexity": "By effort", "monthly": "Monthly plan"}
DONE = {"SETTLED", "SETTLED_REJECTED", "DISPUTE_UPHELD", "VOIDED"}


def _line(row, rec) -> dict:
    charged = row.captured()
    paid_out = row.payout["amount"] if row.payout["status"] != "none" else 0
    fee = max(charged - paid_out, 0) if paid_out else 0
    done = row.state in DONE
    plan = pricing.plan_of(rec.listing) if rec else "flat"
    return {"run_id": row.run_id, "when": row.events[0]["t"] if row.events else 0,
            "helper": rec.id.replace("-", " ").title() if rec else row.pack_key, "plan": PLAN_WORDS.get(plan, plan),
            "hold": row.hold, "price": row.price, "charged": charged, "author_payout": paid_out, "platform_fee": fee,
            "released": max(row.hold - charged, 0) if done else 0,
            "status": STATUS.get(row.state, "Waiting"), "receipt": row.auth_id or ""}


def _totals(lines: list[dict]) -> dict:
    keys = ("hold", "price", "charged", "author_payout", "platform_fee", "released")
    return {"runs": len(lines), **{k: sum(x[k] for x in lines) for k in keys}}


def earnings(app) -> dict:
    me = signing.public_b64(app.world.author_key)
    records = app.world.registry.records
    with app.lock:
        rows = sorted(app.ledger.rows.values(), key=lambda r: -(r.events[0]["t"] if r.events else 0))
        earned = [_line(r, records.get(r.pack_key)) for r in rows
                  if (rec := records.get(r.pack_key)) is not None and rec.publisher_key == me]
        spent = [_line(r, records.get(r.pack_key)) for r in rows if r.requester == app.requester]
    return {"earned": {"rows": earned, "totals": _totals(earned)}, "spent": {"rows": spent, "totals": _totals(spent)}, "test_money": True}


def register(router: Router, app) -> None:
    router.add("GET", "/api/earnings", lambda r: earnings(app))
