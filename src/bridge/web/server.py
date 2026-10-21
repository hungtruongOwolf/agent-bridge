"""Local web console: marketplace, lens, run trace.

Binds to 127.0.0.1 only. Every POST needs the per-process token that only the served page knows, and
the Host header must be local, so another website in your browser cannot start runs that spend your
model key (CSRF) or reach the API through DNS rebinding.
"""
from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..engine.flowd import ModelReply
from ..engine.nebius import NebiusModel, load_api_key
from ..engine.tavily import TavilySearch, load_tavily_key
from ..memory.broker import Lens
from ..memory.quarantine import Quarantine, QuarantineError
from ..memory.vault import Vault
from ..pack.digest import tree_digest
from ..runner import run_pack
from ..world import World

STATIC = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


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
                 model_factory=None, web=None):
        self.world, self.vault_path, self.env_file, self.cell = world, Path(vault_path), Path(env_file), cell
        self.web = web or LazySearch(lambda: TavilySearch(load_tavily_key(self.env_file)))
        self.model_factory = model_factory or (lambda: NebiusModel(load_api_key(self.env_file)))
        self.token = secrets.token_urlsafe(16)
        roots = [Path(packs_dir), self.world.state / "candidates"]  # approved improvements live in candidates
        self.dirs = {tree_digest(d): d for r in roots if r.exists() for d in sorted(r.iterdir()) if (d / "pack.yaml").exists()}
        self.runs = 0
        # the live vault is a copy in the state dir, so accepted memories survive restarts
        self.vault_file = self.world.state / "vault.json"
        if not self.vault_file.exists():
            Vault.load(self.vault_path).save(self.vault_file)
        self.quarantine = Quarantine()

    def vault(self) -> Vault:
        return Vault.load(self.vault_file)

    def _proposals(self) -> list[dict]:
        return [{"id": p.id, "type": p.type, "text": p.text, "run_id": p.run_id} for p in self.quarantine.pending()]

    def state(self) -> dict:
        v = self.vault()
        return {
            "market": self.world.market.ranked(),
            "vault": [{"id": r.id, "type": r.type, "sensitivity": r.sensitivity, "text": r.text,
                       "trust": r.trust_tier, "from_run": (r.origin or {}).get("run_id")} for r in v.all()],
            "proposals": self._proposals(),
            "model": "NVIDIA Nemotron on Nebius",
        }

    def run(self, body: dict) -> dict:
        rec = self.world.registry.records.get(body.get("key", ""))
        if rec is None or rec not in self.world.registry.installable():
            raise ValueError("unknown or revoked pack")
        pack_dir = self.dirs.get(rec.digest)
        if pack_dir is None:
            raise ValueError("pack files on disk do not match the registered digest")
        types = frozenset(t for t in body.get("types", []) if isinstance(t, str))
        if not types:
            raise ValueError("choose at least one record type to share")
        sens = body.get("max_sensitivity", "medium")
        if sens not in ("low", "medium", "high"):
            raise ValueError("bad sensitivity")
        if body.get("model") == "leak":
            model = LeakyModel()
        else:
            model = LazyModel(self.model_factory)
        self.runs += 1
        run_id = f"run-{self.runs}-{secrets.token_hex(3)}"
        rep = run_pack(pack_dir, self.vault(), Lens(types=types, max_sensitivity=sens), model,
                       seed=run_id, cell=self.cell, expected_digest=rec.digest, run_id=run_id, web=self.web)
        out = dict(rep.__dict__)
        raw = out.pop("proposals_raw")
        added, problems = self.quarantine.add(run_id, rep.digest, raw) if rep.outcome == "COMPLETE" else ([], [])
        out["proposals"] = [{"id": p.id, "type": p.type, "text": p.text} for p in added]
        out["proposal_problems"] = problems
        return out

    def decide(self, body: dict) -> dict:
        try:
            if body.get("action") == "accept":
                v = self.vault()
                rec = self.quarantine.accept(body.get("id", ""), v)
                v.save(self.vault_file)
                return {"accepted": rec.id}
            if body.get("action") == "reject":
                self.quarantine.reject(body.get("id", ""))
                return {"rejected": body.get("id")}
        except QuarantineError as e:
            raise ValueError(str(e)) from e
        raise ValueError("action must be accept or reject")

    def revert(self, body: dict) -> dict:
        v = self.vault()
        out = self.quarantine.revert_run(str(body.get("run_id", "")), v)
        v.save(self.vault_file)
        return out


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0] if not (self.headers.get("Host") or "").startswith("[") \
                else "[::1]"
            return host in LOCAL_HOSTS

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data:; connect-src 'self'; "
                                                         "font-src 'self' data:; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if self.path in ("/", "/index.html"):
                html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", app.token)
                return self._send(200, html.encode(), "text/html; charset=utf-8")
            if self.path == "/api/state":
                return self._json(200, app.state())
            self._json(404, {"error": "not found"})

        def do_POST(self):
            # always consume the (bounded) body first, so an early 403 never resets the client's connection
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n > 20000:
                left = min(n, 1_000_000)  # drain a bounded amount so the client sees the 413, not a reset
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
                if self.path == "/api/run":
                    return self._json(200, app.run(body))
                if self.path == "/api/proposal":
                    return self._json(200, app.decide(body))
                if self.path == "/api/revert":
                    return self._json(200, app.revert(body))
                if self.path == "/api/star":
                    stars = app.world.registry.star(body["key"], str(body.get("user", "you"))[:40])
                    return self._json(200, {"stars": stars})
                self._json(404, {"error": "not found"})
            except (ValueError, KeyError) as e:
                self._json(400, {"error": str(e)})
            except Exception as e:  # never leak internals or keys to the page
                self._json(500, {"error": f"run failed: {type(e).__name__}"})

    return H


def serve(app: App, port: int = 8787) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
