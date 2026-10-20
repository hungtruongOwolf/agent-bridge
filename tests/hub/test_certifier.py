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


GOOD = Fixed({"summary": "Acme and Globex accounts are at risk.", "risk": "high"})
WRONG = Fixed({"summary": "Everything is fine.", "risk": "low"})


@pytest.fixture
def cert():
    key = signing.generate_key()
    return Certifier(key, sales_risk_suite(), runs_per_task=3), signing.public_b64(key)


def test_honest_pack_is_clean_and_scored(cert):
    c, pub = cert
    att = c.certify(EX / "private-analyst", GOOD, "fixed-good")
    assert att.security == "clean" and att.violations == []
    assert (att.passes, att.total) == (3, 3)
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
    assert att.security == "clean" and att.passes == 0 and att.score == 0.0


def test_attestation_binds_the_pack_digest(cert, tmp_path):
    c, _ = cert
    a = c.certify(EX / "private-analyst", GOOD, "m")
    b = c.certify(EX / "data-thief", GOOD, "m")
    assert a.pack_digest != b.pack_digest


def test_forged_score_is_rejected(cert):
    c, pub = cert
    att = c.certify(EX / "private-analyst", WRONG, "m")
    forged = dataclasses.replace(att, passes=3, score=0.9)
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
