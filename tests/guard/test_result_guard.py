import pytest

from bridge.guard.result_guard import ResultGuard, longest_shared_run
from bridge.memory.broker import Verdict

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "risk"],
    "properties": {
        "summary": {"type": "string", "maxLength": 400},
        "risk": {"enum": ["low", "medium", "high"]},
    },
}
RECORD = "Sales pipeline: three big accounts at risk because the renewal budget was cut in half this quarter"


def guard(**kw):
    return ResultGuard(SCHEMA, **kw)


def test_clean_result_passes():
    r = guard().check({"summary": "Two accounts need attention.", "risk": "medium"},
                      canaries=["CANARY-abc"], lens_texts=[RECORD])
    assert r.verdict is Verdict.ALLOW


def test_canary_in_output_kills():
    r = guard().check({"summary": "see CANARY-abc123 for more", "risk": "low"},
                      canaries=["CANARY-abc123"], lens_texts=[])
    assert r.verdict is Verdict.KILL and r.evidence == "canary"


def test_canary_hidden_by_spacing_and_case_still_kills():
    r = guard().check({"summary": "c-a-n-a-r-y abc 123".replace("-", ""), "risk": "low"},
                      canaries=["CANARY-abc123"], lens_texts=[])
    assert r.verdict is Verdict.KILL


def test_canary_checked_before_schema():
    r = guard().check({"summary": "CANARY-x", "risk": "nope", "extra": 1}, canaries=["CANARY-x"], lens_texts=[])
    assert r.verdict is Verdict.KILL


def test_schema_violation_denied():
    r = guard().check({"summary": "ok", "risk": "extreme"}, canaries=[], lens_texts=[])
    assert r.verdict is Verdict.DENY and r.reasons[0].startswith("schema")


def test_extra_field_denied():
    r = guard().check({"summary": "ok", "risk": "low", "notes": "x"}, canaries=[], lens_texts=[])
    assert r.verdict is Verdict.DENY


def test_oversized_result_denied():
    r = guard(max_bytes=50).check({"summary": "x" * 100, "risk": "low"}, canaries=[], lens_texts=[])
    assert r.verdict is Verdict.DENY and "larger" in r.reasons[0]


def test_verbatim_dump_of_a_record_denied():
    r = guard().check({"summary": RECORD, "risk": "low"}, canaries=[], lens_texts=[RECORD])
    assert r.verdict is Verdict.DENY and "verbatim" in r.reasons[0]


def test_short_quote_is_fine():
    r = guard().check({"summary": "three big accounts at risk", "risk": "high"}, canaries=[], lens_texts=[RECORD])
    assert r.verdict is Verdict.ALLOW


def test_longest_shared_run():
    assert longest_shared_run("hello brave new world", "xx brave new yy") == len("bravenew")
    assert longest_shared_run("abc", "xyz") == 0


def test_bad_schema_rejected_at_construction():
    with pytest.raises(Exception):
        ResultGuard({"type": "not-a-type"})


def test_schema_denial_never_repeats_the_offending_value():
    secret = "Bank account 000111222 balance 91000 " * 30
    r = guard().check({"summary": secret, "risk": "low"}, canaries=[], lens_texts=[])
    assert r.verdict is Verdict.DENY
    assert "000111222" not in " ".join(r.reasons) and "summary breaks maxLength" in r.reasons[0]
