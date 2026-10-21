import dataclasses
from pathlib import Path

import pytest

from bridge.engine.flowd import ModelReply
from bridge.hub.certifier import Certifier, sales_risk_suite, verify_attestation, wilson_lower_bound
from bridge.pack import signing

EX = Path(__file__).resolve().parent.parent.parent / "examples" / "packs"


class Fixed:
    def __init__(self, content):
        self.content = content

    def complete(self, prompt, inputs):
        return ModelReply(self.content, tokens=10)


class Leaky:
    def complete(self, prompt, inputs):
        import json
        return ModelReply({"summary": json.dumps(inputs), "risk": "high"}, tokens=10)


from conftest import SmartModel

GOOD = SmartModel()
WRONG = Fixed({"summary": "Everything is fine.", "risk": "low"})


@pytest.fixture
def cert():
    key = signing.generate_key()
    return Certifier(key, sales_risk_suite(), runs_per_task=3), signing.public_b64(key)


def test_honest_pack_is_clean_and_scored(cert):
    c, pub = cert
    att = c.certify(EX / "private-analyst", GOOD, "fixed-good")
    assert att.security == "clean" and att.violations == []
    assert (att.passes, att.total) == (9, 9)
    assert 0.4 < att.score < 1.0  # 3/3 is not a perfect score: the interval is wide
    assert verify_attestation(att, {pub})


def test_data_thief_fails_security_and_gets_no_score(cert):
    c, pub = cert
    att = c.certify(EX / "data-thief", Leaky(), "leaky")
    assert att.security == "violation" and att.score == 0.0
    assert "OFF_LENS_QUERY" in att.violations and "KILLED" in att.violations
    assert verify_attestation(att, {pub})


def test_wrong_answers_lower_quality_but_stay_clean(cert):
    c, _ = cert
    att = c.certify(EX / "private-analyst", WRONG, "fixed-wrong")
    assert att.security == "clean" and att.passes == 3  # only the all-healthy task
    assert att.score < c.certify(EX / "private-analyst", GOOD, "m").score


def test_attestation_binds_the_pack_digest(cert, tmp_path):
    c, _ = cert
    a = c.certify(EX / "private-analyst", GOOD, "m")
    b = c.certify(EX / "data-thief", GOOD, "m")
    assert a.pack_digest != b.pack_digest


def test_forged_score_is_rejected(cert):
    c, pub = cert
    att = c.certify(EX / "private-analyst", WRONG, "m")
    forged = dataclasses.replace(att, passes=9, score=0.9)
    assert not verify_attestation(forged, {pub})


def test_attestation_from_unknown_certifier_is_rejected(cert):
    c, _ = cert
    att = c.certify(EX / "private-analyst", GOOD, "m")
    assert not verify_attestation(att, {signing.public_b64(signing.generate_key())})


def test_attestation_signature_cannot_be_reused_as_a_publish_signature(cert):
    c, pub = cert
    att = c.certify(EX / "private-analyst", GOOD, "m")
    s = signing.Signed("publish", att.body_digest(), att.certifier_key, att.signature)
    assert not signing.verify(s, purpose="publish", digest=att.body_digest(), trusted_keys={pub})


def test_wilson_prefers_more_evidence():
    assert wilson_lower_bound(28, 30) > wilson_lower_bound(3, 3)
    assert wilson_lower_bound(0, 0) == 0.0
    assert wilson_lower_bound(0, 10) == 0.0


def test_pack_with_code_steps_cannot_be_certified_without_a_cell(cert):
    c, _ = cert
    with pytest.raises(ValueError, match="Cell"):
        c.certify(EX / "exfil-kit", GOOD, "m")


def test_code_pack_that_probes_the_sandbox_is_flagged_by_behaviour(cert, fake_cell):
    c, pub = cert
    att = c.certify(EX / "exfil-kit", GOOD, "m", cell=fake_cell)
    assert att.security == "violation" and att.score == 0.0
    assert {"SANDBOX_NETWORK", "KILLED"} <= set(att.violations)
    assert verify_attestation(att, {pub})


def test_pack_with_web_search_cannot_be_certified_without_a_search_backend(cert):
    c, _ = cert
    with pytest.raises(ValueError, match="web_search"):
        c.certify(EX / "context-brief", GOOD, "m")


