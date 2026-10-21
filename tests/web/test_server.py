import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from bridge.engine.flowd import ModelReply
from bridge.web import server
from bridge.world import open_world, seed

from conftest import FakeCell, FakeWeb

EX = Path(__file__).resolve().parent.parent.parent / "examples"


class Fixed:
    def complete(self, prompt, inputs):
        return ModelReply({"summary": "Acme and Globex accounts are at risk.", "risk": "high"}, tokens=1)


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    state = tmp_path_factory.mktemp("state")
    world = open_world(state)
    seed(world, EX / "packs", Fixed(), "fixed", cell=FakeCell(), web=FakeWeb(), log=lambda *_: None)
    app = server.App(world, EX / "packs", EX / "vault.json", state / ".env", cell=FakeCell(), web=FakeWeb())
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
    assert st["memory"]["total"] == 7 and st["proposals"] == []


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
    seed(world, EX / "packs", Fixed(), "fixed", cell=FakeCell(), web=FakeWeb(), log=lambda *_: None)
    app = server.App(world, EX / "packs", EX / "vault.json", tmp_path / ".env", model_factory=Briefer, cell=FakeCell(), web=FakeWeb())
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
    assert len(st["proposals"]) == 1 and st["memory"]["total"] == 7  # still only the user's records


def test_accept_adds_a_marked_record_that_survives_restart(mem_app):
    app, url = mem_app
    pid = run_brief(app, url)[1]["proposals"][0]["id"]
    assert call(url + "/api/proposal", {"id": pid, "action": "accept"}, app.token)[0] == 200
    vault = call(url + "/api/memory?limit=200")[1]["items"]
    new = [r for r in vault if r["trust"] == 1]
    assert len(new) == 1 and new[0]["from_run"] and new[0]["sensitivity"] == "low"
    assert len(server.App(app.world, EX / "packs", EX / "vault.json", app.env_file).vault().all()) == 8


def test_reject_leaves_the_vault_unchanged(mem_app):
    app, url = mem_app
    pid = run_brief(app, url)[1]["proposals"][0]["id"]
    assert call(url + "/api/proposal", {"id": pid, "action": "reject"}, app.token)[0] == 200
    st = call(url + "/api/state")[1]
    assert st["proposals"] == [] and st["memory"]["total"] == 7


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
    assert call(url + "/api/state")[1]["memory"]["total"] == 7


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


def test_web_pack_run_uses_the_public_search_and_keeps_records_private(mem_app):
    app, url = mem_app
    code, rep = call(url + "/api/run", {"key": key_of(app, "context-brief"), "types": ["note", "contact"]}, app.token)
    assert code == 200 and rep["outcome"] == "COMPLETE"
    assert app.web.queries[-1] == "B2B SaaS renewal budget cuts trends 2026"  # no private text in the query
    assert "000111222" not in json.dumps(rep)


def test_oversized_body_is_refused(srv):
    app, url = srv
    assert call(url + "/api/run", {"key": "x" * 430000}, app.token)[0] in (413,)


def test_history_and_per_run_report_are_available(mem_app):
    app, url = mem_app
    rep = run_brief(app, url)[1]
    st = call(url + "/api/state")[1]
    assert st["history"][0]["run_id"] == rep["run_id"] and "Delivered a result" in st["history"][0]["summary"]
    code, again = call(url + "/api/report/" + rep["run_id"])
    assert code == 200 and again["journal"][0]["kind"] == "run_started"
    assert call(url + "/api/report/unknown")[0] == 404


def test_history_lists_newest_first(mem_app):
    app, url = mem_app
    a = run_brief(app, url)[1]["run_id"]
    b = run_brief(app, url)[1]["run_id"]
    assert [h["run_id"] for h in call(url + "/api/state")[1]["history"][:2]] == [b, a]


# ---- money (TEST money through the fake provider) -------------------------------------------------

def pay(rep):
    return rep["payment"]


def test_a_completed_run_captures_only_the_floor_until_you_decide(mem_app):
    app, url = mem_app
    rep = run_brief(app, url)[1]  # deal-brief costs $0.60
    p = pay(rep)
    assert p["state"] == "RESULT_READY" and p["price"] == 60 and p["captured"] == 15 and p["test_money"] is True
    assert app.ledger.provider.captured_total() == 15


def test_accept_captures_the_rest_and_pays_the_author(mem_app):
    app, url = mem_app
    rep = run_brief(app, url)[1]
    code, p = call(url + "/api/settle", {"run_id": rep["run_id"], "action": "accept"}, app.token)
    assert code == 200 and p["state"] == "SETTLED" and p["captured"] == 60
    assert p["payout"]["status"] == "paid" and p["payout"]["amount"] == 54  # 60 minus a 10% platform fee
    st = call(url + "/api/state")[1]["payments"]
    assert st["captured"] == 60 and st["paid_out"] == 54 and st["test_money"] is True


def test_reject_keeps_only_the_floor(mem_app):
    app, url = mem_app
    rep = run_brief(app, url)[1]
    code, p = call(url + "/api/settle", {"run_id": rep["run_id"], "action": "reject", "reason": "not useful"}, app.token)
    assert p["state"] == "SETTLED_REJECTED" and p["captured"] == 15 and p["payout"]["amount"] == 14


