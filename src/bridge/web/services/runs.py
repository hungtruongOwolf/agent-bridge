"""Running a helper: pick it, place the hold, run it in the sealed cell, settle the money for what happened, and keep the report.
Holds the state of runs in flight (waiting for approval, working now) and the reports of recent ones."""
from __future__ import annotations

import re
import secrets

from ...engine.journal import Journal
from ...hub.pricing import facts_from_report
from ...memory.broker import Lens
from ...payments.ledger import StateError
from ...payments.provider import ProviderError
from ...runner import run_pack
from .clients import LazyModel, LeakyModel


def _words(text: str) -> frozenset:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def _similar(a: frozenset, b: frozenset) -> bool:
    """Two short texts that share most of their words say the same thing (a suggestion that only rephrases memory)."""
    return bool(a and b) and len(a & b) / len(a | b) >= 0.7


HARD_EVIDENCE = ("CANARY_HIT", "SANDBOX_NETWORK", "SANDBOX_PROCESS")  # a bait record was touched, or the sealed room was probed


def live_incident(rep) -> str | None:
    """The deterministic evidence in a killed run, if any. A bait read, a canary in the output or a probe of the sealed
    room cannot happen by accident; a plain refusal or a budget stop can."""
    for e in rep.broker_events:
        if e["kind"] in HARD_EVIDENCE:
            return e["kind"]
    return "CANARY_IN_OUTPUT" if rep.outcome == "KILLED" and any("canary" in r for r in rep.reasons) else None


