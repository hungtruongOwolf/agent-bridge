import json
import threading
import time
from pathlib import Path

import pytest

from bridge.web import server
from bridge.world import open_world, seed

from conftest import FakeCell, FakeWeb, SmartModel
from test_chat_api import Echo, call

EX = Path(__file__).resolve().parent.parent.parent / "examples"


class PlainModel(SmartModel):
    """The starter helper's answer has only a summary, so drop the extra field the sales model adds."""

    def complete(self, prompt, inputs):
        r = super().complete(prompt, inputs)
        r.content.pop("risk", None)
        return r


@pytest.fixture
def srv(tmp_path):
    world = open_world(tmp_path)
    seed(world, EX / "packs", SmartModel(), "fixed", cell=FakeCell(), web=FakeWeb(), log=lambda *_: None)
    app = server.App(world, EX / "packs", EX / "vault.json", tmp_path / ".env", cell=FakeCell(), web=FakeWeb())
    app.model_factory = lambda: PlainModel()
    httpd = server.serve(app, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def post(app, url, path, body):
    return call(url + path, body, app.token)


def make(app, url, hid="my-helper", template="starter"):
    code, out = post(app, url, "/api/studio/create", {"id": hid, "template": template})
    assert code == 200, out
    return out


def wait_tested(app, url, hid, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = call(url + "/api/studio/helper?id=" + hid)[1]["versions"]
        if v and not v[0]["testing"]:
            return v[0]
        time.sleep(0.2)
    raise AssertionError("testing did not finish")


def test_a_new_helper_starts_from_a_template_and_shows_its_harness_as_a_graph(srv):
    app, url = srv
    h = make(app, url)
    assert h["problems"] == [] and h["manifest"]["id"] == "my-helper"
    g = h["graph"]
    ids = [n["id"] for n in g["nodes"]]
    assert ids[0] == "read" and set(ids) == {"read", "think", "check", "done", "failed"}
    by = {n["id"]: n for n in g["nodes"]}
    assert by["read"]["touches_files"] and by["think"]["private"] and not by["failed"]["private"]
    assert {"from": "check", "to": "failed", "kind": "fail"} in g["edges"]
    assert {"from": "task", "to": "think", "kind": "data"} in g["edges"]
    assert by["done"]["col"] > by["check"]["col"] > by["think"]["col"] > by["read"]["col"]
    assert h["caps"]["memory_lens"] and not h["caps"]["web"]


def test_names_are_checked_and_a_draft_cannot_escape_its_folder(srv):
    app, url = srv
    for bad in ("../evil", "Bad Name", "x", "a/b", "", None, "-dash"):
        assert post(app, url, "/api/studio/create", {"id": bad, "template": "starter"})[0] == 400
    make(app, url)
    assert post(app, url, "/api/studio/create", {"id": "my-helper", "template": "starter"})[0] == 400
    assert post(app, url, "/api/studio/create", {"id": "other", "template": "nope"})[0] == 400
    assert call(url + "/api/studio/helper?id=..%2F..%2Fregistry")[0] == 404


def test_editing_the_steps_is_checked_with_plain_reasons(srv):
    app, url = srv
    h = make(app, url)
    wf = json.loads(json.dumps(h["graph"] and yaml_to_dict(h["workflow_text"])))
    wf["steps"][0]["next"] = "nowhere"
    out = post(app, url, "/api/studio/save", {"id": "my-helper", "workflow": wf})[1]
    assert out["graph"] is None and any("unknown step" in p for p in out["problems"])
    wf["steps"][0]["next"] = "think"
    # a web step may never read private data
    wf["steps"].insert(1, {"id": "leak", "kind": "tool", "tool": "web_search", "tools": ["web_search"], "reads": ["read"], "prompt": "x", "next": "think"})
    wf["steps"][0]["next"] = "leak"
    out = post(app, url, "/api/studio/save", {"id": "my-helper", "workflow": wf})[1]
    assert any("private" in p for p in out["problems"])


def yaml_to_dict(text):
    import yaml
    return yaml.safe_load(text)


def test_the_description_must_name_concrete_skills(srv):
    app, url = srv
    h = make(app, url)
    m = h["manifest"]
    m["skills"][0]["does"] = "Helps"
    out = post(app, url, "/api/studio/save", {"id": "my-helper", "manifest": m})[1]
    assert any("does must say" in p for p in out["problems"])
    m["skills"][0]["does"] = "Answers questions about the files you share in two short sentences."
    m["id"] = "something-else"  # the name never changes
    out = post(app, url, "/api/studio/save", {"id": "my-helper", "manifest": m})[1]
    assert out["manifest"]["id"] == "my-helper" and out["problems"] == []


def test_a_draft_can_be_tried_on_chosen_shelves_without_publishing_or_paying(srv):
    app, url = srv
    make(app, url)
    code, out = post(app, url, "/api/studio/try", {"id": "my-helper", "task": "Which accounts are at risk?", "shelves": ["note"]})
    assert code == 200 and out["outcome"] == "COMPLETE" and "Acme" in out["answer"]
    assert out["visited"][:2] == ["read", "think"] and out["files"] and "no coins moved" in out["note"]
    assert not any(r.id == "my-helper" for r in app.world.registry.records.values())
    code, out = post(app, url, "/api/studio/try", {"id": "my-helper", "task": "Which accounts are at risk?", "shelves": []})
    assert code == 200 and out["files"] == []  # nothing shared, nothing seen
    assert post(app, url, "/api/studio/try", {"id": "my-helper", "task": "  ", "shelves": []})[0] == 400


def test_publishing_lists_the_helper_tests_it_and_lets_the_author_manage_it(srv):
    app, url = srv
    make(app, url)
    assert post(app, url, "/api/studio/publish", {"id": "my-helper", "price_usd": 0})[0] == 400
    assert post(app, url, "/api/studio/publish", {"id": "my-helper", "price_usd": 0.2, "payout_email": "not an email"})[0] == 400
    code, out = post(app, url, "/api/studio/publish", {"id": "my-helper", "price_usd": 0.2})
    assert code == 200 and out["version"] == "0.1.0"
    v = wait_tested(app, url, "my-helper")
    assert v["status"] in ("certified", "flagged", "uncertified") and v["price_usd"] == 0.2 and v["test_error"] == ""
    market = {m["id"]: m for m in call(url + "/api/state")[1]["market"]}
    assert "my-helper" in market
    # it can now be chatted with like any other helper
    key = v["key"]
    t = call(url + "/api/threads", {"agent_key": key, "shelves": ["note"]}, app.token)[1]
    out = call(url + "/api/thread/send", {"id": t["id"], "text": "Which accounts are at risk?"}, app.token)[1]
    assert out["thread"]["messages"][-1]["role"] == "helper"
    # the same version cannot be republished with different content
    h = call(url + "/api/studio/helper?id=my-helper")[1]
    m = h["manifest"]
    m["summary"] = "A different summary that is long enough to count."
    post(app, url, "/api/studio/save", {"id": "my-helper", "manifest": m})
    assert post(app, url, "/api/studio/publish", {"id": "my-helper", "price_usd": 0.2})[0] == 400
    m["version"] = "0.2.0"
    post(app, url, "/api/studio/save", {"id": "my-helper", "manifest": m})
    assert post(app, url, "/api/studio/publish", {"id": "my-helper", "price_usd": 0.25})[0] == 200
    wait_tested(app, url, "my-helper")
    assert [x["version"] for x in call(url + "/api/studio/helper?id=my-helper")[1]["versions"]] == ["0.2.0", "0.1.0"]
    assert post(app, url, "/api/studio/price", {"key": key, "price_usd": 0.5})[0] == 200
    assert next(x for x in call(url + "/api/studio/helper?id=my-helper")[1]["versions"] if x["key"] == key)["price_usd"] == 0.5
    assert post(app, url, "/api/studio/retire", {"key": key})[0] == 200
    assert next(x for x in call(url + "/api/studio/helper?id=my-helper")[1]["versions"] if x["key"] == key)["status"] == "retired"


def test_a_new_version_that_can_do_more_needs_a_new_first_number(srv):
    app, url = srv
    make(app, url)
    post(app, url, "/api/studio/publish", {"id": "my-helper", "price_usd": 0.2})
    wait_tested(app, url, "my-helper")
    h = call(url + "/api/studio/helper?id=my-helper")[1]
    wf = yaml_to_dict(h["workflow_text"])
    wf["steps"].insert(0, {"id": "web", "kind": "tool", "tool": "web_search", "tools": ["web_search"], "prompt": "{task}", "next": "read"})
    wf["start"] = "web"
    m = h["manifest"]; m["version"] = "0.2.0"
    out = post(app, url, "/api/studio/save", {"id": "my-helper", "manifest": m, "workflow": wf})[1]
    assert any("first number" in p for p in out["problems"])
    m["version"] = "1.0.0"
    assert post(app, url, "/api/studio/save", {"id": "my-helper", "manifest": m})[1]["problems"] == []


def test_only_your_own_published_helpers_can_be_retired_or_repriced(srv):
    app, url = srv
    other = next(k for k, r in app.world.registry.records.items() if r.id == "deal-brief")
    for path in ("/api/studio/retire", "/api/studio/price", "/api/studio/retest"):
        assert post(app, url, path, {"key": other, "price_usd": 1})[0] == 400
    assert post(app, url, "/api/studio/retire", {"key": "nope"})[0] == 400


def test_studio_routes_need_the_token_and_the_list_shows_my_drafts_only(srv):
    app, url = srv
    assert call(url + "/api/studio/create", {"id": "abc", "template": "starter"})[0] == 403
    make(app, url)
    lst = call(url + "/api/studio")[1]
    assert [h["id"] for h in lst["helpers"]] == ["my-helper"]  # the sample helpers are not mine to edit
    assert {t["id"] for t in lst["templates"]} >= {"starter", "web-first", "copy:deal-brief"}
    assert lst["suites"] and all(not s["id"].endswith("-dev") for s in lst["suites"])
    h = make(app, url, "my-copy", "copy:deal-brief")
    assert h["manifest"]["version"] == "0.3.0" and h["problems"] == [] and h["graph"]["nodes"]
    assert post(app, url, "/api/studio/delete", {"id": "my-copy"})[0] == 200
    assert call(url + "/api/studio/helper?id=my-copy")[0] == 404


def test_the_layout_of_the_graph_is_remembered(srv):
    app, url = srv
    make(app, url)
    pos = {"read": {"x": 10, "y": 20}, "bad": {"x": "no", "y": 1}}
    out = post(app, url, "/api/studio/save", {"id": "my-helper", "layout": pos})[1]
    assert out["layout"] == {"read": {"x": 10, "y": 20}}


def test_a_helper_can_charge_for_what_it_reads_up_to_a_stated_maximum(srv):
    from test_chat_api import new_chat, send
    app, url = srv
    make(app, url)
    assert post(app, url, "/api/studio/publish", {"id": "my-helper", "price_usd": 0.5, "per_file_cents": 5, "base_usd": 0.9})[0] == 400  # base above the maximum
    assert post(app, url, "/api/studio/publish", {"id": "my-helper", "price_usd": 0.5, "per_file_cents": 900})[0] == 400
    assert post(app, url, "/api/studio/publish", {"id": "my-helper", "price_usd": 0.5, "per_file_cents": 5, "base_usd": 0.05})[0] == 200
    v = wait_tested(app, url, "my-helper")
    assert v["per_file_cents"] == 5 and "5¢ + 5¢ per file it reads, at most 50¢" == v["price_text"]
    market = next(m for m in call(url + "/api/state")[1]["market"] if m["id"] == "my-helper")
    assert market["metered"] and market["price_text"] == v["price_text"]
    t = new_chat(app, url, pid="my-helper", shelves=["note"])
    out = send(app, url, t["id"], "Which accounts are at risk?")[1]
    files = len(out["thread"]["messages"][-1]["files"])
    rid = out["thread"]["messages"][-1]["run_id"]
    row = app.ledger.rows[rid]
    assert files >= 1 and row.hold == 50 and row.price == min(50, 5 + 5 * files)
    r = next(x for x in call(url + "/api/payments")[1]["items"] if x["run_id"] == rid)
    assert r["price"] == row.price and any("of the 50¢ hold" in e["why"] for e in r["events"])
    assert post(app, url, "/api/studio/price", {"key": v["key"], "price_usd": 0.3})[0] == 200  # back to one flat price
    assert next(x for x in call(url + "/api/studio/helper?id=my-helper")[1]["versions"])["price_text"] == "30¢ per answer"
