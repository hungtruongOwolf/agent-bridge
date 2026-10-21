"""Monthly plans: pay once, ask many times for 30 days.

A plan is bought like any other hire: the buyer approves a hold for the monthly fee, the first answer is delivered, and the plan
starts when that payment is SETTLED (the buyer kept going, or the accept window passed). A plan that was marked not helpful,
refunded or never paid never starts. While a plan is active, answers from that helper cost nothing more and are counted. It
ends after 30 days or when its answers run out, and it NEVER renews by itself: buying another month is a new hold that the
buyer approves. The author is paid from the one monthly payment, through the ordinary ledger.

Plans belong to a helper (its publisher and id), not to one version, so an upgrade does not cancel a month that was paid for.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from ..hub.pricing import SUBSCRIPTION_DAYS
from ..storage.db import Database

PAID_STATES = {"SETTLED"}
DEAD_STATES = {"SETTLED_REJECTED", "DISPUTE_UPHELD", "VOIDED"}


def plan_key(rec) -> str:
    return f"{rec.publisher_key[:8]}/{rec.id}"


class Subscriptions:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.lock = threading.RLock()
        self.pending: dict[str, dict] = {}  # run id -> a plan waiting for its payment to settle
        self.active: dict[str, dict] = {}  # "<buyer>|<plan key>" -> the running plan
        self.docs = None
        if self.path:  # plans live in a database beside the given name; an older JSON file of that name is imported once
            self.docs = Database(self.path.with_suffix(".db")).collection("plans")
            if self.path.exists() and self.docs.count() == 0:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.docs.write({"pending": raw.get("pending", {}), "active": raw.get("active", {})})
            self.pending, self.active = self.docs.get("pending", {}), self.docs.get("active", {})

    def _save(self) -> None:
        if self.docs is not None:
            self.docs.write({"pending": self.pending, "active": self.active})

    @staticmethod
    def _k(buyer: str, key: str) -> str:
        return f"{buyer}|{key}"

    def register(self, run_id: str, rec, buyer: str) -> None:
        """A plan has been bought: it starts once this run's payment settles."""
        with self.lock:
            self.pending[run_id] = {"buyer": buyer, "key": plan_key(rec), "helper": rec.id, "included": rec.listing.included_answers,
                                    "fee_cents": rec.listing.max_cents}
            self._save()

    def _settle(self, ledger, now: float) -> None:
        """Start the plans whose payment went through, and forget the ones that did not."""
        changed = False
        for run_id, p in list(self.pending.items()):
            row = ledger.rows.get(run_id)
            if row is None or row.state in DEAD_STATES:
                del self.pending[run_id]
                changed = True
            elif row.state in PAID_STATES and row.captured() >= p["fee_cents"]:
                paid_at = next((e["t"] for e in reversed(row.events) if e["to"] in PAID_STATES), now)
                self.active[self._k(p["buyer"], p["key"])] = {"helper": p["helper"], "key": p["key"], "buyer": p["buyer"], "since": paid_at,
                                                              "until": paid_at + SUBSCRIPTION_DAYS * 86400, "included": p["included"], "used": 0, "run_id": run_id}
                del self.pending[run_id]
                changed = True
        if changed:
            self._save()

    def current(self, buyer: str, rec, ledger, now: float) -> dict | None:
        """The buyer's running plan for this helper, if it can still answer."""
        with self.lock:
            self._settle(ledger, now)
            a = self.active.get(self._k(buyer, plan_key(rec)))
            if a is None:
                return None
            if now >= a["until"] or a["used"] >= a["included"]:
                return None
            return dict(a, left=a["included"] - a["used"])

    def use(self, buyer: str, rec) -> None:
        with self.lock:
            a = self.active.get(self._k(buyer, plan_key(rec)))
            if a is not None:
                a["used"] += 1
                self._save()

    def cancel(self, buyer: str, key: str) -> bool:
        """Stop a plan now. The month already paid for is not refunded; nothing else will ever be charged."""
        with self.lock:
            gone = self.active.pop(self._k(buyer, key), None) is not None
            if gone:
                self._save()
            return gone

    def listing(self, buyer: str, ledger, now: float) -> list[dict]:
        with self.lock:
            self._settle(ledger, now)
            out = [dict(a, left=max(0, a["included"] - a["used"]), running=now < a["until"] and a["used"] < a["included"])
                   for a in self.active.values() if a["buyer"] == buyer]
            out += [{"helper": p["helper"], "key": p["key"], "pending": True, "included": p["included"], "fee_cents": p["fee_cents"]}
                    for p in self.pending.values() if p["buyer"] == buyer]
            return sorted(out, key=lambda a: -a.get("since", 0))
