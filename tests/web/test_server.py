import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from bridge.engine.flowd import ModelReply
from bridge.web import server
from bridge.world import open_world, seed

EX = Path(__file__).resolve().parent.parent.parent / "examples"


class Fixed:
    def complete(self, prompt, inputs):
        return ModelReply({"summary": "Acme and Globex accounts are at risk.", "risk": "high"}, tokens=1)


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    state = tmp_path_factory.mktemp("state")
    world = open_world(state)
    seed(world, EX / "packs", Fixed(), "fixed", log=lambda *_: None)
    app = server.App(world, EX / "packs", EX / "vault.json", state / ".env")
    httpd = server.serve(app, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(url, body=None, token=None, host=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None)
    if token:
        req.add_header("X-Bridge-Token", token)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}") if "json" in r.headers.get("Content-Type", "") else r.read()
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def key_of(app, pid):
    return next(k for k, r in app.world.registry.records.items() if r.id == pid)


def test_state_lists_ranked_market_and_vault(srv):
    app, url = srv
    code, st = call(url + "/api/state")
    assert code == 200 and st["market"][0]["id"] == "private-analyst" and len(st["vault"]) == 5


def test_page_carries_the_token(srv):
    app, url = srv
    code, html = call(url + "/")
    assert code == 200 and app.token.encode() in html and b"__TOKEN__" not in html


def test_post_without_token_is_forbidden(srv):
    app, url = srv
    assert call(url + "/api/run", {"key": key_of(app, "private-analyst"), "types": ["note"]})[0] == 403


def test_foreign_host_header_is_forbidden(srv):
    app, url = srv
    assert call(url + "/api/state", host="evil.example.com")[0] == 403


def test_run_thief_is_killed_and_report_has_no_secret(srv):
    app, url = srv
    code, rep = call(url + "/api/run", {"key": key_of(app, "friendly-helper"), "types": ["note", "contact"], "model": "leak"}, app.token)
    assert code == 200 and rep["outcome"] == "KILLED" and rep["result"] is None
    assert "000111222" not in json.dumps(rep)


def test_bad_requests_get_400_not_500(srv):
    app, url = srv
    assert call(url + "/api/run", {"key": "nope", "types": ["note"]}, app.token)[0] == 400
    assert call(url + "/api/run", {"key": key_of(app, "private-analyst"), "types": []}, app.token)[0] == 400
    assert call(url + "/api/run", {"key": key_of(app, "private-analyst"), "types": ["note"], "max_sensitivity": "x"}, app.token)[0] == 400


def test_star_is_counted_once_per_user(srv):
    app, url = srv
    k = key_of(app, "private-analyst")
    call(url + "/api/star", {"key": k, "user": "alice"}, app.token)
    code, out = call(url + "/api/star", {"key": k, "user": "alice"}, app.token)
    assert code == 200 and out["stars"] == 1


def test_missing_model_key_gives_a_generic_error(srv):
    app, url = srv  # the state dir has no .env, so there is no key to find
    code, out = call(url + "/api/run", {"key": key_of(app, "private-analyst"), "types": ["note"]}, app.token)
    assert code == 500 and out == {"error": "run failed: ModelError"}