def test_settling_twice_or_with_a_bad_action_is_a_400(mem_app):
    app, url = mem_app
    rid = run_brief(app, url)[1]["run_id"]
    call(url + "/api/settle", {"run_id": rid, "action": "accept"}, app.token)
    assert call(url + "/api/settle", {"run_id": rid, "action": "accept"}, app.token)[0] == 400
    assert call(url + "/api/settle", {"run_id": rid, "action": "burn"}, app.token)[0] == 400
    assert call(url + "/api/settle", {"run_id": "nope", "action": "accept"}, app.token)[0] == 400
    assert call(url + "/api/settle", {"run_id": rid, "action": "accept"})[0] == 403  # needs the token


def test_a_flagged_pack_that_gets_killed_costs_you_nothing(mem_app):
    app, url = mem_app
    code, rep = call(url + "/api/run", {"key": key_of(app, "quick-insights"), "types": ["note", "contact"]}, app.token)
    p = pay(rep)
    assert rep["outcome"] == "KILLED" and p["state"] == "DISPUTE_UPHELD" and p["captured"] == 0
    assert app.ledger.provider.captured_total() == 0 and p["payout"]["status"] == "none"
    assert any("kill claim" in e["why"] for e in p["events"])


def test_a_model_outage_voids_the_hold_and_nobody_is_blamed(mem_app):
    app, url = mem_app

    def down():
        class Down:
            def complete(self, prompt, inputs):
                raise TimeoutError("provider down")
        return Down()

    app.model_factory = down
    rep = run_brief(app, url)[1]
    assert rep["outcome"] == "FAILED_INFRA" and pay(rep)["state"] == "VOIDED" and pay(rep)["captured"] == 0


def test_a_killed_pack_that_the_certifier_has_not_flagged_stays_in_dispute(mem_app):
    app, url = mem_app
    key = key_of(app, "quick-insights")
    app.world.market._atts.pop(app.world.registry.records[key].digest)  # no independent evidence for this claim
    code, rep = call(url + "/api/run", {"key": key, "types": ["note", "contact"]}, app.token)
    assert rep["outcome"] == "KILLED"
    assert pay(rep)["state"] == "DISPUTE_HOLD" and pay(rep)["captured"] == 0
    assert app.ledger.summary()["held"] == 10  # the whole $0.10 stays held, nobody is paid


def test_unaccepted_results_auto_accept_after_the_deadline(mem_app):
    app, url = mem_app
    t = {"now": 1_000_000.0}
    app.clock = lambda: t["now"]
    rid = run_brief(app, url)[1]["run_id"]
    t["now"] += 49 * 3600  # past the 48 h accept window
    st = call(url + "/api/state")[1]["payments"]
    assert app.ledger.rows[rid].state == "SETTLED" and st["captured"] == 60


def test_money_state_persists_across_a_restart(mem_app):
    app, url = mem_app
    rid = run_brief(app, url)[1]["run_id"]
    again = server.App(app.world, EX / "packs", EX / "vault.json", app.env_file, cell=FakeCell(), web=FakeWeb())
    assert again.ledger.rows[rid].state == "RESULT_READY" and again.ledger.provider.captured_total() == 15
    again.settle({"run_id": rid, "action": "accept"})
    assert again.ledger.provider.captured_total() == 60


# ---- PayPal-style approval: the run waits until the buyer approves the hold ---------------------------

