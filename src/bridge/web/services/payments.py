"""Payments as the buyer sees them: one run's payment, the totals, every receipt, and the accept/reject decision.
Owns no money itself: the ledger does. This only reads it and words it plainly."""
from __future__ import annotations

from ...payments.ledger import PendingError, StateError
from ...payments.provider import ProviderError

STATE_WORDS = {"AWAITING_APPROVAL": "Waiting for you to approve the hold", "AUTHORIZED": "Hold placed", "RUNNING": "The helper is working",
               "RESULT_READY": "Answer delivered; the rest is paid when you keep going", "SETTLED": "Paid", "SETTLED_REJECTED": "You said not helpful: deposit only",
               "DISPUTE_HOLD": "On hold while it is checked", "DISPUTE_UPHELD": "Refunded: the helper was caught cheating", "VOIDED": "Not charged"}


class PaymentsService:
    def __init__(self, *, ledger, subs, threads, registry, reports: dict, lock, clock, requester: str, mode: str, dashboard: str):
        self.ledger, self.subs, self.threads, self.registry = ledger, subs, threads, registry
        self.reports, self.lock, self.clock = reports, lock, clock
        self.requester, self.mode, self.dashboard = requester, mode, dashboard

    def payment(self, run_id: str) -> dict:
        row = self.ledger.rows[run_id]
        return {
            "state": row.state, "price": row.price, "floor": row.floor, "captured": row.captured(),
            "refunded": sum(c["amount"] for c in row.captures if c["id"] in row.refunded),
            "accept_by": row.accept_by, "payout": row.payout, "test_money": True,
            "events": [{"to": e["to"], "why": e["why"]} for e in row.events],
        }

    def summary(self) -> dict:
        with self.lock:
            try:
                self.ledger.tick(self.clock())
                self.ledger.release_payouts(self.clock())
            except (ProviderError, PendingError):
                pass  # the provider is slow; show what we know and try again on the next refresh
            summary = self.ledger.summary()
            summary["on_hold"] = self.ledger.on_hold()
        return {**summary, "test_money": True, "provider": self.mode, "holdback": "demo holdback 0 s; production would hold for days"}

    def receipts(self) -> dict:
        """Every payment as a plain receipt: who was hired, for which chat, what moved, and why the state is what it is."""
        with self.lock:
            chats = {rid: t.title for t in self.threads.threads.values() for rid in t.runs}
            items = []
            for row in list(self.ledger.rows.values())[-100:]:
                rec = self.registry.records.get(row.pack_key)
                refunded = sum(c["amount"] for c in row.captures if c["id"] in row.refunded)
                items.append({"run_id": row.run_id, "helper": rec.id.replace("-", " ").title() if rec else row.pack_key, "chat": chats.get(row.run_id, ""),
                              "price": row.price, "state": row.state, "state_text": STATE_WORDS.get(row.state, row.state), "captured": row.captured(),
                              "refunded": refunded, "payout": {"status": row.payout["status"], "amount": row.payout["amount"]},
                              "author": row.author if "@" in row.author else "", "reference": row.auth_id or "",
                              "when": row.events[0]["t"] if row.events else 0,
                              "events": [{"t": e["t"], "to": STATE_WORDS.get(e["to"], e["to"]), "why": e["why"]} for e in row.events]})
        items.sort(key=lambda i: -i["when"])
        plans = []
        for p in self.subs.listing(self.requester, self.ledger, self.clock()):
            plans.append({"helper": p["helper"].replace("-", " ").title(), "key": p["key"], "pending": bool(p.get("pending")), "included": p["included"],
                          "used": p.get("used", 0), "left": p.get("left", p["included"]), "until": p.get("until", 0), "running": bool(p.get("running"))})
        return {"mode": self.mode, "dashboard": self.dashboard, "summary": self.summary(), "items": items, "plans": plans}

    def settle(self, body: dict) -> dict:
        run_id, action, now = str(body.get("run_id", "")), body.get("action"), self.clock()
        with self.lock:
            if run_id not in self.ledger.rows:
                raise ValueError("unknown run")
            try:
                if action == "accept":
                    self.ledger.accept(run_id, now)
                elif action == "reject":
                    self.ledger.reject(run_id, now, str(body.get("reason", "rejected"))[:80])
                else:
                    raise ValueError("action must be accept or reject")
            except StateError as e:
                raise ValueError(str(e)) from e
            self.ledger.release_payouts(now)
            pay = self.payment(run_id)
            if run_id in self.reports:
                self.reports[run_id]["payment"] = pay
            return pay

    def cancel_plan(self, body: dict) -> dict:
        return {"cancelled": self.subs.cancel(self.requester, str(body.get("key", "")))}
