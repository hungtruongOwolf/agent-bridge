from pathlib import Path

from bridge.engine.flowd import ModelReply
from bridge.world import open_world, seed

PACKS = Path(__file__).resolve().parent.parent / "examples" / "packs"


class Fixed:
    def complete(self, prompt, inputs):
        return ModelReply({"summary": "Acme and Globex accounts are at risk.", "risk": "high"}, tokens=1)


def test_seed_builds_a_ranked_market_that_survives_restart(tmp_path):
    w = open_world(tmp_path / "state")
    seed(w, PACKS, Fixed(), "fixed", log=lambda *_: None)
    rows = {r["id"]: r for r in w.market.ranked()}
    assert rows["private-analyst"]["status"] == "certified" and rows["deal-brief"]["status"] == "certified"
    assert sorted(r["rank"] for r in rows.values() if "rank" in r) == [1, 2]
    assert rows["friendly-helper"]["status"] == "flagged"

    again = open_world(tmp_path / "state")  # same keys, registry and attestations are reloaded
    rows2 = {r["id"]: r for r in again.market.ranked()}
    assert rows2["private-analyst"]["status"] == "certified"
    assert rows2["friendly-helper"]["status"] == "flagged"


def test_keys_are_stable_across_opens(tmp_path):
    a = open_world(tmp_path / "s")
    b = open_world(tmp_path / "s")
    from bridge.pack import signing
    assert signing.public_b64(a.author_key) == signing.public_b64(b.author_key)
