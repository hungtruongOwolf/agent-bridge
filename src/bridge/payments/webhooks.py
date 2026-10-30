"""Outbound webhooks: a small JSON event when a payment settles, a payout is made, a refund happens or a dispute is resolved.

Set BRIDGE_WEBHOOK_URL (environment or .env) to receive them, for example from a Zapier "Catch Hook" trigger. Unset means off.
Optional BRIDGE_WEBHOOK_SECRET signs the exact body bytes with HMAC-SHA256 in the header `X-Agora-Signature: sha256=<hex>`.

Safety rules: the payload carries only the event name, run id, helper name, amounts in cents, status and time. It never
carries chat text, emails, memory content or the buyer/author identity. Delivery runs on a background thread with a short
timeout and two retries (backoff), so a slow or broken receiver can never block or fail a payment; failures are logged only.
Events are test-money events.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import queue
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("bridge.webhooks")
TIMEOUT_S = 5.0
RETRIES = 2  # after the first try
BACKOFF_S = 0.5  # doubles each retry
QUEUE_MAX = 200
FIELDS = ("event", "run_id", "helper", "status", "price", "captured", "refunded", "payout", "upheld")


def _env_value(name: str, env_file: Path | str) -> str:
    if os.environ.get(name):
        return os.environ[name].strip()
    try:
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def build_payload(event: dict) -> dict:
    """Only whitelisted fields leave the process."""
    out = {k: event[k] for k in FIELDS if k in event}
    out["currency"] = "USD"
    out["test_money"] = True
    out["amounts_in_cents"] = True
    out["timestamp"] = datetime.fromtimestamp(float(event.get("at", time.time())), timezone.utc).isoformat()
    return out


class Webhooks:
    def __init__(self, url: str, secret: str = "", *, timeout: float = TIMEOUT_S, retries: int = RETRIES,
                 backoff: float = BACKOFF_S):
        self.url, self.secret, self.timeout, self.retries, self.backoff = url, secret, timeout, retries, backoff
        self._q: queue.Queue = queue.Queue(QUEUE_MAX)
        self.failed = 0
        self.delivered = 0
        threading.Thread(target=self._worker, daemon=True, name="webhooks").start()

    def __call__(self, event: dict) -> None:
        """Queue an event and return at once."""
        try:
            self._q.put_nowait(build_payload(event))
        except queue.Full:
            self.failed += 1
            log.warning("webhook queue full; event dropped")

    def join(self, timeout: float = 10.0) -> None:
        """Wait until queued events are handled (for tests and a clean exit)."""
        end = time.time() + timeout
        while self._q.unfinished_tasks and time.time() < end:
            time.sleep(0.01)

    def _worker(self) -> None:
        while True:
            payload = self._q.get()
            try:
                self._deliver(payload)
            except Exception as e:  # never let the worker die
                self.failed += 1
                log.warning("webhook delivery crashed: %s", type(e).__name__)
            finally:
                self._q.task_done()

    def _deliver(self, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "agora-webhook/1"}
        if self.secret:
            headers["X-Agora-Signature"] = "sha256=" + hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        delay = self.backoff
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    if 200 <= r.status < 300:
                        self.delivered += 1
                        return
            except Exception as e:
                log.info("webhook attempt %d failed: %s", attempt + 1, type(e).__name__)
            if attempt < self.retries:
                time.sleep(delay)
                delay *= 2
        self.failed += 1
        log.warning("webhook gave up for %s", payload.get("run_id"))


def from_env(env_file: Path | str = ".env"):
    """A Webhooks sender, or None when BRIDGE_WEBHOOK_URL is not set (or is not http/https)."""
    url = _env_value("BRIDGE_WEBHOOK_URL", env_file)
    if not url.startswith(("http://", "https://")):
        return None
    return Webhooks(url, _env_value("BRIDGE_WEBHOOK_SECRET", env_file))
