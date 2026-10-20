import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from bridge.engine.flowd import ModelReply
from bridge.web import server
from bridge.world import open_world, seed

from conftest import FakeCell

EX = Path(__file__).resolve().parent.parent.parent / "examples"


class Fixed:
    def complete(self, prompt, inputs):
        return ModelReply({"summary": "Acme and Globex accounts are at risk.", "risk": "high"}, tokens=1)


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    state = tmp_path_factory.mktemp("state")
    world = open_world(state)
    seed(world, EX / "packs", Fixed(), "fixed", cell=FakeCell(), log=lambda *_: None)
    app = server.App(world, EX / "packs", EX / "vault.json", state / ".env", cell=FakeCell())
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
    assert code == 200 and st["market"][0]["status"] == "certified" and {r["id"] for r in st["market"] if r["status"] == "flagged"} == {"friendly-helper", "quick-insights"}
    assert len(st["vault"]) == 5 and st["proposals"] == []


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


def test_missing_model_key_ends_the_run_as_an_infra_failure_with_no_details(srv):
    app, url = srv  # the state dir has no .env, so there is no key to find
    code, out = call(url + "/api/run", {"key": key_of(app, "private-analyst"), "types": ["note"]}, app.token)
    assert code == 200 and out["outcome"] == "FAILED_INFRA" and out["result"] is None
    assert out["reasons"] == ["model call failed: ModelError"]


class Briefer:
    """Answers the analyze step and the remember step differently, like a real pack's model would."""

    def complete(self, prompt, inputs):
        if "proposals" in prompt:
            return ModelReply({"proposals": [{"type": "note", "text": "Acme renewal risk raised in October"}]}, tokens=5)
        return ModelReply({"summary": "Acme and Globex accounts are at risk.", "risk": "high"}, tokens=5)


@pytest.fixture
def mem_app(tmp_path):
    world = open_world(tmp_path / "state")
    seed(world, EX / "packs", Fixed(), "fixed", cell=FakeCell(), log=lambda *_: None)
    app = server.App(world, EX / "packs", EX / "vault.json", tmp_path / ".env", model_factory=Briefer, cell=FakeCell())
    httpd = server.serve(app, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def run_brief(app, url, **extra):
    return call(url + "/api/run", {"key": key_of(app, "deal-brief"), "types": ["note", "contact"], **extra}, app.token)


def test_run_creates_a_pending_proposal_and_does_not_touch_the_vault(mem_app):
    app, url = mem_app
    code, rep = run_brief(app, url)
    assert code == 200 and rep["outcome"] == "COMPLETE" and len(rep["proposals"]) == 1
    st = call(url + "/api/state")[1]
    assert len(st["proposals"]) == 1 and len(st["vault"]) == 5  # still only the user's records


def test_accept_adds_a_marked_record_that_survives_restart(mem_app):
    app, url = mem_app
    pid = run_brief(app, url)[1]["proposals"][0]["id"]
    assert call(url + "/api/proposal", {"id": pid, "action": "accept"}, app.token)[0] == 200
    vault = call(url + "/api/state")[1]["vault"]
    new = [r for r in vault if r["trust"] == 1]
    assert len(new) == 1 and new[0]["from_run"] and new[0]["sensitivity"] == "low"
    assert len(server.App(app.world, EX / "packs", EX / "vault.json", app.env_file).vault().all()) == 6


def test_reject_leaves_the_vault_unchanged(mem_app):
    app, url = mem_app
    pid = run_brief(app, url)[1]["proposals"][0]["id"]
    assert call(url + "/api/proposal", {"id": pid, "action": "reject"}, app.token)[0] == 200
    st = call(url + "/api/state")[1]
    assert st["proposals"] == [] and len(st["vault"]) == 5


def test_accepting_twice_or_a_bad_id_is_a_400(mem_app):
    app, url = mem_app
    pid = run_brief(app, url)[1]["proposals"][0]["id"]
    call(url + "/api/proposal", {"id": pid, "action": "accept"}, app.token)
    assert call(url + "/api/proposal", {"id": pid, "action": "accept"}, app.token)[0] == 400
    assert call(url + "/api/proposal", {"id": "nope", "action": "accept"}, app.token)[0] == 400
    assert call(url + "/api/proposal", {"id": pid, "action": "burn"}, app.token)[0] == 400


def test_revert_undoes_one_run_and_keeps_the_users_own_records(mem_app):
    app, url = mem_app
    rep = run_brief(app, url)[1]
    call(url + "/api/proposal", {"id": rep["proposals"][0]["id"], "action": "accept"}, app.token)
    code, out = call(url + "/api/revert", {"run_id": rep["run_id"]}, app.token)
    assert code == 200 and out["removed_from_vault"] == 1
    assert len(call(url + "/api/state")[1]["vault"]) == 5


def test_proposal_endpoints_need_the_token(mem_app):
    app, url = mem_app
    assert call(url + "/api/proposal", {"id": "p1", "action": "accept"})[0] == 403
    assert call(url + "/api/revert", {"run_id": "x"})[0] == 403


def test_a_killed_run_creates_no_proposals(mem_app):
    app, url = mem_app
    code, rep = call(url + "/api/run", {"key": key_of(app, "friendly-helper"), "types": ["note"], "model": "leak"}, app.token)
    assert rep["outcome"] == "KILLED" and rep["proposals"] == []


def test_code_pack_run_is_killed_for_probing_the_cell_and_report_lists_each_attempt(srv):
    app, url = srv
    code, rep = call(url + "/api/run", {"key": key_of(app, "quick-insights"), "types": ["note", "contact"]}, app.token)
    assert code == 200 and rep["outcome"] == "KILLED" and rep["result"] is None
    kinds = {e["kind"] for e in rep["broker_events"]}
    assert {"SANDBOX_NETWORK", "SANDBOX_PROCESS", "SANDBOX_WRITE"} <= kinds
