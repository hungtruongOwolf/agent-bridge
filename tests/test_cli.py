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
