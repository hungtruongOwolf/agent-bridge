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


def test_attestations_persist_and_are_reverified_on_load(world, tmp_path):
    reg, market, cert, packs = world
    path = tmp_path / "atts.json"
    m1 = Marketplace(reg, market.trusted, path)
    m1.add_attestation(cert.certify(packs["private-analyst"][0], Fixed(), "fixed"))
    assert Marketplace(reg, market.trusted, path).ranked()[0]["status"] == "certified"
    # a different trust set (certifier no longer trusted) drops the stored attestation
    assert Marketplace(reg, {"someone-else"}, path).ranked()[0]["status"] == "uncertified"


def test_a_profile_separates_what_the_author_says_from_what_was_measured(world):
    reg, market, cert, packs = world
    good_dir, good = packs["private-analyst"]
    market.add_attestation(cert.certify(good_dir, Fixed(), "fixed"))
    p = market.profile(good.key)
    assert [s["name"] for s in p["author_says"]["skills"]] == ["Spot accounts at risk", "Answer questions about your sales notes"]
    assert p["author_says"]["good_to_know"] and p["measured"]["tested"] and p["measured"]["suite"] == "sales-risk v3"
    skills = {s["what"]: (s["passes"], s["total"]) for s in p["measured"]["by_skill"]}
    assert len(skills) == 6 and all(t == 3 for _, t in skills.values())


def test_what_a_pack_can_touch_is_read_from_its_program_not_from_its_claims(world):
    reg, market, cert, packs = world
    plain = market.profile(packs["private-analyst"][1].key)
    kinds = [w["kind"] for w in plain["works_with"]]
    assert kinds[0] == "files" and "web" not in kinds and "program" not in kinds
    assert "Use the internet." in plain["cannot"] and "Send your files to anyone." in plain["cannot"]
    code = market.profile(packs["exfil-kit"][1].key) if "exfil-kit" in packs else None
    assert code is None or "program" in [w["kind"] for w in code["works_with"]]


def test_a_flagged_pack_shows_what_it_did_instead_of_a_score(world):
    reg, market, cert, packs = world
    market.add_attestation(cert.certify(packs["data-thief"][0], Leaky(), "leaky"))
    m = market.profile(packs["data-thief"][1].key)["measured"]
    assert m["status"] == "flagged" and "score" not in m and "OFF_LENS_QUERY" in m["violations"]


def test_an_untested_pack_says_so_plainly(world):
    reg, market, cert, packs = world
    m = market.profile(packs["private-analyst"][1].key)["measured"]
    assert m["tested"] is False and "not ranked" in m["note"]


def test_unknown_or_revoked_packs_have_no_profile(world):
    reg, market, cert, packs = world
    with pytest.raises(MarketError):
        market.profile("nope/none@1.0.0")
    key = packs["private-analyst"][1].key
    reg.revoke(key, "malicious-confirmed")
    with pytest.raises(MarketError):
        market.profile(key)


def test_listing_rows_carry_skill_names_and_what_the_pack_uses(world):
    reg, market, cert, packs = world
    row = next(r for r in market.ranked() if r["id"] == "private-analyst")
    assert row["skills"][0] == "Spot accounts at risk" and row["web"] is False and row["code"] is False


def test_equal_scores_are_ordered_by_the_lower_price(world, tmp_path):
    reg, market, cert, packs = world
    dear_dir = tmp_path / "quick-skim-dear"
    shutil.copytree(EX / "quick-skim", dear_dir)
    cheap_dir = tmp_path / "quick-skim-cheap"
    shutil.copytree(EX / "quick-skim", cheap_dir)
    for d, name in ((dear_dir, "quick-skim-dear"), (cheap_dir, "quick-skim-cheap")):  # two different helpers
        f = d / "pack.yaml"
        f.write_bytes(f.read_bytes().replace(b"id: quick-skim", ("id: " + name).encode(), 1))
    author = signing.generate_key()
    dear = reg.publish(dear_dir, author, Listing(price_usd=0.9))
    cheap = reg.publish(cheap_dir, author, Listing(price_usd=0.2))
    for d in (dear_dir, cheap_dir):
        market.add_attestation(cert.certify(d, Fixed(), "fixed"))
    rows = [r for r in market.ranked() if r["status"] == "certified"]
    assert [r["key"] for r in rows][:2] == [cheap.key, dear.key] and rows[0]["score"] == rows[1]["score"]
