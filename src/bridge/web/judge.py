"""Judge mode: the real application, open to the public, with no keys and nothing shared between visitors.

    bridge serve --judge-mode [--host 0.0.0.0] [--allowed-host NAME ...] [--port N]

What is real: the server, the ledger, the PayPal client code, the Result Guard, the memory broker.
What is not: the answers come from a recorded model (engine/recorded.py) unless a Nebius key is in the environment AND
`--judge-real-model` is given, in which case a hard hourly cap (everyone, and each visitor) protects the key and
the recorded model answers once a cap is reached. Payments go to a practice server that copies PayPal's API; it runs
inside this process and is mounted under /practice, because a host such as Render exposes a single port. Test money.

Each visitor (cookie) gets an App of their own in a folder under one temp root: own ledger, chats, memory (seeded from
the read-only demo vault) and practice PayPal. At most `max_sessions` live at once (least recently used goes first) and
an idle session ends after `ttl_s`. Helpers that run code or search the web are refused.
"""
from __future__ import annotations

import collections
import hashlib
import http.cookies
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ..engine.nebius import NebiusModel
from ..engine.recorded import PROVIDER as RECORDED_PROVIDER, RecordedModel
from ..hub.certifier import Certifier, sales_risk_suite
from ..hub.market import Marketplace
from ..hub.registry import Registry
from ..hub.suites import available, load_suite
from ..pack import signing
from ..pack.digest import tree_digest
from ..payments.ledger import Ledger
from ..payments.paypal import PayPalSandbox
from ..payments.paypal_mock import MOCK_ID, MOCK_SECRET, MockPayPal, MockState, buyer_decision, checkout_page, state_page
from ..world import World, _load_or_create_key
from .api.transport import HOST_RE, MAX_BODY, PAGE_PATH, STATIC_PATH, make_handler

LOCAL = ("127.0.0.1", "localhost", "[::1]")
COOKIE = "agora_sid"
BANNER_RECORDED = "Judge mode: answers come from a recorded model; payments use the practice PayPal server. Test money."
BANNER_LIVE = ("Judge mode: answers come from a live model with a small hourly limit, then from a recorded model; "
               "payments use the practice PayPal server. Test money.")
REPO = Path(__file__).resolve().parents[3]
REFUSED = ("This public copy does not run helpers that run code or search the web. Pick another helper.")


@dataclass
class JudgeConfig:
    allowed_hosts: tuple = ()
    packs_dir: Path = REPO / "examples" / "packs"
    vault_path: Path = REPO / "examples" / "vault-library.json"
    template: Path = REPO / "examples" / "judge"
    root: Path | None = None  # everything is written under here; a fresh temp folder when None
    max_sessions: int = 50
    ttl_s: float = 7200
    real_model: bool = False
    model_per_hour: int = 60  # live-model calls an hour for everyone
    model_per_visitor_hour: int = 12
    new_per_ip_minute: int = 20
    new_per_minute: int = 120
    clock: object = time.time
    history: bool = True  # every visitor starts with a sample past (see judge_seed.py)
    history_max_age_s: float = 12 * 3600  # the template is rebuilt when older, so "waiting for a decision" and "last days" stay true


class Window:
    """Counts events in the last `span` seconds."""

    def __init__(self, span: float, clock):
        self.span, self.clock, self.t = span, clock, collections.deque()

    def _trim(self):
        now = self.clock()
        while self.t and now - self.t[0] >= self.span:
            self.t.popleft()

    def count(self) -> int:
        self._trim()
        return len(self.t)

    def add(self):
        self.t.append(self.clock())