@pytest.fixture
def approval_app(tmp_path):
    from bridge.payments.ledger import Ledger
    from bridge.payments.provider import FakeProvider
    world = open_world(tmp_path / "state")
    seed(world, EX / "packs", Fixed(), "fixed", cell=FakeCell(), web=FakeWeb(), log=lambda *_: None)
    provider = FakeProvider(require_approval=True)
    app = server.App(world, EX / "packs", EX / "vault.json", tmp_path / ".env", model_factory=Briefer,
                     cell=FakeCell(), web=FakeWeb(), ledger=Ledger(provider), demo_author_email="author@example.com")
    httpd = server.serve(app, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{httpd.server_address[1]}", provider
    httpd.shutdown()


def test_the_run_does_not_start_until_the_buyer_approves(approval_app):
    app, url, provider = approval_app
    code, out = call(url + "/api/run", {"key": key_of(app, "deal-brief"), "types": ["note", "contact"]}, app.token)
    assert code == 200 and out["needs_approval"] is True and out["approve_url"].startswith("https://sandbox.fake/approve/")
    assert app.ledger.rows[out["run_id"]].state == "AWAITING_APPROVAL"
    assert app.history == [] and provider.captured_total() == 0  # nothing ran, nothing was charged


def test_continuing_before_approving_is_refused_and_the_run_stays_pending(approval_app):
    app, url, provider = approval_app
    out = call(url + "/api/run", {"key": key_of(app, "deal-brief"), "types": ["note"]}, app.token)[1]
    code, err = call(url + "/api/run/continue", {"run_id": out["run_id"]}, app.token)
    assert code == 400 and "not approved" in err["error"]
    assert out["run_id"] in app.pending


def test_after_approval_the_run_executes_and_is_paid_as_usual(approval_app):
    app, url, provider = approval_app
    out = call(url + "/api/run", {"key": key_of(app, "deal-brief"), "types": ["note", "contact"]}, app.token)[1]
    provider.buyer_approves(app.ledger.rows[out["run_id"]].auth_id)
    code, rep = call(url + "/api/run/continue", {"run_id": out["run_id"]}, app.token)
    assert code == 200 and rep["outcome"] == "COMPLETE" and rep["payment"]["state"] == "RESULT_READY"
    assert rep["payment"]["captured"] == 15
    assert call(url + "/api/run/continue", {"run_id": out["run_id"]}, app.token)[0] == 400  # not twice


def test_unknown_run_cannot_be_continued_and_the_endpoint_needs_the_token(approval_app):
    app, url, _ = approval_app
    assert call(url + "/api/run/continue", {"run_id": "nope"}, app.token)[0] == 400
    assert call(url + "/api/run/continue", {"run_id": "nope"})[0] == 403


def test_return_pages_are_plain_and_need_no_token(approval_app):
    app, url, _ = approval_app
    assert b"approved the hold" in call(url + "/paypal/return?token=X")[1]
    assert b"cancelled" in call(url + "/paypal/cancel")[1]


def test_the_author_is_paid_at_their_listing_email_or_the_demo_email(approval_app):
    app, url, provider = approval_app
    out = call(url + "/api/run", {"key": key_of(app, "deal-brief"), "types": ["note"]}, app.token)[1]
    assert app.ledger.rows[out["run_id"]].author == "author@example.com"


def test_state_reports_which_payment_provider_is_in_use(srv):
    app, url = srv
    assert call(url + "/api/state")[1]["payments"]["provider"] == "test"


def test_static_files_are_served_with_the_right_type(srv):
    app, url = srv
    import urllib.request
    for path, ctype in (("/static/fonts/press-start-2p-latin-400.woff2", "font/woff2"), ("/static/fonts/license.txt", "text/plain")):
        with urllib.request.urlopen(url + path) as r:
            assert r.status == 200 and ctype in r.headers["Content-Type"] and len(r.read()) > 100


@pytest.mark.parametrize("path", ["/static/../server.py", "/static/..%2fserver.py", "/static/fonts/../../server.py",
                                  "/static/index.html", "/static/nope.js", "/static/.hidden", "/static/fonts/x.exe",
                                  "/static/%2e%2e/server.py"])
def test_static_route_refuses_anything_that_is_not_a_known_plain_file(srv, path):
    app, url = srv
    assert call(url + path)[0] == 404


JARGON = ("broker", "sidecar", "digest", "hash", "lens", "journal", "quarantine", "certifier", "canary", "schema", "attestation", "ledger")


def static_text(url, name):
    import urllib.request
    with urllib.request.urlopen(url + "/static/" + name) as r:
        return r.read().decode()


def test_the_page_loads_the_stylesheet_and_every_script_and_all_of_them_are_served(srv):
    app, url = srv
    html = call(url + "/")[1].decode()
    for name in ("style.css", "chat.js", "office.js", "story.js", "app.js"):
        assert "/static/" + name in html
        assert len(static_text(url, name)) > 200
    assert 'id="floor"' in html and 'data-token="' + app.token in html


def test_the_page_speaks_plain_language_with_no_developer_words(srv):
    import re
    app, url = srv
    html = call(url + "/")[1].decode().lower()
    visible = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    for word in JARGON:
        assert word not in visible, word
    for needle in ("your market floor", "who do you want to talk with", "what the helper sees", "my memory", "coins"):
        assert needle in visible


def test_money_decisions_and_the_approval_step_are_wired_in_the_script(srv):
    app, url = srv
    js = static_text(url, "chat.js") + static_text(url, "app.js")
    for needle in ("/api/thread/reject", "/api/run/continue", "Not helpful", "I approved, continue", "^https?:", "Coins"):
        assert needle in js
    assert "http://" not in js  # nothing in the script points outside this machine


def test_the_floor_replays_the_run_record_and_says_so(srv):
    app, url = srv
    story = static_text(url, "story.js")
    for needle in ("step_started", "step_committed", "cell_run", "incident", "run_finished", "model_call"):
        assert needle in story
    assert "office.play(report" in static_text(url, "chat.js")



def test_the_profile_endpoint_describes_a_helper_and_refuses_unknown_ones(srv):
    import urllib.parse
    app, url = srv
    key = key_of(app, "private-analyst")
    code, p = call(url + "/api/agent?key=" + urllib.parse.quote(key, safe=""))
    assert code == 200 and p["id"] == "private-analyst" and p["author_says"]["skills"] and p["cannot"]
    assert p["measured"]["tested"] is True and p["price_cents"] == 40
    assert call(url + "/api/agent?key=" + urllib.parse.quote("nope", safe=""))[0] == 404
    assert call(url + "/api/agent")[0] == 404
