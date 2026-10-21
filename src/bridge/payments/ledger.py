"""Hub ledger: one row per hire, one state machine, money moves only through idempotent provider calls.

States
  AWAITING_APPROVAL  the buyer has not yet approved the hold on the provider's page; nothing is held
  AUTHORIZED         the requester's cap is held; nothing is charged
  RUNNING            the run started
  RESULT_READY       floor fee captured; waiting for accept / reject (or auto-accept at the deadline)
  SETTLED            outcome fee captured; author payout scheduled
  SETTLED_REJECTED   requester rejected: the floor fee stays with the author, the rest is released
  DISPUTE_HOLD       a kill claim: the hold stays until someone adjudicates (never a final void of delivered work)
  DISPUTE_UPHELD     claim upheld: everything refunded or released, the author gets nothing
  VOIDED             no charge (infrastructure failure or the pack's own failure before any result)

Rules (from the design, SM s3): a non-refundable floor fee plus an outcome fee; accept, reject, kill and void
are mutually exclusive because every transition checks the row's current state under one lock; every
provider call carries a request id derived from the run id, so a retry after a lost reply never charges twice;
a write-ahead `intent` makes a crash between "provider acted" and "row updated" recoverable.
Silence after a run started captures the floor and falls to auto-accept (N-1 in the design review).
Amounts are integer cents. All fees here are proposals, not facts.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..storage.db import Database
from .provider import PaymentProvider, ProviderError

TERMINAL = {"SETTLED", "SETTLED_REJECTED", "DISPUTE_UPHELD", "VOIDED"}
APPROVAL_WINDOW_S = 15 * 60


class StateError(Exception):
    """The requested transition is not allowed from the row's current state."""


class PendingError(Exception):
    """The provider did not confirm in time. The intent is saved; `recover()` will finish it."""


@dataclass
class Row:
    run_id: str
    pack_key: str
    author: str
    requester: str
    price: int
    floor: int
    hold: int = 0  # what was put on hold at hire; the final price may turn out lower (metered helpers)
    state: str = "AUTHORIZED"
    rev: int = 0
    auth_id: str | None = None
    captures: list = field(default_factory=list)  # [{id, amount, kind}]
    refunded: list = field(default_factory=list)
    payout: dict = field(default_factory=lambda: {"status": "none", "amount": 0})
    run_deadline: float | None = None
    accept_by: float | None = None
    dispute_by: float | None = None
    accept_window_s: float = 48 * 3600
    voided: bool = False
    approve_url: str | None = None
    approval_by: float | None = None
    intent: dict | None = None
    events: list = field(default_factory=list)

    def captured(self) -> int:
        return sum(c["amount"] for c in self.captures if c["id"] not in self.refunded)


