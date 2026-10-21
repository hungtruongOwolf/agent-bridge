"""The API router on its own: matching, parameters, and that every address is declared exactly once."""
from bridge.web.api.router import Router


def test_an_address_with_a_name_part_matches_and_hands_the_part_over():
    r = Router()
    r.add("GET", "/api/report/:run_id", lambda req: req.params)
    route, params = r.find("GET", "/api/report/run-1-abc")
    assert params == {"run_id": "run-1-abc"} and route.token is False


def test_a_change_needs_the_token_and_a_read_does_not_unless_it_says_so():
    r = Router()
    r.add("GET", "/a", lambda q: 1)
    r.add("POST", "/a", lambda q: 1)
    r.add("GET", "/secret", lambda q: 1, token=True)
    assert [r.find("GET", "/a")[0].token, r.find("POST", "/a")[0].token, r.find("GET", "/secret")[0].token] == [False, True, True]


def test_method_and_path_must_both_match():
    r = Router()
    r.add("GET", "/a", lambda q: 1)
    assert r.find("POST", "/a") is None and r.find("GET", "/a/b") is None and r.find("GET", "/b") is None


def test_the_console_declares_each_address_once(tmp_path):
    from pathlib import Path
    from bridge.web import server
    from bridge.world import open_world, seed
    from conftest import FakeCell, FakeWeb
    ex = Path(__file__).resolve().parent.parent.parent / "examples"
    app = server.App(open_world(tmp_path), ex / "packs", ex / "vault.json", tmp_path / ".env", cell=FakeCell(), web=FakeWeb())
    table = app.router().table()
    assert len(table) == len(set(table))
    for needed in (("GET", "/api/state"), ("POST", "/api/thread/send"), ("POST", "/api/memory"), ("GET", "/api/memory/export"), ("POST", "/api/settle")):
        assert needed in table