class ModelCap:
    """A hard ceiling on live-model calls: per hour for everyone and per hour for each visitor."""

    def __init__(self, per_hour: int, per_visitor: int, clock):
        self.per_hour, self.per_visitor, self.clock = per_hour, per_visitor, clock
        self.all = Window(3600, clock)
        self.each: dict[str, Window] = {}
        self.lock = threading.Lock()

    def _win(self, vid):
        return self.each.setdefault(vid, Window(3600, self.clock))

    def room(self, vid: str) -> bool:
        with self.lock:
            return self.all.count() < self.per_hour and self._win(vid).count() < self.per_visitor

    def take(self, vid: str) -> bool:
        with self.lock:
            w = self._win(vid)
            if self.all.count() >= self.per_hour or w.count() >= self.per_visitor:
                return False
            self.all.add()
            w.add()
            return True

    def forget(self, vid: str):
        with self.lock:
            self.each.pop(vid, None)


class JudgeModel:
    """Recorded answers; the live model only when it is switched on and the caps still have room."""

    def __init__(self, hub, vid: str):
        self.hub, self.vid, self.recorded = hub, vid, RecordedModel()

    @property
    def provider(self):
        if self.hub.live is not None and self.hub.cap.room(self.vid):
            return self.hub.live.provider
        return RECORDED_PROVIDER

    def complete(self, prompt, inputs):
        if self.hub.live is not None and self.hub.cap.take(self.vid):
            return self.hub.live.complete(prompt, inputs)
        return self.recorded.complete(prompt, inputs)


class RefusingCell:
    """No containers here (and no Docker inside Docker): code never runs."""

    def run(self, script, inputs):
        raise RuntimeError("code is not run in judge mode")


class NoWeb:
    def search(self, query):
        raise RuntimeError("web search is off in judge mode")

    product_search = search


@dataclass
class Visitor:
    vid: str
    app: object
    router: object
    seen: float
    dir: Path = None


class TooManyNew(Exception):
    pass


def _inproc(api: MockPayPal):
    """The PayPal client's transport, pointed straight at the practice server in this process."""
    import json

    def http(method, url, headers, body):
        path = urllib.parse.urlsplit(url).path
        h = {k.lower(): v for k, v in headers.items()}
        data = json.loads(body) if body and "json" in h.get("content-type", "") else None
        status, out = api.call(method, path, h, data)
        return status, (out if status != 204 else {})
    return http


def _close_databases(folder: Path) -> None:
    """Close every SQLite file open under a visitor's folder (it cannot be removed otherwise on Windows, and file handles would pile up)."""
    import gc
    from ..storage.db import Database
    for o in gc.get_objects():
        if isinstance(o, Database):
            try:
                if Path(o.path).is_relative_to(folder):
                    o.close()
            except Exception:
                pass