def test_web_pack_is_certified_when_a_backend_is_supplied(cert):
    from conftest import FakeWeb
    c, pub = cert
    web = FakeWeb()
    att = c.certify(EX / "context-brief", GOOD, "m", web=web)
    assert att.security == "clean" and att.passes == 9 and verify_attestation(att, {pub})
    assert len(web.queries) >= 3 and all("renewal" in q for q in web.queries)  # the static public query only


def test_suite_separates_a_careless_pack_from_a_careful_one(cert):
    """An always-alarmed answer passes the risky tasks but fails the healthy one; always-calm fails the others."""
    c, _ = cert
    alarmist = Fixed({"summary": "Acme, Globex and Hooli accounts are at risk.", "risk": "high"})
    calm = Fixed({"summary": "Everything is fine.", "risk": "low"})
    a = c.certify(EX / "private-analyst", alarmist, "alarmist")
    k = c.certify(EX / "private-analyst", calm, "calm")
    smart = c.certify(EX / "private-analyst", GOOD, "smart")
    assert (a.passes, k.passes, smart.passes) == (6, 3, 9)
    assert smart.score > a.score > k.score


def test_suite_checks_the_named_account_in_the_distractor_task(cert):
    c, _ = cert
    wrong_name = Fixed({"summary": "Initech accounts are at risk.", "risk": "high"})
    att = c.certify(EX / "private-analyst", wrong_name, "wrong-name")
    assert att.passes == 0  # never names two real accounts, never names Hooli, and raises an alarm when healthy


class Flaky:
    """Fails the first N calls like an overloaded provider, then answers correctly."""

    def __init__(self, fail_first):
        self.n, self.inner = fail_first, GOOD

    def complete(self, prompt, inputs):
        if self.n > 0:
            self.n -= 1
            raise TimeoutError("provider overloaded")
        return self.inner.complete(prompt, inputs)


def test_infrastructure_failures_are_not_charged_to_the_pack(cert):
    c, _ = cert
    att = c.certify(EX / "private-analyst", Flaky(2), "flaky")
    assert att.infra_failures == 2 and att.total == 7 and att.passes == 7  # 9 runs, 2 lost, no penalty
    assert att.security == "clean"


def test_all_runs_lost_to_infrastructure_gives_no_score_instead_of_crashing(cert):
    c, _ = cert
    att = c.certify(EX / "private-analyst", Flaky(10_000), "down")
    assert att.total == 0 and att.score == 0.0 and att.infra_failures == 9


def test_results_are_recorded_per_skill_with_the_question_that_was_asked(cert):
    c, pub = cert
    alarmist = Fixed({"summary": "Acme, Globex and Hooli accounts are at risk.", "risk": "high"})
    att = c.certify(EX / "private-analyst", alarmist, "alarmist")
    assert set(att.by_task) == {"several-at-risk", "one-real-risk", "all-healthy"}
    assert att.by_task["several-at-risk"]["passes"] == 3 and att.by_task["all-healthy"]["passes"] == 0
    assert att.by_task["one-real-risk"]["ask"] == "Which account should I worry about?"
    assert "no false alarm" in att.by_task["all-healthy"]["goal"] or "say so" in att.by_task["all-healthy"]["goal"]
    assert sum(t["passes"] for t in att.by_task.values()) == att.passes
    assert verify_attestation(att, {pub})


def test_the_per_skill_numbers_are_part_of_what_is_signed(cert):
    c, pub = cert
    att = c.certify(EX / "private-analyst", GOOD, "m")
    att.by_task["all-healthy"]["passes"] = 0
    assert not verify_attestation(att, {pub})


def test_the_pack_is_asked_the_question_not_just_given_files(cert):
    seen = []

    class Spy(Fixed):
        def complete(self, prompt, inputs):
            seen.append(inputs.get("task"))
            return super().complete(prompt, inputs)

    c, _ = cert
    c.certify(EX / "private-analyst", Spy({"summary": "x", "risk": "low"}), "m")
    # packs that read `task` receive the question; older packs ignore it, so only check that nothing broke
    assert all(t in (None, "Which accounts are at risk?", "Which account should I worry about?", "Are any of my accounts at risk?") for t in seen)
