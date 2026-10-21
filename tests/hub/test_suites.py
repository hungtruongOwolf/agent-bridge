import pytest

from bridge.hub.suites import SuiteError, available, load_suite, make_check, parse_suite

BASE = """
id: tiny
version: "1"
lens_types: [note]
record_sets:
  a: [{id: n1, type: note, sensitivity: low, text: "Hello there"}]
tasks:
  - {name: t1, records: [a], ask: "Hi?", check: {contains_any: [hello]}}
trap: {records: [a]}
"""


def test_the_built_in_suites_load_and_describe_the_same_work_as_before():
    s = load_suite("sales-risk")
    assert s.id == "sales-risk" and len(s.quality) == 6 and any(t.history for t in s.quality)
    assert {"sales-risk", "sales-risk-dev"} <= set(available())


def test_checks_are_plain_conditions():
    c = make_check({"risk_in": ["high"], "contains_all": ["acme"], "contains_n": {"terms": ["x", "y", "z"], "at_least": 2}}, "t")
    assert c({"summary": "Acme, x and y", "risk": "high"})
    assert not c({"summary": "Acme, x", "risk": "high"}) and not c({"summary": "Acme x y", "risk": "low"})
    assert not c("not a dict")


@pytest.mark.parametrize("bad,msg", [
    (BASE.replace("contains_any", "contians_any"), "unknown condition"),
    (BASE.replace("records: [a], ask", "records: [zzz], ask"), "unknown record set"),
    (BASE.replace("check: {contains_any: [hello]}", "check: {}"), "at least one condition"),
    (BASE.replace("tasks:", "tasksx:"), "missing 'tasks'"),
])
def test_a_typo_in_a_suite_fails_loudly(bad, msg):
    with pytest.raises(SuiteError, match=msg):
        parse_suite(bad)


def test_a_pack_can_name_its_suite_and_unknown_names_are_refused(tmp_path):
    import shutil
    from pathlib import Path
    from bridge.hub.certifier import Certifier
    from bridge.pack import signing
    from conftest import SmartModel
    ex = Path(__file__).resolve().parent.parent.parent / "examples" / "packs"
    c = Certifier(signing.generate_key(), load_suite("sales-risk"), runs_per_task=1, suites={"sales-risk-dev": load_suite("sales-risk-dev")})
    d = tmp_path / "p"
    shutil.copytree(ex / "private-analyst", d)
    f = d / "pack.yaml"
    f.write_bytes(f.read_bytes().replace(b"speciality:", b"suite: sales-risk-dev\nspeciality:", 1))
    assert c.certify(d, SmartModel(), "m").suite == "sales-risk-dev"
    f.write_bytes(f.read_bytes().replace(b"sales-risk-dev", b"nope", 1))
    with pytest.raises(ValueError, match="no test suite named"):
        c.certify(d, SmartModel(), "m")
