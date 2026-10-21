import json
from pathlib import Path

import pytest

from bridge.engine.flowd import ModelReply
from bridge.memory.broker import Lens
from bridge.memory.vault import Record, Vault
from bridge.runner import run_pack

EX = Path(__file__).resolve().parent.parent / "examples"


def vault():
    return Vault([Record(**r) for r in json.loads((EX / "vault.json").read_text(encoding="utf-8"))])


class Good:
    def complete(self, prompt, inputs):
        return ModelReply({"summary": "Several accounts are at risk.", "risk": "high"}, tokens=7)


class Leaky:
    def complete(self, prompt, inputs):
        return ModelReply({"summary": json.dumps(inputs), "risk": "high"}, tokens=7)


LENS = Lens(types=frozenset({"note", "contact"}))


def test_honest_run_report():
    rep = run_pack(EX / "packs" / "private-analyst", vault(), LENS, Good(), seed="s")
    assert rep.outcome == "COMPLETE" and rep.result["risk"] == "high"
    assert rep.staged["count"] == 3 and set(rep.withheld) == {"n3", "f1"}
    assert rep.journal_ok and rep.journal_entries >= 8
    assert set(rep.records_handed) <= {"n1", "n2", "c1"}
    json.dumps(rep.__dict__)  # serialisable for the web API
    started = [s for s in rep.steps if s["event"] == "step_started"]
    assert [s["kind"] for s in started] == ["tool", "llm", "gate", "return"]  # step kind is not overwritten


def test_thief_run_report_shows_kill_and_no_result():
    rep = run_pack(EX / "packs" / "data-thief", vault(), LENS, Leaky(), seed="s")
    assert rep.outcome == "KILLED" and rep.result is None
    assert [e["kind"] for e in rep.broker_events] == ["OFF_LENS_QUERY"]
    assert any(s["event"] == "incident" for s in rep.steps)
    assert "000111222" not in json.dumps(rep.__dict__)  # the real bank number is nowhere in the report


def test_digest_mismatch_refuses_to_run():
    with pytest.raises(ValueError, match="does not match"):
        run_pack(EX / "packs" / "private-analyst", vault(), LENS, Good(), seed="s", expected_digest="sha256:" + "0" * 64)


def test_report_carries_the_audit_journal_and_a_plain_summary():
    rep = run_pack(EX / "packs" / "private-analyst", vault(), LENS, Good(), seed="s")
    assert rep.journal[0]["kind"] == "run_started" and rep.journal[-1]["kind"] == "run_finished"
    assert all(len(e["hash"]) == 12 for e in rep.journal) and len(rep.journal) == rep.journal_entries
    assert rep.summary == "Delivered a result after reading 3 record(s); 2 stayed private."


def test_summaries_for_each_kind_of_ending():
    killed = run_pack(EX / "packs" / "data-thief", vault(), LENS, Leaky(), seed="s")
    assert killed.summary == "Stopped for OFF_LENS_QUERY; nothing was delivered."

    class Down:
        def complete(self, prompt, inputs):
            raise TimeoutError("x")
    assert "not blamed" in run_pack(EX / "packs" / "private-analyst", vault(), LENS, Down(), seed="s").summary
