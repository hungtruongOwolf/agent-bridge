"""Local web console: the composition root.

`App` builds every part once and wires them together; it holds no logic of its own. The parts:
  services/runs.py       running a helper and settling its money
  services/payments.py   payments worded for the buyer
  chat/, studio.py       conversations and building helpers
  memory/                the memory service
  routes/*.py            which address calls which part
  api/router.py          the router; api/transport.py the socket side with every safety rule

Binds to 127.0.0.1 only. Every POST needs the per-process token that only the served page knows, and
the Host header must be local, so another website in your browser cannot start runs that spend your
model key (CSRF) or reach the API through DNS rebinding.
"""
from __future__ import annotations

import secrets
import threading
import time
import traceback
from http.server import ThreadingHTTPServer
from pathlib import Path

from ..chat.plain import BLOCKED
from ..chat.service import ChatService
from ..chat.threads import ThreadStore
from ..engine.nebius import NebiusModel, load_api_key
from ..engine.tavily import TavilySearch, load_tavily_key
from ..memory.quarantine import Quarantine
from ..memory.service import MemoryService
from ..memory.vault import Vault
from ..pack.digest import tree_digest
from ..payments.ledger import Ledger
from ..payments.provider import FakeProvider
from ..payments.subscriptions import Subscriptions
from ..studio import Studio
from ..world import World
from .api.router import Router
from .api.transport import make_handler as _make_handler, serve_router
from .routes import chat as chat_routes, core, memory as memory_routes, payments as payment_routes, studio as studio_routes
from .services.clients import LazyModel, LazySearch, LeakyModel  # noqa: F401  (kept importable from here)
from .services.payments import PaymentsService
from .services.runs import RunService


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
        self.lock = threading.RLock()  # guards runs in flight, reports, history and pending approvals
        self.clock = clock or time.time
        self.requester = "you"
        self.demo_author_email = demo_author_email
        self.payments_mode = payments_mode
        self.payments_dashboard = payments_dashboard  # where to look at the money, when the provider has a page for it

        # memory: kept in the state dir (seeded once from the starter vault), so accepted memories survive restarts
        self.vault_file = self.world.state / "vault.json"  # the memory database sits beside it; an older JSON file of this name is imported once
        self.quarantine = Quarantine()
        self.threads = ThreadStore(self.world.state / "threads.json", clock=self.clock)
        self.memory = MemoryService(self.vault_file, self.quarantine, threads=self.threads,
                                    registry=self.world.registry, clock=self.clock, lock=self.lock, seed=self.vault_path)

        # money is TEST money: a fake provider now, the PayPal sandbox client when credentials exist
        self.ledger = ledger or Ledger(FakeProvider(path=self.world.state / "provider.json"),
                                       path=self.world.state / "ledger.json", holdback_s=0)
        self.subs = Subscriptions(self.world.state / "subscriptions.json")  # monthly plans bought by the buyer

        self.payments = PaymentsService(ledger=self.ledger, subs=self.subs, threads=self.threads, registry=self.world.registry,
                                        reports={}, lock=self.lock, clock=self.now, requester=self.requester,
                                        mode=payments_mode, dashboard=payments_dashboard)
        self.runs = RunService(registry=self.world.registry, market=self.world.market, dirs=self.dirs, vault=self.vault,
                               quarantine=self.quarantine, threads=self.threads, ledger=self.ledger, subs=self.subs,
                               payments=self.payments, lock=self.lock, clock=self.now, requester=self.requester,
                               payee=self.author_payee, model_factory=lambda: self.model_factory(), web=self.web, cell=cell)  # the factory is looked up on each run, so it can be swapped
        self.payments.reports = self.runs.reports  # a settled decision updates the report of that run
        self.chat = ChatService(self)
        self.runs.chat = self.chat
        self.studio = Studio(self)

    # -- short names the chat and studio parts use ------------------------------------------------
    pending = property(lambda self: self.runs.pending)
    live = property(lambda self: self.runs.live)
    reports = property(lambda self: self.runs.reports)
    history = property(lambda self: self.runs.history)

    def now(self) -> float:
        return self.clock()  # looked up on each call, so the clock can be swapped (tests move time)

    def new_run_id(self) -> str:
        return self.runs.new_run_id()

    def resolve_agent(self, key: str):
        return self.runs.resolve_agent(key)

    def hire(self, rec, run_id: str):
        return self.runs.hire(rec, run_id)

    def job(self, run_id: str, params: dict) -> dict:
        return self.runs.job(run_id, params)

    def receipts(self) -> dict:
        return self.payments.receipts()

    def vault(self) -> Vault:
        return self.memory.vault()

    def author_payee(self, rec) -> str:
        """Where this author is paid: their listing email, else the demo author email, else a key prefix."""
        return rec.listing.payout_email or self.demo_author_email or rec.publisher_key[:8]

    def log_error(self, where: str, exc: BaseException) -> None:
        """Keep the full story of an unexpected failure in <state>/errors.log, for the person running the console. Never sent to the page."""
        try:
            with open(self.world.state / "errors.log", "a", encoding="utf-8") as f:
                f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {where[:80]}\n" + "".join(traceback.format_exception(exc))[-3000:] + "\n")
        except OSError:
            pass

    def state(self) -> dict:
        with self.lock:
            proposals = [{"id": p.id, "type": p.type, "text": p.text, "run_id": p.run_id} for p in self.quarantine.pending()]
        return {
            "market": self.world.market.ranked(),
            "memory": self.memory.overview(),
            "threads": self.threads.summaries(),
            "blocked_phrases": BLOCKED,
            "proposals": proposals,
            "history": list(reversed(self.history[-20:])),
            "payments": self.payments.summary(),
            "model": "NVIDIA Nemotron on Nebius",
        }

    def router(self) -> Router:
        r = Router()
        for module in (core, memory_routes, chat_routes, studio_routes, payment_routes):
            module.register(r, self)
        return r


def make_handler(app: App):
    return _make_handler(app, app.router())


def serve(app: App, port: int = 8787) -> ThreadingHTTPServer:
    return serve_router(app, app.router(), port)