class JudgeHub:
    def __init__(self, cfg: JudgeConfig):
        self.cfg = cfg
        self.clock = cfg.clock
        self.root = Path(cfg.root) if cfg.root else Path(tempfile.mkdtemp(prefix="agora-judge-"))
        (self.root / "v").mkdir(parents=True, exist_ok=True)
        hosts = set(LOCAL) | {h.strip().lower() for h in cfg.allowed_hosts if h.strip()}
        ext = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
        if ext:
            hosts.add(ext)
        self.hosts = hosts
        self.sessions: collections.OrderedDict[str, Visitor] = collections.OrderedDict()
        self.lock = threading.RLock()
        self.cap = ModelCap(cfg.model_per_hour, cfg.model_per_visitor_hour, self.clock)
        key = os.environ.get("NEBIUS_API_KEY", "").strip()
        self.live = NebiusModel(key) if (cfg.real_model and key) else None
        self.banner = BANNER_LIVE if self.live is not None else BANNER_RECORDED
        self.trusted_pub = (cfg.template / "certifier.pub").read_text(encoding="utf-8").strip()
        self.suites = {n: load_suite(n) for n in available()}
        self.pack_dirs = {tree_digest(d): d for d in sorted((cfg.template / "packs").iterdir()) if (d / "pack.yaml").exists()}
        self.per_ip: dict[str, Window] = {}
        self.minute = Window(60, self.clock)
        self.seed_dir: Path | None = None
        self.seed_at = 0.0
        self.seed_n = 0
        self.refresh_seed()

    # -- sessions --------------------------------------------------------------------------------
    @staticmethod
    def vid_of(sid: str) -> str:
        return hashlib.sha256(sid.encode()).hexdigest()[:24]  # the folder name never reveals the cookie

    def get(self, sid: str | None) -> Visitor | None:
        if not sid:
            return None
        with self.lock:
            v = self.sessions.get(sid)
            if v is None:
                return None
            if self.clock() - v.seen > self.cfg.ttl_s:
                self._drop(sid)
                return None
            v.seen = self.clock()
            self.sessions.move_to_end(sid)
            return v

    def create(self, ip: str) -> tuple[str, Visitor]:
        with self.lock:
            w = self.per_ip.setdefault(ip, Window(60, self.clock))
            if w.count() >= self.cfg.new_per_ip_minute or self.minute.count() >= self.cfg.new_per_minute:
                raise TooManyNew()
            w.add()
            self.minute.add()
            if len(self.per_ip) > 2000:
                self.per_ip = {k: x for k, x in self.per_ip.items() if x.count()}
            now = self.clock()
            for sid in [s for s, v in self.sessions.items() if now - v.seen > self.cfg.ttl_s]:
                self._drop(sid)
            sid = secrets.token_urlsafe(24)
            v = self._build(sid)
            self.sessions[sid] = v
            while len(self.sessions) > self.cfg.max_sessions:
                self._drop(next(iter(self.sessions)))  # least recently used
            return sid, v

    def _drop(self, sid: str):
        v = self.sessions.pop(sid, None)
        if v is None:
            return
        self.cap.forget(v.vid)
        _close_databases(v.dir)
        shutil.rmtree(v.dir, ignore_errors=True)

    def _assemble(self, d: Path, model_factory, clock=None):
        """An App over the folder `d`: the keys, registry and attestations in it (made when missing), a practice PayPal and a ledger of its own."""
        from .server import App

        for name in ("registry.json", "attestations.json"):
            if not (d / name).exists():
                shutil.copy2(self.cfg.template / name, d / name)
        author, cert = _load_or_create_key(d / "author.key"), _load_or_create_key(d / "certifier.key")
        registry = Registry(d / "registry.json")
        market = Marketplace(registry, {self.trusted_pub, signing.public_b64(cert)}, d / "attestations.json")
        world = World(d, registry, market, author, Certifier(cert, sales_risk_suite(), runs_per_task=4, suites=self.suites))
        api = MockPayPal("/practice", MockState(d / "paypal-mock.json"))
        ledger = Ledger(PayPalSandbox(MOCK_ID, MOCK_SECRET, base_url="http://127.0.0.1:19", http=_inproc(api),
                                      return_url="/paypal/return", cancel_url="/paypal/cancel"), path=d / "ledger-paypal-mock.json")
        app = App(world, self.cfg.packs_dir, self.cfg.vault_path, self.root / "no.env", cell=RefusingCell(), model_factory=model_factory,
                  web=NoWeb(), ledger=ledger, clock=clock, demo_author_email="author@example.com", payments_mode="paypal-mock",
                  payments_dashboard="/practice/mock/state")
        app.dirs.update(self.pack_dirs)
        app.mock = api
        return app

    def refresh_seed(self) -> None:
        """Build the sample past once into a template folder. Visitors get a copy of it."""
        if not self.cfg.history:
            return
        from .judge_seed import StoryClock, tell_story

        self.seed_n += 1
        folder = self.root / f"seed-{self.seed_n}"
        folder.mkdir(parents=True)
        now = self.clock()
        recorded = RecordedModel()
        app = self._assemble(folder, lambda: recorded, StoryClock(now))
        tell_story(app, app.clock, now)
        _close_databases(folder)
        old, self.seed_dir, self.seed_at = self.seed_dir, folder, now
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)

    def _build(self, sid: str) -> Visitor:
        vid = self.vid_of(sid)
        d = self.root / "v" / vid
        if self.seed_dir is not None:
            if self.clock() - self.seed_at > self.cfg.history_max_age_s:
                self.refresh_seed()
            shutil.copytree(self.seed_dir, d)
        else:
            d.mkdir(parents=True)
        model = JudgeModel(self, vid)
        app = self._assemble(d, lambda: model)
        self._adapt(app)
        return Visitor(vid, app, app.router(), self.clock(), d)

    def _adapt(self, app):
        """Make the words true for this copy, and refuse what it cannot do."""
        resolve = app.runs.resolve_agent

        def guarded(key):
            rec, pack_dir = resolve(key)
            if rec.caps.get("code") or rec.caps.get("web"):
                raise ValueError(REFUSED)
            return rec, pack_dir
        app.runs.resolve_agent = guarded
        state = app.state
        label = "A recorded model (judge mode)" if self.live is None else "A live model with an hourly limit, else a recorded model (judge mode)"
        app.state = lambda: {**state(), "model": label}
        context = app.chat.context
        where = ("the recorded model that runs inside this server; nothing is sent to any model service." if self.live is None else
                 "a live model while the hourly limit allows, otherwise the recorded model inside this server.")

        def ctx(*a, **k):
            out = context(*a, **k)
            if isinstance(out, dict) and "goes_to_the_brain" in out:
                out["goes_to_the_brain"] = ("To write an answer, your message, the files that match it and the last " + str(out.get("history_turns", 0)) +
                                            " messages of this chat are sent to " + where + " The helper itself cannot send anything anywhere.")
            return out
        app.chat.context = ctx


