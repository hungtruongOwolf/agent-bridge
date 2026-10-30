import http.client
import json
import re
import threading
from pathlib import Path

import pytest

from bridge.web.judge import JudgeConfig, JudgeHub, JudgeModel, ModelCap, serve_judge

EX = Path(__file__).resolve().parent.parent.parent / "examples"


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    cfg = JudgeConfig(allowed_hosts=("judge.example.test",), root=tmp_path_factory.mktemp("judge"), max_sessions=3, new_per_ip_minute=100, new_per_minute=100)
    httpd, hub = serve_judge(cfg, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield hub, httpd.server_address[1]
    httpd.shutdown()


class Client:
    def __init__(self, port, host="127.0.0.1"):
        self.port, self.host, self.cookie, self.token = port, f"{host}:{port}", None, None

    def req(self, method, path, body=None, host=None, token=True, cookie=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        h = {"Host": host or self.host}
        if cookie and self.cookie:
            h["Cookie"] = self.cookie
        if token and self.token:
            h["X-Bridge-Token"] = self.token
        data = json.dumps(body).encode() if body is not None else None
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        sc = r.getheader("Set-Cookie")
        if sc:
            self.cookie = sc.split(";")[0]
        c.close()
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw.decode("utf-8", "replace")

    def open(self):
        status, page = self.req("GET", "/")
        assert status == 200
        self.token = re.search(r'data-token="([^"]+)"', page).group(1)
        return self


def brief_key(c):
    return next(r["key"] for r in c.req("GET", "/api/state")[1]["market"] if r["id"] == "account-brief")


def test_health_needs_no_cookie_and_no_host(srv):
    _, port = srv
    assert Client(port).req("GET", "/healthz", host="anything.invalid") == (200, {"ok": True})


def test_wrong_host_is_rejected_everywhere(srv):
    _, port = srv
    c = Client(port).open()
    assert c.req("GET", "/", host="evil.example.com")[0] == 403
    assert c.req("GET", "/api/state", host="evil.example.com")[0] == 403
    assert c.req("POST", "/api/thread/send", {"id": "x", "text": "hi"}, host="evil.example.com")[0] == 403
    assert c.req("GET", "/practice/mock/state", host="evil.example.com")[0] == 403
    assert c.req("GET", "/api/state", host="judge.example.test")[0] == 200  # the configured name is accepted


def test_missing_or_wrong_token_is_rejected(srv):
    _, port = srv
    c = Client(port).open()
    assert c.req("POST", "/api/thread/send", {"id": "x", "text": "hi"}, token=False)[0] == 403
    c.token = "not-the-token"
    assert c.req("POST", "/api/thread/send", {"id": "x", "text": "hi"})[0] == 403


def test_no_cookie_no_api(srv):
    _, port = srv
    c = Client(port).open()
    st, out = c.req("GET", "/api/state", cookie=False)
    assert st == 403 and "reload" in out["error"]
    assert c.req("POST", "/api/thread/send", {"id": "x", "text": "hi"}, cookie=False)[0] == 403
    assert c.req("GET", "/practice/checkoutnow?token=ORDER-00001", cookie=False)[0] == 403


def test_cookie_is_httponly_and_lax(srv):
    _, port = srv
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("GET", "/", headers={"Host": "127.0.0.1"})
    sc = c.getresponse().getheader("Set-Cookie")
    assert "HttpOnly" in sc and "SameSite=Lax" in sc


def test_banner_is_on_every_page(srv):
    _, port = srv
    st, page = Client(port).req("GET", "/")
    assert "answers come from a recorded model" in page and "Test money" in page


def test_visitor_a_cannot_read_visitor_bs_chat(srv):
    _, port = srv
    a, b = Client(port).open(), Client(port).open()
    t = b.req("POST", "/api/threads", {"agent_key": brief_key(b)})[1]
    assert a.req("GET", "/api/thread?id=" + t["id"])[0] in (400, 404)
    assert b.req("GET", "/api/thread?id=" + t["id"])[0] == 200
    assert a.req("GET", "/api/state")[1]["threads"] == []
    # B's token with A's cookie is no use either
    a.token = b.token
    assert a.req("POST", "/api/thread/send", {"id": t["id"], "text": "hi"})[0] == 403


def test_hold_goes_to_the_practice_page_on_the_same_port(srv):
    _, port = srv
    c = Client(port).open()
    t = c.req("POST", "/api/threads", {"agent_key": brief_key(c)})[1]
    out = c.req("POST", "/api/thread/send", {"id": t["id"], "text": "Which accounts are at risk?"})[1]
    assert out["needs_approval"] and out["approve_url"].startswith(f"http://127.0.0.1:{port}/practice/checkoutnow?token=")
    page = c.req("GET", "/practice/checkoutnow?token=" + out["approve_url"].split("=")[1])[1]
    assert "Practice server" in page and "/practice/checkoutnow/approve" in page
    other = Client(port).open()  # another visitor cannot see or approve this order
    assert "not found" in other.req("GET", "/practice/checkoutnow?token=" + out["approve_url"].split("=")[1])[1]


def test_code_helpers_are_refused_with_a_plain_message(srv):
    _, port = srv
    c = Client(port).open()
    key = next(r["key"] for r in c.req("GET", "/api/state")[1]["market"] if r["id"] == "quick-insights")  # the one that runs code
    st, out = c.req("POST", "/api/threads", {"agent_key": key})
    assert st == 400 and "does not run helpers that run code" in out["error"]


def test_sessions_are_capped_least_recently_used_and_folders_removed(srv):
    hub, port = srv
    first = Client(port).open()
    folders = lambda: {p.name for p in (hub.root / "v").iterdir()}
    for _ in range(4):
        Client(port).open()
    assert len(hub.sessions) == 3 and len(folders()) == 3
    assert first.req("GET", "/api/state")[0] == 403  # evicted


def test_idle_session_expires(tmp_path):
    clock = Clock()
    hub = JudgeHub(JudgeConfig(root=tmp_path, ttl_s=60, clock=clock))
    sid, _ = hub.create("1.2.3.4")
    assert hub.get(sid) is not None
    clock.t += 61
    assert hub.get(sid) is None and not list((tmp_path / "v").iterdir())


def test_new_visitor_rate_limit(tmp_path):
    from bridge.web.judge import TooManyNew
    hub = JudgeHub(JudgeConfig(root=tmp_path, new_per_ip_minute=2, clock=Clock()))
    hub.create("9.9.9.9"), hub.create("9.9.9.9")
    with pytest.raises(TooManyNew):
        hub.create("9.9.9.9")
    hub.create("8.8.8.8")


def test_model_caps_are_enforced():
    clock = Clock()
    cap = ModelCap(per_hour=3, per_visitor=2, clock=clock)
    assert [cap.take("a"), cap.take("a"), cap.take("a")] == [True, True, False]  # one visitor: 2 an hour
    assert cap.take("b") and not cap.take("c")  # everyone: 3 an hour
    clock.t += 3601
    assert cap.take("c")  # the window moves on


def test_live_model_is_used_only_while_the_cap_has_room(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "not-a-real-key")
    hub = JudgeHub(JudgeConfig(root=tmp_path, real_model=True, model_per_hour=2, model_per_visitor_hour=2, clock=Clock()))
    calls = []

    class Live:
        provider = "live"

        def complete(self, prompt, inputs):
            calls.append(1)
            return None
    hub.live = Live()
    m = JudgeModel(hub, "v1")
    assert m.provider == "live"
    m.complete("p", {}), m.complete("p", {})
    assert len(calls) == 2 and m.provider != "live"
    reply = m.complete("Reply as JSON with keys summary", {"task": "x", "read": []})  # over the cap: the recorded model answers, no call is made
    assert len(calls) == 2 and "summary" in reply.content


def test_no_live_model_without_the_flag_even_with_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "not-a-real-key")
    assert JudgeHub(JudgeConfig(root=tmp_path)).live is None


def test_render_hostname_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "Agora.onrender.com")
    assert "agora.onrender.com" in JudgeHub(JudgeConfig(root=tmp_path)).hosts


def test_nothing_is_written_outside_the_root(tmp_path):
    hub = JudgeHub(JudgeConfig(root=tmp_path / "root"))
    before = {p for p in EX.rglob("*")}
    hub.create("1.1.1.1")
    assert {p for p in EX.rglob("*")} == before and (tmp_path / "root" / "v").is_dir()


def test_default_serve_stays_local_only(capsys):
    from bridge import cli
    assert cli.main(["serve", "--host", "0.0.0.0"]) == 2
    assert "only allowed together with --judge-mode" in capsys.readouterr().out
