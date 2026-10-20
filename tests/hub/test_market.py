import dataclasses
import shutil
from pathlib import Path

import pytest

from bridge.engine.flowd import ModelReply
from bridge.hub.certifier import Certifier, sales_risk_suite
from bridge.hub.market import Marketplace, MarketError
from bridge.hub.registry import Listing, Registry
from bridge.pack import signing

EX = Path(__file__).resolve().parent.parent.parent / "examples" / "packs"


class Fixed:
    def complete(self, prompt, inputs):
        return ModelReply({"summary": "Acme and Globex accounts are at risk.", "risk": "high"}, tokens=1)


class Leaky:
    def complete(self, prompt, inputs):
        import json
        return ModelReply({"summary": json.dumps(inputs), "risk": "high"}, tokens=1)


@pytest.fixture
def world(tmp_path):
    author, certkey = signing.generate_key(), signing.generate_key()
    reg = Registry()
    packs = {}
    for name in ("private-analyst", "data-thief"):
        dst = tmp_path / name
        shutil.copytree(EX / name, dst)
        packs[name] = (dst, reg.publish(dst, author, Listing(price_usd=0.5)))
    market = Marketplace(reg, {signing.public_b64(certkey)})
    return reg, market, Certifier(certkey, sales_risk_suite(), runs_per_task=3), packs


def test_certified_pack_ranks_above_uncertified_even_with_more_stars(world):
    reg, market, cert, packs = world
    good_dir, good = packs["private-analyst"]
    _, thief = packs["data-thief"]
    for u in ("a", "b", "c", "d"):
        reg.star(thief.key, u)  # popularity must not buy rank
    market.add_attestation(cert.certify(good_dir, Fixed(), "fixed"))
    rows = market.ranked()
    assert [r["id"] for r in rows] == ["private-analyst", "friendly-helper"]
    assert rows[0]["status"] == "certified" and rows[0]["rank"] == 1 and rows[0]["score"] > 0
    assert rows[1]["status"] == "uncertified" and "rank" not in rows[1]


def test_security_violation_is_flagged_not_ranked(world):
    reg, market, cert, packs = world
    market.add_attestation(cert.certify(packs["data-thief"][0], Leaky(), "leaky"))
    market.add_attestation(cert.certify(packs["private-analyst"][0], Fixed(), "fixed"))
    rows = {r["id"]: r for r in market.ranked()}
    assert rows["friendly-helper"]["status"] == "flagged"
    assert rows["friendly-helper"]["score"] is None and "OFF_LENS_QUERY" in rows["friendly-helper"]["violations"]
    assert market.ranked()[-1]["id"] == "friendly-helper"


def test_attestation_from_untrusted_certifier_refused(world):
    reg, market, _, packs = world
    rogue = Certifier(signing.generate_key(), sales_risk_suite(), runs_per_task=1)
    with pytest.raises(MarketError, match="trusted Certifier"):
        market.add_attestation(rogue.certify(packs["private-analyst"][0], Fixed(), "m"))


def test_attestation_for_unknown_digest_refused(world, tmp_path):
    reg, market, cert, packs = world
    other = tmp_path / "other"
    shutil.copytree(packs["private-analyst"][0], other)
    (other / "pack.yaml").write_bytes((other / "pack.yaml").read_bytes() + b"# x\n")
    with pytest.raises(MarketError, match="does not hold"):
        market.add_attestation(cert.certify(other, Fixed(), "m"))


def test_revoked_pack_disappears_from_the_market(world):
    reg, market, cert, packs = world
    market.add_attestation(cert.certify(packs["private-analyst"][0], Fixed(), "fixed"))
    reg.revoke(packs["private-analyst"][1].key, "malicious-confirmed")
    assert [r["id"] for r in market.ranked()] == ["friendly-helper"]


def test_forged_attestation_refused(world):
    reg, market, cert, packs = world
    att = cert.certify(packs["data-thief"][0], Leaky(), "leaky")
    forged = dataclasses.replace(att, security="clean", violations=[], score=0.9)
    with pytest.raises(MarketError):
        market.add_attestation(forged)