def _banner_html(text: str) -> str:
    return ('<div id="judgebar" style="position:fixed;left:0;right:0;bottom:0;z-index:2147483000;background:#1A1320;color:#FFF8E7;'
            'font:13px/1.35 system-ui,sans-serif;padding:6px 12px;text-align:center">' + text +
            '</div><style>body{padding-bottom:36px}</style>')


def make_judge_handler(hub: JudgeHub):
    ctx = threading.local()

    class AppProxy:
        def __getattr__(self, name):
            return getattr(ctx.visitor.app, name)

    class RouterProxy:
        def find(self, method, path):
            return ctx.visitor.router.find(method, path)

    Base = make_handler(AppProxy(), RouterProxy())
    secure = bool(os.environ.get("RENDER"))

    class J(Base):
        _cookie = None

        # -- who is asking -----------------------------------------------------------------------
        def _host_ok(self) -> bool:
            m = HOST_RE.match((self.headers.get("Host") or "").strip().lower())
            return bool(m) and m.group(1) in hub.hosts

        def _sid(self) -> str | None:
            raw = self.headers.get("Cookie") or ""
            try:
                c = http.cookies.SimpleCookie(raw)
            except http.cookies.CookieError:
                return None
            return c[COOKIE].value if COOKIE in c else None

        def _ip(self) -> str:
            xff = (self.headers.get("X-Forwarded-For") or "").split(",")[-1].strip()
            return xff[:64] or self.client_address[0]

        def _origin(self) -> str:
            proto = "https" if (secure or self.headers.get("X-Forwarded-Proto") == "https") else "http"
            return f"{proto}://{(self.headers.get('Host') or '').strip().lower()}"  # the Host was already checked against the allowed names

        def _see(self, v):
            """The console only shows approval links that are full addresses, so the practice PayPal is told where this visitor reached us."""
            if v is not None:
                v.app.mock.base = self._origin() + "/practice"
            return v

        def end_headers(self):
            if self._cookie:
                self.send_header("Set-Cookie", self._cookie)
            super().end_headers()

        def _send(self, code, body, ctype):
            if ctype.startswith("text/html") and b"<body" in body and b"judgebar" not in body:
                body = re.sub(rb"(<body[^>]*>)", lambda m: m.group(1) + _banner_html(hub.banner).encode(), body, count=1)
            super()._send(code, body, ctype)

        def _no_session(self):
            self.close_connection = True
            self._json(403, {"error": "your session ended; reload the page to start again"})

        def _visitor_for_page(self):
            v = hub.get(self._sid())
            if v is not None:
                return self._see(v)
            try:
                sid, v = hub.create(self._ip())
            except TooManyNew:
                self._json(503, {"error": "too many new visitors right now; try again in a minute"})
                return None
            flags = "Path=/; HttpOnly; SameSite=Lax; Max-Age=%d" % int(hub.cfg.ttl_s) + ("; Secure" if secure or self.headers.get("X-Forwarded-Proto") == "https" else "")
            self._cookie = f"{COOKIE}={sid}; {flags}"
            return self._see(v)

        # -- the practice PayPal, mounted under /practice ----------------------------------------
        def _practice(self, method: str, path: str):
            v = hub.get(self._sid())
            if v is None:
                return self._send(403, b"<!doctype html><meta charset=utf-8><p>Your session ended. Go back to the app and start again.</p>", "text/html; charset=utf-8")
            sub = path[len("/practice"):] or "/"
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            token = q.get("token", [""])[0]
            api = v.app.mock
            if method == "GET":
                if sub == "/checkoutnow":
                    status, page = checkout_page(api, token, "/practice")
                    return self._send(status, page, "text/html; charset=utf-8")
                if sub == "/mock/state":
                    return self._send(200, state_page(api), "text/html; charset=utf-8")
                return self._json(404, {"error": "not found"})
            if sub in ("/checkoutnow/approve", "/checkoutnow/cancel"):
                origin = self.headers.get("Origin")
                if origin and (urllib.parse.urlsplit(origin).hostname or "") not in {h.strip("[]") for h in hub.hosts}:
                    return self._json(403, {"error": "forbidden"})
                target = buyer_decision(api, "approve" if sub.endswith("approve") else "cancel", token)
                if not target:
                    return self._send(404, b"<!doctype html><meta charset=utf-8><p>That payment was not found.</p>", "text/html; charset=utf-8")
                self.send_response(303)
                self.send_header("Location", target)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self._json(404, {"error": "not found"})

        # -- requests ----------------------------------------------------------------------------
        def do_GET(self):
            self._cookie = None
            path = self.path.split("?")[0]
            if path == "/healthz":
                return self._json(200, {"ok": True})
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if path == "/practice" or path.startswith("/practice/"):
                return self._practice("GET", path)
            if STATIC_PATH.match(path):
                ctx.visitor = None
            elif path in ("/", "/index.html") or PAGE_PATH.match(path):
                ctx.visitor = self._visitor_for_page()
                if ctx.visitor is None:
                    return
            else:
                ctx.visitor = self._see(hub.get(self._sid()))
                if ctx.visitor is None:
                    return self._no_session()
            super().do_GET()

        def do_POST(self):
            self._cookie = None
            path = self.path.split("?")[0]
            if path.startswith("/practice/"):
                n = min(int(self.headers.get("Content-Length") or 0), MAX_BODY) if (self.headers.get("Content-Length") or "0").isdigit() else 0
                if n:
                    self.rfile.read(n)
                if not self._host_ok():
                    return self._json(403, {"error": "forbidden"})
                return self._practice("POST", path)
            ctx.visitor = self._see(hub.get(self._sid()))
            if ctx.visitor is None:
                return self._no_session()
            super().do_POST()  # host, token and body rules are the console's own

    return J


def serve_judge(cfg: JudgeConfig, host: str = "127.0.0.1", port: int = 8787) -> tuple[ThreadingHTTPServer, JudgeHub]:
    hub = JudgeHub(cfg)
    return ThreadingHTTPServer((host, port), make_judge_handler(hub)), hub
