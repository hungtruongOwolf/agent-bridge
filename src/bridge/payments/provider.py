"""Payment provider interface and an in-memory fake.

Amounts are integer cents. Every call carries a request id; calling again with the same id must return
the same result and move money at most once. That is what lets the ledger retry after a lost response
without double-charging (PayPal's `PayPal-Request-Id` header plays this role for the real client).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class Auth:
    auth_id: str
    amount: int


@dataclass(frozen=True)
class Capture:
    capture_id: str
    amount: int


class PaymentProvider(Protocol):
    def authorize(self, amount: int, request_id: str, reference: str) -> Auth: ...
    def capture(self, auth_id: str, amount: int, request_id: str) -> Capture: ...
    def void(self, auth_id: str, request_id: str) -> None: ...
    def refund(self, capture_id: str, request_id: str) -> None: ...
    def payout(self, to: str, amount: int, request_id: str) -> str: ...


@dataclass
class FakeProvider:
    """Deterministic in-memory provider with the failure modes the ledger must survive."""

    auths: dict[str, dict] = field(default_factory=dict)
    captures: dict[str, dict] = field(default_factory=dict)
    payouts: dict[str, dict] = field(default_factory=dict)
    seen: dict[str, object] = field(default_factory=dict)  # request id -> first result
    calls: list[tuple[str, str]] = field(default_factory=list)
    lose_response_once: set[str] = field(default_factory=set)  # ops whose reply is lost after the effect happens
    decline_capture: bool = False
    path: Path | None = None  # when set, state is saved after every call and reloaded on start
    _n: int = 0

    def __post_init__(self):
        if self.path and Path(self.path).exists():
            raw = json.loads(Path(self.path).read_text(encoding="utf-8"))
            self.auths, self.captures, self.payouts = raw["auths"], raw["captures"], raw["payouts"]
            self._n = raw["n"]
            from_json = raw["seen"]
            for k, v in from_json.items():  # results are stored as plain dicts; rebuild the typed values
                self.seen[k] = Auth(**v) if k.startswith("authorize:") else Capture(**v) if k.startswith("capture:") else v

    def _persist(self):
        if not self.path:
            return
        def plain(v):
            return v.__dict__ if hasattr(v, "__dict__") else v
        data = {"auths": self.auths, "captures": self.captures, "payouts": self.payouts, "n": self._n,
                "seen": {k: plain(v) for k, v in self.seen.items()}}
        tmp = Path(self.path).with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self.path)

    def _idem(self, op: str, request_id: str, make):
        self.calls.append((op, request_id))
        key = f"{op}:{request_id}"
        if key in self.seen:
            return self.seen[key]
        result = make()
        self.seen[key] = result
        self._persist()
        if op in self.lose_response_once:
            self.lose_response_once.discard(op)
            raise ProviderError("timeout after the provider acted", retryable=True)
        return result

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n}"

    def authorize(self, amount, request_id, reference):
        def make():
            a = Auth(self._id("AUTH"), amount)
            self.auths[a.auth_id] = {"amount": amount, "captured": 0, "voided": False, "reference": reference}
            return a
        return self._idem("authorize", request_id, make)

    def capture(self, auth_id, amount, request_id):
        def make():
            a = self.auths.get(auth_id)
            if a is None:
                raise ProviderError("unknown authorization")
            if self.decline_capture:
                raise ProviderError("capture declined")
            if a["voided"]:
                raise ProviderError("authorization was voided")
            if a["captured"] + amount > a["amount"]:
                raise ProviderError("capture exceeds the authorized amount")
            a["captured"] += amount
            c = Capture(self._id("CAP"), amount)
            self.captures[c.capture_id] = {"auth": auth_id, "amount": amount, "refunded": False}
            return c
        return self._idem("capture", request_id, make)

    def void(self, auth_id, request_id):
        def make():
            a = self.auths.get(auth_id)
            if a is None:
                raise ProviderError("unknown authorization")
            a["voided"] = True
            return True
        self._idem("void", request_id, make)

    def refund(self, capture_id, request_id):
        def make():
            c = self.captures.get(capture_id)
            if c is None:
                raise ProviderError("unknown capture")
            c["refunded"] = True
            return True
        self._idem("refund", request_id, make)

    def payout(self, to, amount, request_id):
        def make():
            pid = self._id("PAYOUT")
            self.payouts[pid] = {"to": to, "amount": amount}
            return pid
        return self._idem("payout", request_id, make)

    # -- helpers for assertions ---------------------------------------------------------------
    def captured_total(self) -> int:
        return sum(c["amount"] for c in self.captures.values() if not c["refunded"])

    def paid_total(self) -> int:
        return sum(p["amount"] for p in self.payouts.values())
