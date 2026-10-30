import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from bridge.payments.ledger import Ledger
from bridge.payments.provider import FakeProvider
from bridge.payments.webhooks import Webhooks, from_env


class Receiver:
    def __init__(self, statuses=(200,), delay=0.0):
        self.got, self.statuses, self.delay = [], list(statuses), delay
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.got.append((self.headers, body))
                if outer.delay:
                    import time
                    time.sleep(outer.delay)
                code = outer.statuses.pop(0) if len(outer.statuses) > 1 else outer.statuses[0]
                try:
                    self.send_response(code)
                    self.end_headers()
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/hook"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


def settle(l):
    l.hire("r1", "deal-brief@1.0", "someone@example.com", "buyer@example.com", 100, 0)
    l.start("r1", 1)
    l.result_ready("r1", 2)
    l.accept("r1", 3)
    l.release_payouts(4)


def test_settle_and_payout_events_are_signed_and_private():
    r = Receiver()
    w = Webhooks(r.url, "s3cret", backoff=0.01)
    settle(Ledger(FakeProvider(), on_event=w))
    w.join()
    r.close()
    assert [json.loads(b)["event"] for _, b in r.got] == ["payment.settled", "payout.paid"]
    h, body = r.got[0]
    assert h["X-Agora-Signature"] == "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    d = json.loads(body)
    assert d["run_id"] == "r1" and d["helper"] == "deal-brief" and d["price"] == 100 and d["status"] == "SETTLED" and d["timestamp"]
    text = body.decode()
    assert "@" not in text and "example.com" not in text and "buyer" not in text and "author" not in text


def test_500_then_success():
    r = Receiver(statuses=(500, 200))
    w = Webhooks(r.url, backoff=0.01)
    w({"event": "payment.settled", "run_id": "x", "at": 1})
    w.join()
    r.close()
    assert len(r.got) == 2 and w.delivered == 1 and w.failed == 0


def test_timeout_never_blocks_the_payment_and_is_counted():
    r = Receiver(delay=0.6)
    w = Webhooks(r.url, timeout=0.1, retries=1, backoff=0.01)
    import time
    t = time.time()
    settle(Ledger(FakeProvider(), on_event=w))
    assert time.time() - t < 0.5  # the ledger did not wait for the receiver
    w.join(5)
    r.close()
    assert w.failed >= 1 and w.delivered == 0


def test_a_broken_listener_cannot_fail_a_payment():
    def boom(e):
        raise RuntimeError("x")
    l = Ledger(FakeProvider(), on_event=boom)
    settle(l)
    assert l.rows["r1"].state == "SETTLED"


def test_disabled_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("BRIDGE_WEBHOOK_URL", raising=False)
    assert from_env(tmp_path / "missing.env") is None
    (tmp_path / ".env").write_text("BRIDGE_WEBHOOK_URL=\n", encoding="utf-8")
    assert from_env(tmp_path / ".env") is None


def test_enabled_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("BRIDGE_WEBHOOK_URL", raising=False)
    (tmp_path / ".env").write_text("BRIDGE_WEBHOOK_URL=http://127.0.0.1:9/h\nBRIDGE_WEBHOOK_SECRET=k\n", encoding="utf-8")
    w = from_env(tmp_path / ".env")
    assert w is not None and w.secret == "k"
