"""Local web console: marketplace, lens, run trace.

Binds to 127.0.0.1 only. Every POST needs the per-process token that only the served page knows, and
the Host header must be local, so another website in your browser cannot start runs that spend your
model key (CSRF) or reach the API through DNS rebinding.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..engine.flowd import ModelReply
from ..engine.nebius import NebiusModel, load_api_key
from ..engine.tavily import TavilySearch, load_tavily_key
from ..memory.broker import Lens
from ..memory.quarantine import Quarantine
from ..memory.service import MemoryChangeError, MemoryService
from ..memory.vault import Vault
from ..chat.plain import BLOCKED, how_made
from ..chat.service import ChatBusy, ChatService
from ..chat.threads import ThreadError, ThreadStore
from ..engine.limits import clean_history
from ..engine.journal import Journal
from ..hub.pricing import facts_from_report
from ..payments.ledger import TERMINAL, Ledger, PendingError, StateError
from ..payments.subscriptions import Subscriptions
from ..payments.provider import FakeProvider, ProviderError
from ..pack.digest import tree_digest
from ..runner import run_pack
from ..hub.market import MarketError
from ..studio import Studio
from ..world import World

STATIC = Path(__file__).parent / "static"
STATIC_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".woff2": "font/woff2",
                ".txt": "text/plain; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}
STATIC_PATH = re.compile(r"^/static/((?:fonts/)?[a-z0-9][a-z0-9_.-]*)$")
HOST_RE = re.compile(r"^(\[[0-9a-f:]+\]|[a-z0-9.-]+)(?::[0-9]{1,5})?$")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _words(text: str) -> frozenset:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def _similar(a: frozenset, b: frozenset) -> bool:
    """Two short texts that share most of their words say the same thing (a suggestion that only rephrases memory)."""
    return bool(a and b) and len(a & b) / len(a | b) >= 0.7


class LeakyModel:
    """Simulates a compromised model step that copies everything it can see."""

    def complete(self, prompt, inputs):
        return ModelReply({"summary": json.dumps(inputs, ensure_ascii=False), "risk": "high"}, tokens=100)


class LazyModel:
    """Builds the real model client on first use, so a pack with no model step never needs a key."""

    def __init__(self, factory):
        self._factory, self._model = factory, None

    def complete(self, prompt, inputs):
        if self._model is None:
            self._model = self._factory()
        return self._model.complete(prompt, inputs)


class LazySearch:
    """Builds the Tavily client on first use, so packs that never search need no Tavily key."""

    def __init__(self, factory):
        self._factory, self._client = factory, None

    def search(self, query):
        if self._client is None:
            self._client = self._factory()
        return self._client.search(query)


class App:
    def __init__(self, world: World, packs_dir: Path, vault_path: Path, env_file: Path, cell=None,
                 model_factory=None, web=None, ledger=None, clock=None, demo_author_email: str = "",
                 payments_mode: str = "test", payments_dashboard: str = ""):
        self.world, self.vault_path, self.env_file, self.cell = world, Path(vault_path), Path(env_file), cell
        self.web = web or LazySearch(lambda: TavilySearch(load_tavily_key(self.env_file)))
        self.model_factory = model_factory or (lambda: NebiusModel(load_api_key(self.env_file)))
        self.token = secrets.token_urlsafe(16)
        roots = [Path(packs_dir), self.world.state / "candidates", self.world.state / "published"]  # improvements and the helpers you published live in state
        self.dirs = {tree_digest(d): d for r in roots if r.exists() for d in sorted(r.iterdir()) if (d / "pack.yaml").exists()}
        self.lock = threading.RLock()  # guards counters, reports, history and pending approvals
        self.runs = 0
        # the live vault is a copy in the state dir, so accepted memories survive restarts
        self.vault_file = self.world.state / "vault.json"
        if not self.vault_file.exists():
            Vault.load(self.vault_path).save(self.vault_file)
        self.quarantine = Quarantine()
        self.clock = clock or time.time
        self.lock = threading.RLock() if not hasattr(self, 'lock') else self.lock
        self.threads = ThreadStore(self.world.state / "threads.json", clock=self.clock)
        self.memory = MemoryService(self.vault_file, self.quarantine, threads=self.threads,
                                    registry=self.world.registry, clock=self.clock, lock=self.lock)
        self.requester = "you"
        self.demo_author_email = demo_author_email
        self.payments_mode = payments_mode
        self.payments_dashboard = payments_dashboard  # where to look at the money, when the provider has a page for it
        self.pending: dict[str, dict] = {}  # runs waiting for the buyer to approve the hold
        # money is TEST money: a fake provider now, the PayPal sandbox client when credentials exist
        self.ledger = ledger or Ledger(FakeProvider(path=self.world.state / "provider.json"),
                                       path=self.world.state / "ledger.json", holdback_s=0)
        self.live: dict[str, object] = {}  # run id -> journal of a run in progress, so the page can show what is happening
        self.reports: dict[str, dict] = {}  # run_id -> full report (this session)
        self.history: list[dict] = []
        self.subs = Subscriptions(self.world.state / "subscriptions.json")  # monthly plans bought by the buyer
        self.chat = ChatService(self)
        self.studio = Studio(self)

    def vault(self) -> Vault:
        return self.memory.vault()

    def new_run_id(self) -> str:
        with self.lock:
            self.runs += 1
            return f"run-{self.runs}-{secrets.token_hex(3)}"

    def resolve_agent(self, key: str):
        if not isinstance(key, str):
            raise ValueError("unknown or revoked pack")
        rec = self.world.registry.records.get(key)
        if rec is None or rec not in self.world.registry.installable():
            raise ValueError("unknown or revoked pack")
        pack_dir = self.dirs.get(rec.digest)
        if pack_dir is None:
            raise ValueError("pack files on disk do not match the registered digest")
        return rec, pack_dir

    def hire(self, rec, run_id: str):
        price = rec.listing.max_cents  # the most this answer can cost (a monthly plan: the fee); the real price is worked out afterwards
        try:  # the hold comes last before starting; nothing is charged before a result exists
            with self.lock:
                row = self.ledger.hire(run_id, rec.key, self.author_payee(rec), self.requester, price, self.clock())
                if rec.listing.subscription:  # the plan starts once this payment settles
                    self.subs.register(run_id, rec, self.requester)
                return row
        except ProviderError as e:
            raise ValueError(f"payment could not be authorized: {e}") from e

    def _proposals(self) -> list[dict]:
        with self.lock:
            return self._proposals_locked()

    def _proposals_locked(self) -> list[dict]:
        return [{"id": p.id, "type": p.type, "text": p.text, "run_id": p.run_id} for p in self.quarantine.pending()]

    def state(self) -> dict:
        return {
            "market": self.world.market.ranked(),
            "memory": self.memory.overview(),
            "threads": self.threads.summaries(),
            "blocked_phrases": BLOCKED,
            "proposals": self._proposals(),
            "history": list(reversed(self.history[-20:])),
            "payments": self._payments_summary(),
            "model": "NVIDIA Nemotron on Nebius",
        }

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
                               "test_money": True, "events": []} if covered else self.payment(run_id))
            self.reports[run_id] = out
            while len(self.reports) > 100:
                self.reports.pop(next(iter(self.reports)))
            del self.history[:-100]
            self.history.append({"run_id": run_id, "pack": f"{rep.pack_id} v{rep.version}", "outcome": rep.outcome,
                                 "summary": rep.summary, "n": self.runs})
        return out

    def author_payee(self, rec) -> str:
        """Where this author is paid: their listing email, else the demo author email, else a key prefix."""
        return rec.listing.payout_email or self.demo_author_email or rec.publisher_key[:8]

    # -- money ------------------------------------------------------------------------------------
    def _settle_outcome(self, rec, run_id: str, rep) -> None:
        now = self.clock()
        if rep.outcome == "COMPLETE":
            self.ledger.result_ready(run_id, now)  # floor fee captured; the requester decides on the rest
        elif rep.outcome == "KILLED":
            why = rep.broker_events[0]["kind"] if rep.broker_events else "evidence of theft"
            self.ledger.kill(run_id, now, why)  # a held claim, never a final void of delivered work
            if self.world.market.status(rec) == "flagged":
                # the Certifier independently reproduced a violation for this exact pack digest
                self.ledger.adjudicate(run_id, True, now)
        else:
            self.ledger.fail_infra(run_id, now, f"no usable result ({rep.outcome})")

    def payment(self, run_id: str) -> dict:
        row = self.ledger.rows[run_id]
        return {
            "state": row.state, "price": row.price, "floor": row.floor, "captured": row.captured(),
            "refunded": sum(c["amount"] for c in row.captures if c["id"] in row.refunded),
            "accept_by": row.accept_by, "payout": row.payout, "test_money": True,
            "events": [{"to": e["to"], "why": e["why"]} for e in row.events],
        }

    def _payments_summary(self) -> dict:
        with self.lock:
            try:
                self.ledger.tick(self.clock())
                self.ledger.release_payouts(self.clock())
            except (ProviderError, PendingError):
                pass  # the provider is slow; show what we know and try again on the next refresh
            summary = self.ledger.summary()
            on_hold = sum(max(0, r.price - r.captured() - sum(c["amount"] for c in r.captures if c["id"] in r.refunded))
                          for r in self.ledger.rows.values() if r.state not in TERMINAL and r.state != "AWAITING_APPROVAL")
            summary["on_hold"] = on_hold
        return {**summary, "test_money": True, "provider": self.payments_mode, "holdback": "demo holdback 0 s; production would hold for days"}

    STATE_WORDS = {"AWAITING_APPROVAL": "Waiting for you to approve the hold", "AUTHORIZED": "Hold placed", "RUNNING": "The helper is working",
                   "RESULT_READY": "Answer delivered; the rest is paid when you keep going", "SETTLED": "Paid", "SETTLED_REJECTED": "You said not helpful: deposit only",
                   "DISPUTE_HOLD": "On hold while it is checked", "DISPUTE_UPHELD": "Refunded: the helper was caught cheating", "VOIDED": "Not charged"}

    def receipts(self) -> dict:
        """Every payment as a plain receipt: who was hired, for which chat, what moved, and why the state is what it is."""
        with self.lock:
            chats = {rid: t.title for t in self.threads.threads.values() for rid in t.runs}
            items = []
            for row in list(self.ledger.rows.values())[-100:]:
                rec = self.world.registry.records.get(row.pack_key)
                refunded = sum(c["amount"] for c in row.captures if c["id"] in row.refunded)
                items.append({"run_id": row.run_id, "helper": rec.id.replace("-", " ").title() if rec else row.pack_key, "chat": chats.get(row.run_id, ""),
                              "price": row.price, "state": row.state, "state_text": self.STATE_WORDS.get(row.state, row.state), "captured": row.captured(),
                              "refunded": refunded, "payout": {"status": row.payout["status"], "amount": row.payout["amount"]},
                              "author": row.author if "@" in row.author else "", "reference": row.auth_id or "",
                              "when": row.events[0]["t"] if row.events else 0,
                              "events": [{"t": e["t"], "to": self.STATE_WORDS.get(e["to"], e["to"]), "why": e["why"]} for e in row.events]})
        items.sort(key=lambda i: -i["when"])
        plans = []
        for p in self.subs.listing(self.requester, self.ledger, self.clock()):
            plans.append({"helper": p["helper"].replace("-", " ").title(), "key": p["key"], "pending": bool(p.get("pending")), "included": p["included"],
                          "used": p.get("used", 0), "left": p.get("left", p["included"]), "until": p.get("until", 0), "running": bool(p.get("running"))})
        return {"mode": self.payments_mode, "dashboard": self.payments_dashboard, "summary": self._payments_summary(), "items": items, "plans": plans}

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

    def decide(self, body: dict) -> dict:
        if body.get("action") == "accept":
            return self.memory.accept_proposal(str(body.get("id", "")))
        if body.get("action") == "reject":
            return self.memory.reject_proposal(str(body.get("id", "")))
        raise ValueError("action must be accept or reject")

    def revert(self, body: dict) -> dict:
        return self.memory.revert_run(str(body.get("run_id", "")))

    def memory_change(self, body: dict) -> dict:
        action = body.get("action")
        if action == "add":
            return self.memory.add(str(body.get("type", "note")), str(body.get("text", "")), str(body.get("sensitivity", "low")), str(body.get("shelf", "")), str(body.get("title", "")))
        if action == "add_many":
            return self.memory.add_many(body.get("items"), str(body.get("sensitivity", "low")), str(body.get("type", "note")), str(body.get("shelf", "")))
        if action == "update":
            return self.memory.update(str(body.get("id", "")), text=body.get("text"), sensitivity=body.get("sensitivity"), type=body.get("type"), path=body.get("shelf"), title=body.get("title"))
        if action == "delete":
            return self.memory.delete(str(body.get("id", "")))
        if action == "restore":
            return self.memory.restore(str(body.get("id", "")))
        if action == "empty_trash":
            return self.memory.empty_trash()
        if action == "restore_version":
            return self.memory.restore_version(str(body.get("id", "")), body.get("index"))
        if action == "bulk":
            return self.memory.bulk(body.get("ids"), str(body.get("op", "")), shelf=body.get("shelf"), level=body.get("level"))
        if action == "restore_backup":
            return self.memory.restore_backup(body.get("backup"))
        if action == "move_shelf":
            return self.memory.move_shelf(str(body.get("from", "")), str(body.get("to", "")))
        if action == "shelf_note":
            return self.memory.set_label(str(body.get("shelf", "")), body.get("text", ""))
        raise ValueError("that is not something memory can do")


POST_ROUTES = {
    "/api/run": lambda a, b: a.run(b),
    "/api/run/continue": lambda a, b: a.continue_run(b),
    "/api/proposal": lambda a, b: a.decide(b),
    "/api/settle": lambda a, b: a.settle(b),
    "/api/revert": lambda a, b: a.revert(b),
    "/api/memory": lambda a, b: a.memory_change(b),
    "/api/threads": lambda a, b: a.chat.create(b),
    "/api/thread/settings": lambda a, b: a.chat.settings(b),
    "/api/thread/send": lambda a, b: a.chat.send(b),
    "/api/thread/cancel": lambda a, b: a.chat.cancel_pending(b),
    "/api/thread/reject": lambda a, b: a.chat.reject(b),
    "/api/thread/forget": lambda a, b: a.chat.forget(b),
    "/api/thread/clear": lambda a, b: a.chat.clear(b),
    "/api/thread/delete": lambda a, b: a.chat.delete(b),
    "/api/subscription/cancel": lambda a, b: {"cancelled": a.subs.cancel(a.requester, str(b.get("key", "")))},
    "/api/studio/create": lambda a, b: a.studio.create(b.get("id"), b.get("template")),
    "/api/studio/save": lambda a, b: a.studio.save(b.get("id"), b),
    "/api/studio/delete": lambda a, b: a.studio.delete(b.get("id")),
    "/api/studio/try": lambda a, b: a.studio.try_it(b.get("id"), b.get("task"), b.get("shelves")),
    "/api/studio/publish": lambda a, b: a.studio.publish(b.get("id"), b, b.get("payout_email", "")),
    "/api/studio/retest": lambda a, b: a.studio.retest(b.get("key")),
    "/api/studio/retire": lambda a, b: a.studio.retire(b.get("key")),
    "/api/studio/price": lambda a, b: a.studio.set_price(b.get("key"), b, b.get("payout_email", "")),
}


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        timeout = 15  # a client that stalls mid-request cannot pin a worker forever

        def log_message(self, *a):  # quiet
            pass

        def _host_ok(self) -> bool:
            m = HOST_RE.match((self.headers.get("Host") or "").strip().lower())
            return bool(m) and m.group(1) in LOCAL_HOSTS

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data:; connect-src 'self'; "
                                                         "font-src 'self' data:; img-src 'self' data:; frame-ancestors 'none'")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            m = STATIC_PATH.match(self.path.split("?")[0])
            if m:  # only plain file names inside static/ (and static/fonts/) with a known type, never a path that climbs out
                f = STATIC / m.group(1)
                if f.suffix in STATIC_TYPES and f.is_file() and f.resolve().is_relative_to(STATIC.resolve()):
                    return self._send(200, f.read_bytes(), STATIC_TYPES[f.suffix])
                return self._json(404, {"error": "not found"})
            if self.path in ("/", "/index.html"):
                html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", app.token)
                return self._send(200, html.encode(), "text/html; charset=utf-8")
            if self.path == "/api/state":
                return self._json(200, app.state())
            if self.path.split("?")[0] in ("/paypal/return", "/paypal/cancel"):
                ok = self.path.startswith("/paypal/return")
                note = ("You approved the hold. This tab can be closed: the console carries on by itself."
                        if ok else "You cancelled. Nothing was held or charged. You can close this tab.")
                script = ("<script>try{const c=new BroadcastChannel('agent-bridge-paypal');c.postMessage('" + ("approved" if ok else "cancelled") + "');c.close();}catch(e){}"
                          "try{localStorage.setItem('agent-bridge-paypal','" + ("approved" if ok else "cancelled") + ":'+Date.now())}catch(e){}</script>")
                return self._send(200, ("<!doctype html><meta charset=utf-8><title>agent-bridge</title>"
                                        "<body style='font:16px system-ui;padding:40px'>" + note + script + "</body>").encode(),
                                  "text/html; charset=utf-8")
            if self.path.split("?")[0] == "/api/agent":
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                try:
                    return self._json(200, app.world.market.profile((q.get("key") or [""])[0]))
                except MarketError as e:
                    return self._json(404, {"error": str(e)})
            if self.path.startswith("/api/report/"):
                with app.lock:
                    rep = app.reports.get(self.path.rsplit("/", 1)[1])
                return self._json(200, rep) if rep else self._json(404, {"error": "unknown run"})
            route = self.path.split("?")[0]
            q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
            try:
                if route == "/api/threads":
                    return self._json(200, {"threads": app.threads.summaries()})
                if route == "/api/thread":
                    return self._json(200, app.chat.view(q.get("id", "")))
                if route == "/api/thread/context":
                    return self._json(200, app.chat.context(q.get("id", ""), q.get("draft", "")[:1000]))
                if route == "/api/studio":
                    return self._json(200, app.studio.list())
                if route == "/api/studio/helper":
                    return self._json(200, app.studio.get(q.get("id", "")))
                if route == "/api/payments":
                    return self._json(200, app.receipts())
                if route == "/api/office":
                    return self._json(200, app.chat.office())
                if route == "/api/thread/progress":
                    return self._json(200, app.chat.progress(q.get("id", "")))
                if route == "/api/how":
                    with app.lock:
                        rep = app.reports.get(q.get("run_id", ""))
                    if rep is None:
                        return self._json(404, {"error": "the details of this answer are no longer kept"})
                    return self._json(200, {"steps": how_made(rep["steps"])})
                if route == "/api/match":
                    return self._json(200, {"matches": app.world.market.match(q.get("q", "")[:300])})
                if route == "/api/memory":
                    ids = [x for x in q.get("ids", "").split(",") if x][:100] if "ids" in q else None
                    return self._json(200, {"items": app.memory.list(shelf=q.get("shelf") or None, ids=ids, q=q.get("q", "")[:200],
                                                                     offset=int(q.get("offset", "0") or 0), limit=int(q.get("limit", "30") or 30))})
                if route == "/api/memory/trash":
                    return self._json(200, {"items": app.memory.trash()})
                if route == "/api/memory/history":
                    return self._json(200, {"versions": app.memory.history(q.get("id", ""))})
                if route == "/api/memory/export":
                    if self.headers.get("X-Bridge-Token") != app.token:  # a backup holds secret notes, so it needs the page's own token
                        return self._json(403, {"error": "forbidden"})
                    return self._json(200, app.memory.export_backup())
                if route == "/api/memory/tree":
                    return self._json(200, app.memory.overview())
            except (ThreadError, ValueError) as e:
                return self._json(404, {"error": str(e)})
            self._json(404, {"error": "not found"})

        def do_POST(self):
            # always consume the (bounded) body first, so an early 403 never resets the client's connection
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n > 400000:
                left = min(n, 2_000_000)  # drain a bounded amount so the client sees the 413, not a reset
                while left > 0:
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                self.close_connection = True
                return self._json(413, {"error": "too large"})
            raw = self.rfile.read(n) if n > 0 else b""
            if not self._host_ok() or self.headers.get("X-Bridge-Token") != app.token:
                return self._json(403, {"error": "forbidden"})
            try:
                body = json.loads(raw or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("the request must be a JSON object")
                if self.path == "/api/star":
                    stars = app.world.registry.star(str(body["key"]), app.requester)
                    return self._json(200, {"stars": stars})
                fn = POST_ROUTES.get(self.path)
                if fn is not None:
                    return self._json(200, fn(app, body))
                self._json(404, {"error": "not found"})
            except ProviderError:
                self._json(502, {"error": "the payment service refused this. Nothing else was changed."})
            except ChatBusy as e:
                self._json(409, {"error": str(e)})
            except (ValueError, KeyError) as e:  # includes ThreadError and MemoryChangeError
                self._json(400, {"error": str(e)})
            except PendingError as e:
                self._json(503, {"error": "the payment provider has not confirmed yet; try again shortly"})
            except Exception as e:  # never leak internals or keys to the page
                self._json(500, {"error": f"run failed: {type(e).__name__}"})

    return H


def serve(app: App, port: int = 8787) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
