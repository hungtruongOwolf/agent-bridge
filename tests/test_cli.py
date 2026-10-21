from pathlib import Path

import pytest

from bridge import cli
from bridge.engine.flowd import ModelReply

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"


def argv(pack, *extra):
    return ["run", str(EX / "packs" / pack), "--vault", str(EX / "vault.json"), "--types", "note,contact", *extra]


def test_thief_pack_is_killed_and_nothing_is_delivered(capsys):
    code = cli.main(argv("data-thief", "--model", "leak"))
    out = capsys.readouterr().out
    assert code == 2
    assert "KILLED" in out and "nothing delivered" in out
    assert "OFF_LENS_QUERY" in out and "chain verified" in out
    assert "000111222" not in out  # the real bank number never reaches the output


def test_honest_pack_completes(monkeypatch, capsys):
    class Fake:
        def __init__(self, *a, **k): ...
        def complete(self, prompt, inputs):
            assert [r["id"] for r in inputs["read"]]  # it got in-lens records
            return ModelReply({"summary": "Several accounts are at risk of churn.", "risk": "high"}, tokens=10)

    monkeypatch.setattr(cli, "NebiusModel", Fake)
    monkeypatch.setattr(cli, "load_api_key", lambda env: "unused")
    code = cli.main(argv("private-analyst"))
    out = capsys.readouterr().out
    assert code == 0 and "OK" in out and "at risk of churn" in out


def test_journal_file_is_written(tmp_path, capsys):
    j = tmp_path / "run.jsonl"
    cli.main(argv("data-thief", "--model", "leak", "--journal", str(j)))
    assert j.exists() and len(j.read_text(encoding="utf-8").splitlines()) >= 5


def test_unknown_command_exits():
    with pytest.raises(SystemExit):
        cli.main(["nope"])


def test_improve_then_approve_publishes_a_better_version(tmp_path, monkeypatch, capsys):
    from test_improve import GOOD_VARIANT, PromptSensitive
    from bridge.world import open_world

    class Fake(PromptSensitive):
        model = "fake-model"

        def __init__(self, *a, **k):
            super().__init__([GOOD_VARIANT])

    monkeypatch.setattr(cli, "NebiusModel", Fake)
    monkeypatch.setattr(cli, "load_api_key", lambda env: "unused")
    state = tmp_path / "state"
    world = open_world(state)
    world.registry.publish(EX / "packs" / "private-analyst", world.author_key)

    assert cli.main(["improve", "private-analyst", "--packs", str(EX / "packs"), "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "<- chosen" in out and "prompt_only=True" in out and "bridge approve" in out

    assert cli.main(["approve", "private-analyst", "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "published" in out and "0.2.0:" in out and "0.2.1:" in out
    ids = sorted(r.version for r in open_world(state).registry.records.values())
    assert ids == ["0.2.0", "0.2.1"]


def test_approve_without_a_candidate_refuses(tmp_path, capsys):
    assert cli.main(["approve", "nothing", "--state", str(tmp_path / "s")]) == 2
    assert "no candidate" in capsys.readouterr().out


def test_paypal_check_reports_missing_credentials_without_crashing(tmp_path, capsys):
    assert cli.main(["paypal-check", "--env", str(tmp_path / "none.env")]) == 2
    assert "FAILED" in capsys.readouterr().out


def test_paypal_check_with_a_fake_transport_creates_an_order_and_never_approves(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    env.write_text("PAYPAL_CLIENT_ID=i\nPAYPAL_CLIENT_SECRET=s\n", encoding="utf-8")
    calls = []

    def http(method, url, headers, body):
        calls.append(url)
        if url.endswith("/v1/oauth2/token"):
            return 200, {"access_token": "T"}
        return 201, {"id": "ORD1", "links": [{"rel": "approve", "href": "https://sb/approve/ORD1"}]}

    from bridge.payments import paypal
    monkeypatch.setattr(cli, "PayPalSandbox", lambda cid, sec: paypal.PayPalSandbox(cid, sec, http=http))
    assert cli.main(["paypal-check", "--env", str(env)]) == 0
    out = capsys.readouterr().out
    assert "nothing was charged" in out and "ORD1" in out
    assert not any("/authorize" in u or "/capture" in u for u in calls)  # it only created an order
