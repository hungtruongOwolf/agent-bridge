"""The socket side: checks who is asking, serves the page and its files, and hands every API address to the router.
All safety rules live here in one place: local host only, the page's token on every change, bounded bodies, nothing internal in an error."""
from __future__ import annotations

import json
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ...chat.service import ChatBusy
from ...chat.threads import ThreadError
from ...hub.market import MarketError
from ...payments.ledger import PendingError
from ...payments.provider import ProviderError
from .router import HttpError, Reply, Request, Router

STATIC = Path(__file__).resolve().parent.parent / "static"
STATIC_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".woff2": "font/woff2",
                ".txt": "text/plain; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}
STATIC_PATH = re.compile(r"^/static/((?:(?:fonts|vendor/[a-z0-9-]+|js(?:/[a-z0-9_-]+)?)/)?[a-z0-9][a-z0-9_.-]*)$")
# addresses the console draws itself (the browser asks for them on reload or when a link is opened); each serves the same page
PAGE_PATH = re.compile(r"^/(?:hire|chats/[^/]+|helpers(?:/[^/]+){0,2}|memory(?:/.*)?|market/[^/]+|wallet|earnings|help|404)/?$")
HOST_RE = re.compile(r"^(\[[0-9a-f:]+\]|[a-z0-9.-]+)(?::[0-9]{1,5})?$")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
MAX_BODY = 400_000
CSP = ("default-src 'self' 'unsafe-inline' data:; connect-src 'self'; "
       "font-src 'self' data:; img-src 'self' data:; frame-ancestors 'none'")


def make_handler(app, router: Router):
    class H(BaseHTTPRequestHandler):
        timeout = 15  # a client that stalls mid-request cannot pin a worker forever

        def log_message(self, *a):  # quiet
            pass

        # ---- answering -------------------------------------------------------------------------
        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _reply(self, out):
            if isinstance(out, Reply):
                body = out.body if isinstance(out.body, (bytes, bytearray)) else json.dumps(out.body, ensure_ascii=False).encode()
                return self._send(out.status, bytes(body), out.ctype)
            self._json(200, out)

        # ---- who is asking ---------------------------------------------------------------------
        def _host_ok(self) -> bool:
            m = HOST_RE.match((self.headers.get("Host") or "").strip().lower())
            return bool(m) and m.group(1) in LOCAL_HOSTS

        # ---- the page and its files ------------------------------------------------------------
        def _page_or_file(self, path: str) -> bool:
            m = STATIC_PATH.match(path)
            if m:  # only plain file names inside static/ (and static/fonts, static/js) with a known type, never a path that climbs out
                f = STATIC / m.group(1)
                if f.suffix in STATIC_TYPES and f.is_file() and f.resolve().is_relative_to(STATIC.resolve()):
                    self._send(200, f.read_bytes(), STATIC_TYPES[f.suffix])
                else:
                    self._json(404, {"error": "not found"})
                return True
            if path in ("/", "/index.html") or PAGE_PATH.match(path):
                html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", app.token)
                self._send(200, html.encode(), "text/html; charset=utf-8")
                return True
            return False

        # ---- the API ---------------------------------------------------------------------------
        def _dispatch(self, method: str, body: dict | None):
            parts = urllib.parse.urlsplit(self.path)
            found = router.find(method, parts.path)
            if found is None:
                return self._json(404, {"error": "not found"})
            route, params = found
            if route.token and self.headers.get("X-Bridge-Token") != app.token:
                return self._json(403, {"error": "forbidden"})
            query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
            req = Request(method, parts.path, query, body or {}, self.headers, params)
            try:
                self._reply(route.fn(req))
            except HttpError as e:
                self._json(e.status, {"error": e.message})
            except ProviderError as e:
                app.log_error(self.path, e)
                self._json(502, {"error": "the payment service said: " + str(e)[:160] + ". Nothing else was changed."})
            except ChatBusy as e:
                self._json(409, {"error": str(e)})
            except (ThreadError, MarketError) as e:  # an unknown thing was asked for
                self._json(404 if method == "GET" else 400, {"error": str(e)})
            except (ValueError, KeyError) as e:  # includes MemoryChangeError; on a read it means there is no such thing
                self._json(404 if method == "GET" else 400, {"error": str(e)})
            except PendingError:
                self._json(503, {"error": "the payment provider has not confirmed yet; try again shortly"})
            except Exception as e:  # never leak internals or keys to the page
                app.log_error(self.path, e)
                self._json(500, {"error": f"run failed: {type(e).__name__}"})

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if self._page_or_file(self.path.split("?")[0]):
                return
            self._dispatch("GET", None)

        def do_POST(self):
            # always consume the (bounded) body first, so an early 403 never resets the client's connection
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n > MAX_BODY:
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
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            self._dispatch("POST", body)

    return H


def serve_router(app, router: Router, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, router))
