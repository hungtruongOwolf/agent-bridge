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
from ..memory.broker import Lens
from ..memory.vault import Record, Vault
from ..pack.digest import tree_digest
from ..runner import run_pack
from ..world import World

STATIC = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


class LeakyModel:
    """Simulates a compromised model step that copies everything it can see."""

    def complete(self, prompt, inputs):
        return ModelReply({"summary": json.dumps(inputs, ensure_ascii=False), "risk": "high"}, tokens=100)


class App:
    def __init__(self, world: World, packs_dir: Path, vault_path: Path, env_file: Path, cell=None):
        self.world, self.vault_path, self.env_file, self.cell = world, Path(vault_path), Path(env_file), cell
        self.token = secrets.token_urlsafe(16)
        self.dirs = {tree_digest(d): d for d in sorted(Path(packs_dir).iterdir()) if (d / "pack.yaml").exists()}
        self.runs = 0

    def vault(self) -> Vault:
        return Vault([Record(**r) for r in json.loads(self.vault_path.read_text(encoding="utf-8"))])

    def state(self) -> dict:
        v = self.vault()
        return {
            "market": self.world.market.ranked(),
            "vault": [{"id": r.id, "type": r.type, "sensitivity": r.sensitivity, "text": r.text} for r in v.all()],
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
            model = NebiusModel(load_api_key(self.env_file))
        self.runs += 1
        rep = run_pack(pack_dir, self.vault(), Lens(types=types, max_sensitivity=sens), model,
                       seed=f"web-{self.runs}-{secrets.token_hex(4)}", cell=self.cell, expected_digest=rec.digest)
        return rep.__dict__


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
            if not self._host_ok() or self.headers.get("X-Bridge-Token") != app.token:
                return self._json(403, {"error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 20000:
                    return self._json(413, {"error": "too large"})
                body = json.loads(self.rfile.read(n) or b"{}")
                if self.path == "/api/run":
                    return self._json(200, app.run(body))
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