class Ledger:
    def __init__(self, provider: PaymentProvider, *, path: Path | None = None, floor_pct: int = 25,
                 fee_pct: int = 10, holdback_s: float = 0.0, retries: int = 3):
        self.provider, self.path = provider, Path(path) if path else None
        self.floor_pct, self.fee_pct, self.holdback_s, self.retries = floor_pct, fee_pct, holdback_s, retries
        self.rows: dict[str, Row] = {}
        self._lock = threading.RLock()
        self.docs = None
        if self.path:  # rows live in a database beside the given name; an older JSON file of that name is imported once
            self.docs = Database(self.path.with_suffix(".db")).collection("ledger")
            if self.path.exists() and self.docs.count() == 0:
                for raw in json.loads(self.path.read_text(encoding="utf-8")):
                    self.docs.put(raw["run_id"], raw)
            for _, raw in self.docs.items():
                self.rows[raw["run_id"]] = Row(**raw)
        self._dirty: set[str] = set()  # rows changed since they were last stored
        self._active: set[str] = {i for i, r in self.rows.items() if self._needs_attention(r)}
        self._summary: dict | None = None  # recomputed only after something changed
        self._on_hold: int | None = None

    # -- persistence -----------------------------------------------------------------------------
    @staticmethod
    def _needs_attention(r: "Row") -> bool:
        """Rows the clock or a payout can still change. Everything else is history and is never looked at again by the time-driven rules."""
        return r.state not in TERMINAL or r.payout["status"] in ("pending", "failed") or bool(r.intent) or (r.state == "VOIDED" and not r.voided)

    def _touch(self, row: "Row") -> None:
        self._dirty.add(row.run_id)
        self._summary = self._on_hold = None
        (self._active.add if self._needs_attention(row) else self._active.discard)(row.run_id)

    def _save(self) -> None:
        """Store the rows that changed (and only those)."""
        dirty, self._dirty = self._dirty, set()
        if self.docs is not None and dirty:
            self.docs.write({i: asdict(self.rows[i]) for i in dirty if i in self.rows}, [i for i in dirty if i not in self.rows])

    def _row(self, run_id: str) -> Row:
        try:
            row = self.rows[run_id]
        except KeyError:
            raise StateError(f"unknown run {run_id!r}") from None
        self._touch(row)  # whoever asks for a row to work on is about to change it
        return row

    def _move(self, row: Row, allowed: set[str], new: str, now: float, reason: str) -> None:
        if row.state not in allowed:
            raise StateError(f"cannot go to {new}: the run is {row.state}")
        row.events.append({"t": now, "from": row.state, "to": new, "why": reason})
        row.state, row.rev = new, row.rev + 1

    # -- provider calls with retry and write-ahead intent ---------------------------------------
    def _do(self, row: Row, op: str, fn):
        row.intent = {"op": op}
        self._touch(row)
        self._save()
        self._touch(row)  # and again: the caller changes the row once the provider has answered
        last: Exception | None = None
        for _ in range(self.retries):
            try:
                out = fn()
                row.intent = None
                return out
            except ProviderError as e:
                last = e
                if not e.retryable:
                    row.intent = None
                    raise
        self._touch(row)
        self._save()
        raise PendingError(f"{op} for {row.run_id} is unconfirmed: {last}")

    def _capture(self, row: Row, amount: int, kind: str) -> None:
        if amount <= 0 or any(c["kind"] == kind for c in row.captures):
            return
        cap = self._do(row, f"capture:{kind}", lambda: self.provider.capture(row.auth_id, amount, f"{row.run_id}:capture:{kind}"))
        row.captures.append({"id": cap.capture_id, "amount": cap.amount, "kind": kind})

    def _void(self, row: Row) -> None:
        if row.voided:
            return
        self._do(row, "void", lambda: self.provider.void(row.auth_id, f"{row.run_id}:void"))
        row.voided = True

    def _schedule_payout(self, row: Row, now: float) -> None:
        gross = row.captured()
        amount = gross - gross * self.fee_pct // 100
        row.payout = {"status": "pending" if amount > 0 else "none", "amount": amount, "ready_at": now + self.holdback_s}

    # -- the flow ----------------------------------------------------------------------------------
    def hire(self, run_id: str, pack_key: str, author: str, requester: str, price: int, now: float,
             accept_window_s: float = 48 * 3600) -> Row:
        with self._lock:
            if run_id in self.rows:  # the same hire twice is the same hire
                return self.rows[run_id]
            if price <= 0:
                raise StateError("price must be positive")
            if author == requester:
                raise StateError("an author cannot hire their own pack")
            row = Row(run_id, pack_key, author, requester, price, price * self.floor_pct // 100,
                      hold=price, accept_window_s=accept_window_s)
            self.rows[run_id] = row
            self._touch(row)
            try:
                auth = self._do(row, "authorize", lambda: self.provider.authorize(price, f"{run_id}:authorize", run_id))
            except ProviderError:
                del self.rows[run_id]
                self._dirty.discard(run_id)
                self._active.discard(run_id)
                raise
            row.auth_id = auth.auth_id
            if auth.approve_url:  # the buyer must approve on the provider's page before any hold exists
                row.state, row.approve_url, row.approval_by = "AWAITING_APPROVAL", auth.approve_url, now + APPROVAL_WINDOW_S
            row.events.append({"t": now, "from": None, "to": row.state, "why": "hire"})
            self._touch(row)
            self._save()
            return row

    def confirm_approval(self, run_id: str, now: float) -> Row:
        with self._lock:
            row = self._row(run_id)
            self._move(row, {"AWAITING_APPROVAL"}, "AUTHORIZED", now, "buyer approved the hold")
            try:
                # the provider may swap the order id for the real authorization id (PayPal does)
                row.auth_id = self._do(row, "confirm", lambda: self.provider.confirm(row.auth_id, f"{run_id}:confirm")).auth_id
            except PendingError:
                self._save()
                raise
            except ProviderError:
                self._rollback(row, "AWAITING_APPROVAL", now, "the provider says the hold is not approved yet")
                raise
            row.approve_url = None
            self._save()
            return row

    def start(self, run_id: str, now: float, run_deadline_s: float = 3600) -> Row:
        with self._lock:
            row = self._row(run_id)
            self._move(row, {"AUTHORIZED"}, "RUNNING", now, "run started")
            row.run_deadline = now + run_deadline_s
            self._save()
            return row

    def reprice(self, run_id: str, amount: int, now: float, reason: str = "priced by what the helper read") -> Row:
        """Lower the price of a run that is under way, once its real cost is known. It can never go above what was held."""
        with self._lock:
            row = self._row(run_id)
            if row.state != "RUNNING":
                raise StateError(f"cannot change the price: the run is {row.state}")
            hold = row.hold or row.price
            if not isinstance(amount, int) or isinstance(amount, bool) or not 1 <= amount <= hold:
                raise StateError("the price must be between 1 cent and what was held")
            if amount != row.price:
                row.events.append({"t": now, "from": row.state, "to": row.state, "why": f"{reason}: {amount}¢ of the {hold}¢ hold"})
                row.price, row.floor = amount, amount * self.floor_pct // 100
                self._save()
            return row

    def result_ready(self, run_id: str, now: float, reason: str = "result ready") -> Row:
        with self._lock:
            row = self._row(run_id)
            self._move(row, {"RUNNING"}, "RESULT_READY", now, reason)
            row.accept_by = now + row.accept_window_s
            try:
                self._capture(row, row.floor, "floor")
            except PendingError:
                self._save()
                raise  # stays RESULT_READY with an intent; recover() finishes the capture
            except ProviderError:
                self._rollback(row, "RUNNING", now, "floor capture declined")
                raise
            self._save()
            return row

    def _rollback(self, row: Row, state: str, now: float, why: str) -> None:
        row.events.append({"t": now, "from": row.state, "to": state, "why": why})
        row.state, row.rev = state, row.rev + 1
        self._save()

    def accept(self, run_id: str, now: float, reason: str = "accepted") -> Row:
        with self._lock:
            row = self._row(run_id)
            self._move(row, {"RESULT_READY"}, "SETTLED", now, reason)
            try:
                self._capture(row, row.price - row.floor, "outcome")
            except PendingError:
                self._save()
                raise  # stays SETTLED with an intent; recover() finishes capture, void and payout
            except ProviderError:
                self._rollback(row, "RESULT_READY", now, "outcome capture declined")
                raise
            self._finish_settlement(row, now)
            self._save()
            return row

    def _finish_settlement(self, row: Row, now: float) -> None:
        self._void_remainder(row)
        if row.payout["status"] == "none" and row.captured() > 0:
            self._schedule_payout(row, now)

    def reject(self, run_id: str, now: float, reason: str = "rejected") -> Row:
        with self._lock:
            row = self._row(run_id)
            self._move(row, {"RESULT_READY"}, "SETTLED_REJECTED", now, reason)
            self._finish_settlement(row, now)
            self._save()
            return row

    def _void_remainder(self, row: Row) -> None:
        if row.captured() < (row.hold or row.price):  # whatever of the hold was not used goes back to the buyer
            self._void(row)

    def kill(self, run_id: str, now: float, evidence: str, dispute_window_s: float = 72 * 3600) -> Row:
        with self._lock:
            row = self._row(run_id)
            self._move(row, {"RUNNING", "RESULT_READY"}, "DISPUTE_HOLD", now, f"kill claim: {evidence}")
            row.dispute_by = now + dispute_window_s  # no provider call: the hold simply stays
            self._save()
            return row

    def adjudicate(self, run_id: str, upheld: bool, now: float) -> Row:
        with self._lock:
            row = self._row(run_id)
            if upheld:
                self._move(row, {"DISPUTE_HOLD"}, "DISPUTE_UPHELD", now, "claim upheld")
                for c in list(row.captures):
                    if c["id"] not in row.refunded:
                        self._do(row, "refund", lambda c=c: self.provider.refund(c["id"], f"{row.run_id}:refund:{c['id']}"))
                        row.refunded.append(c["id"])
                self._void(row)
            else:
                self._move(row, {"DISPUTE_HOLD"}, "SETTLED_REJECTED", now, "claim rejected: the author keeps the floor")
                self._capture(row, row.floor, "floor")
                self._finish_settlement(row, now)
            self._save()
            return row

    def fail_infra(self, run_id: str, now: float, reason: str = "infrastructure failure") -> Row:
        with self._lock:
            row = self._row(run_id)
            self._move(row, {"AWAITING_APPROVAL", "AUTHORIZED", "RUNNING"}, "VOIDED", now, reason)
            if row.approve_url is None:  # an unapproved order holds nothing, so there is nothing to void
                self._void(row)
            self._save()
            return row

    # -- time-driven rules and payouts -------------------------------------------------------------
    def tick(self, now: float) -> list[tuple[str, str]]:
        """Apply deadlines. Returns (run_id, what happened)."""
        done = []
        with self._lock:
            for row in [self.rows[i] for i in list(self._active) if i in self.rows]:
                self._touch(row)
                if row.state == "AWAITING_APPROVAL" and row.approval_by is not None and now >= row.approval_by:
                    self._move(row, {"AWAITING_APPROVAL"}, "VOIDED", now, "the buyer did not approve in time")
                    done.append((row.run_id, "approval expired"))
                elif row.state == "RESULT_READY" and row.accept_by is not None and now >= row.accept_by:
                    try:
                        self.accept(row.run_id, now, "auto-accept: no decision before the deadline")
                        done.append((row.run_id, "auto-accepted"))
                    except (ProviderError, PendingError):
                        done.append((row.run_id, "auto-accept will be retried"))
                elif row.state == "RUNNING" and row.run_deadline is not None and now >= row.run_deadline:
                    # silence after start: the floor is captured, the outcome falls to the auto-accept default
                    try:
                        self.result_ready(row.run_id, now, "silence after start: floor captured")
                        done.append((row.run_id, "silence: floor captured"))
                    except (ProviderError, PendingError):
                        done.append((row.run_id, "capture will be retried"))
                elif row.state == "DISPUTE_HOLD" and row.dispute_by is not None and now >= row.dispute_by \
                        and not any(e["why"] == "dispute overdue" for e in row.events):
                    row.events.append({"t": now, "from": row.state, "to": row.state, "why": "dispute overdue"})
                    done.append((row.run_id, "dispute overdue"))
            self._save()
        return done

    def release_payouts(self, now: float) -> int:
        paid = 0
        with self._lock:
            for row in [self.rows[i] for i in list(self._active) if i in self.rows]:
                self._touch(row)
                p = row.payout
                if p["status"] == "pending" and now >= p["ready_at"]:
                    try:
                        p["payout_id"] = self._do(row, "payout", lambda r=row: self.provider.payout(
                            r.author, r.payout["amount"], f"{r.run_id}:payout"))
                    except ProviderError as e:  # refused (not just slow): keep the money owed, say why, try again later
                        p["status"], p["error"] = "failed", str(e)[:120]
                        continue
                    p["status"] = "paid"
                    paid += 1
            self._save()
        return paid

    def recover(self, now: float) -> list[str]:
        """Finish operations that were in flight when the process died or the provider timed out."""
        fixed = []
        with self._lock:
            for row in [self.rows[i] for i in list(self._active) if i in self.rows]:
                self._touch(row)
                if not row.intent:
                    continue
                op = row.intent["op"]
                if op == "authorize" and row.auth_id is None:
                    row.auth_id = self._do(row, "authorize", lambda r=row: self.provider.authorize(
                        r.price, f"{r.run_id}:authorize", r.run_id)).auth_id
                elif op.startswith("capture:"):
                    kind = op.split(":", 1)[1]
                    self._capture(row, row.floor if kind == "floor" else row.price - row.floor, kind)
                row.intent = None
                if row.state in ("SETTLED", "SETTLED_REJECTED"):
                    self._finish_settlement(row, now)
                elif row.state == "VOIDED":
                    self._void(row)
                fixed.append(f"{row.run_id}:{op}")
            self._save()
        return fixed

    # -- reporting ----------------------------------------------------------------------------------
    def summary(self) -> dict:
        if self._summary is None:
            self._summary = self._totals()
        return dict(self._summary)

    def on_hold(self) -> int:
        """What the buyer has put on hold and not yet paid or released."""
        if self._on_hold is None:
            self._on_hold = sum(max(0, r.price - r.captured() - sum(c["amount"] for c in r.captures if c["id"] in r.refunded))
                                for r in self.rows.values() if r.state not in TERMINAL and r.state != "AWAITING_APPROVAL")
        return self._on_hold

    def _totals(self) -> dict:
        rows = list(self.rows.values())
        return {
            "captured": sum(r.captured() for r in rows),
            "paid_out": sum(r.payout["amount"] for r in rows if r.payout["status"] == "paid"),
            "pending_payout": sum(r.payout["amount"] for r in rows if r.payout["status"] == "pending"),
            "held": sum(r.price - r.captured() for r in rows if r.state == "DISPUTE_HOLD"),
        }
