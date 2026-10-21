import shutil
from pathlib import Path

import pytest

from bridge.hub.certifier import Certifier, sales_risk_suite
from bridge.hub.market import Marketplace
from bridge.hub.registry import Listing, Registry
from bridge.pack import signing

from conftest import SmartModel

EX = Path(__file__).resolve().parent.parent.parent / "examples" / "packs"


@pytest.fixture
def market(tmp_path):
    author, ck = signing.generate_key(), signing.generate_key()
    reg = Registry()
    m = Marketplace(reg, {signing.public_b64(ck)})
    cert = Certifier(ck, sales_risk_suite(), runs_per_task=1)
    from conftest import FakeCell, FakeWeb
    for name in ("private-analyst", "deal-brief", "context-brief", "data-thief"):
        d = tmp_path / name
        shutil.copytree(EX / name, d)
        reg.publish(d, author, Listing(price_usd=0.5))
        m.add_attestation(cert.certify(d, SmartModel() if name != "data-thief" else __import__("test_certifier").Leaky(), "m", web=FakeWeb()))
    return m


def test_a_question_finds_the_helper_whose_skill_fits(market):
    top = market.match("Which accounts need attention first?")[0]
    assert top["matched"] and top["reason"].startswith("Good at")


def test_market_questions_find_the_web_helper(market):
    top = market.match("how is the market doing for my accounts, anything in the news?")[0]
    assert top["id"] == "context-brief"


def test_a_helper_caught_cheating_is_never_suggested(market):
    assert all(m["id"] != "friendly-helper" for m in market.match("anything new? summarize my notes"))


def test_a_question_nobody_covers_is_said_plainly(market):
    top = market.match("translate my poem into french")[0]
    assert not top["matched"] and "Nothing it says matches" in top["reason"]


def test_matching_returns_a_clickable_example_question(market):
    top = market.match("brief me on my deals")[0]
    assert top["example"] and top["price_cents"] > 0


def test_only_the_newest_version_of_a_helper_is_listed_or_suggested(tmp_path):
    import shutil
    author, ck = signing.generate_key(), signing.generate_key()
    reg = Registry()
    m = Marketplace(reg, {signing.public_b64(ck)})
    for v in ("0.2.0", "0.3.0"):
        d = tmp_path / v
        shutil.copytree(EX / "private-analyst", d)
        f = d / "pack.yaml"
        f.write_bytes(f.read_bytes().replace(b"version: 0.2.0", ("version: " + v).encode(), 1))
        reg.publish(d, author, Listing(price_usd=0.5))
    assert [r["version"] for r in m.ranked()] == ["0.3.0"]
    assert [x["key"].endswith("0.3.0") for x in m.match("which accounts are at risk")] == [True]