class RunService:
    def __init__(self, *, registry, market, dirs: dict, vault, quarantine, threads, ledger, subs, payments,
                 lock, clock, requester: str, payee, model_factory, web, cell):
        self.registry, self.market, self.dirs, self.vault = registry, market, dirs, vault  # vault: a function, so accepted memories are seen at once
        self.quarantine, self.threads, self.ledger, self.subs, self.payments = quarantine, threads, ledger, subs, payments
        self.lock, self.clock, self.requester, self.payee = lock, clock, requester, payee
        self.model_factory, self.web, self.cell = model_factory, web, cell
        self.chat = None  # set once the chat service exists (it needs this one)
        self.count = 0
        self.pending: dict[str, dict] = {}  # runs waiting for the buyer to approve the hold
        self.live: dict[str, object] = {}  # run id -> journal of a run in progress, so the page can show what is happening
        self.reports: dict[str, dict] = {}  # run_id -> full report (this session)
        self.history: list[dict] = []

    def new_run_id(self) -> str:
        with self.lock:
            self.count += 1
            return f"run-{self.count}-{secrets.token_hex(3)}"

    def resolve_agent(self, key: str):
        if not isinstance(key, str):
            raise ValueError("unknown or revoked pack")
        rec = self.registry.records.get(key)
        if rec is None or rec not in self.registry.installable():
            raise ValueError("unknown or revoked pack")
        pack_dir = self.dirs.get(rec.digest)
        if pack_dir is None:
            raise ValueError("pack files on disk do not match the registered digest")
        return rec, pack_dir

    def hire(self, rec, run_id: str):
        price = rec.listing.max_cents  # the most this answer can cost (a monthly plan: the fee); the real price is worked out afterwards
        try:  # the hold comes last before starting; nothing is charged before a result exists
            with self.lock:
                row = self.ledger.hire(run_id, rec.key, self.payee(rec), self.requester, price, self.clock())
                if rec.listing.subscription:  # the plan starts once this payment settles
                    self.subs.register(run_id, rec, self.requester)
                return row
        except ProviderError as e:
            raise ValueError(f"payment could not be authorized: {e}") from e

    def run(self, body: dict) -> dict:
        """One-off run (the office's quick hire): no conversation, the lens comes from the request."""
        rec, pack_dir = self.resolve_agent(body.get("key", ""))
        if not isinstance(body.get("types", []), list):
            raise ValueError("types must be a list")
        types = frozenset(t for t in body.get("types", []) if isinstance(t, str))
        if not types:
            raise ValueError("choose at least one record type to share")
        task = str(body.get("task", ""))[:1000]
        run_id = self.new_run_id()
        row = self.hire(rec, run_id)
        params = {"rec": rec, "pack_dir": pack_dir, "lens": Lens(types=types), "task": task,
                  "history": [], "simulate": body.get("model") == "leak", "thread_id": None}
        if row.state == "AWAITING_APPROVAL":  # the buyer must approve the hold on the provider's page first
            with self.lock:
                self.pending[run_id] = params
            return {"needs_approval": True, "run_id": run_id, "approve_url": row.approve_url,
                    "price": row.price, "test_money": True}
        return self.job(run_id, params)

    def continue_run(self, body: dict) -> dict:
        """Called after the buyer approved the hold, for both one-off runs and chat messages."""
        run_id = str(body.get("run_id", ""))
        with self.lock:
            params = self.pending.get(run_id)
        if params is None:
            raise ValueError("no run is waiting for approval under that id")
        try:
            with self.lock:
                row = self.ledger.rows.get(run_id)
                if row is not None and row.state == "AWAITING_APPROVAL":
                    self.ledger.confirm_approval(run_id, self.clock())
                elif row is None or row.state in ("VOIDED",):
                    self.pending.pop(run_id, None)
                    if params.get("thread_id"):
                        self.threads.end(params["thread_id"])
                    raise ValueError("the approval ran out of time, so nothing was held. Send the message again.")
        except StateError as e:
            raise ValueError("this approval can no longer be used. Send the message again.") from e
        except ProviderError as e:
            raise ValueError(f"the hold is not approved yet: {e}") from e
        with self.lock:
            if self.pending.pop(run_id, None) is None:  # a second click while the first is running
                raise ValueError("this run was already started")
        if params.get("thread_id"):
            return self.chat.finish_turn(run_id, params)
        return self.job(run_id, params)

    def job(self, run_id: str, params: dict) -> dict:
        """Run the pack and settle the money for what happened. Never leaves a hold open."""
        rec, pack_dir = params["rec"], params["pack_dir"]
        model = LeakyModel() if params["simulate"] else LazyModel(self.model_factory)
        covered = bool(params.get("covered"))  # an answer inside a monthly plan that is already paid for: no hold, no ledger row
        try:
            if not covered:
                with self.lock:
                    self.ledger.start(run_id, self.clock())
            journal = Journal()
            with self.lock:
                self.live[run_id] = journal
            try:
                rep = run_pack(pack_dir, self.vault(), params["lens"], model, seed=run_id, cell=self.cell,
                               expected_digest=rec.digest, run_id=run_id, web=self.web,
                               task=params["task"], history=params["history"], journal=journal)
            finally:
                with self.lock:
                    self.live.pop(run_id, None)
        except Exception:
            if not covered:
                with self.lock:
                    try:
                        self.ledger.fail_infra(run_id, self.clock(), "run crashed before a result")
                    except StateError:
                        pass
            raise
        with self.lock:
            if covered:
                if rep.outcome == "COMPLETE":
                    self.subs.use(self.requester, rec)
            else:
                if rep.outcome == "COMPLETE" and rec.listing.metered:  # the buyer pays for what the run did, up to the held maximum
                    facts = facts_from_report(rep)
                    try:
                        self.ledger.reprice(run_id, rec.listing.cents_for(facts), self.clock(), f"priced by what the run did ({rec.listing.explain(facts)})")
                    except StateError:
                        pass
                self._settle_outcome(rec, run_id, rep)
            if rep.outcome == "KILLED" and not params["simulate"]:  # kill switch: hard evidence takes the helper off the market until its author fixes and republishes
                why = live_incident(rep)
                if why:
                    self.registry.revoke(rec.key, f"suspended after a live incident ({why}) in {run_id}")
            out = dict(rep.__dict__)
            raw = out.pop("proposals_raw")
            known = [_words(r.text) for r in self.vault().all()] + [_words(p.text) for p in self.quarantine.pending()]
            fresh = [x for x in raw if not (isinstance(x, dict) and any(_similar(_words(str(x.get("text", ""))), k) for k in known))]
            dupes = len(raw) - len(fresh)
            added, problems = self.quarantine.add(run_id, rep.digest, fresh) if rep.outcome == "COMPLETE" else ([], [])
            if dupes:
                problems.append(f"{dupes} suggestion(s) were already in your memory and were left out")
            out["proposals"] = [{"id": p.id, "type": p.type, "text": p.text} for p in added]
            out["proposal_problems"] = problems
            out["payment"] = ({"state": "COVERED", "price": 0, "floor": 0, "captured": 0, "refunded": 0, "accept_by": None, "payout": {"status": "none", "amount": 0},
                               "test_money": True, "events": []} if covered else self.payments.payment(run_id))
            self.reports[run_id] = out
            while len(self.reports) > 100:
                self.reports.pop(next(iter(self.reports)))
            del self.history[:-100]
            self.history.append({"run_id": run_id, "pack": f"{rep.pack_id} v{rep.version}", "outcome": rep.outcome,
                                 "summary": rep.summary, "n": self.count})
        return out

    def _settle_outcome(self, rec, run_id: str, rep) -> None:
        now = self.clock()
        if rep.outcome == "COMPLETE":
            self.ledger.result_ready(run_id, now)  # floor fee captured; the requester decides on the rest
        elif rep.outcome == "KILLED":
            why = rep.broker_events[0]["kind"] if rep.broker_events else "evidence of theft"
            self.ledger.kill(run_id, now, why)  # a held claim, never a final void of delivered work
            if self.market.status(rec) == "flagged":
                # the Certifier independently reproduced a violation for this exact pack digest
                self.ledger.adjudicate(run_id, True, now)
        else:
            self.ledger.fail_infra(run_id, now, f"no usable result ({rep.outcome})")
