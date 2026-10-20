import pytest

from bridge.memory.vault import Record, Vault

ORIGIN = {"pack_digest": "sha256:ab", "run_id": "r1", "proposal_id": "p1"}


def test_user_record_defaults_to_tier_3_without_origin():
    r = Record("a", "note", "low", "hi")
    assert r.trust_tier == 3 and r.origin is None


def test_foreign_record_must_have_origin():
    with pytest.raises(ValueError, match="where it came from"):
        Record("a", "note", "low", "hi", trust_tier=1)
    assert Record("a", "note", "low", "hi", trust_tier=1, origin=ORIGIN).origin == ORIGIN


def test_bad_tier_rejected():
    with pytest.raises(ValueError):
        Record("a", "note", "low", "hi", trust_tier=9)


def test_remove_returns_the_record_or_none():
    v = Vault([Record("a", "note", "low", "hi")])
    assert v.remove("a").id == "a" and v.remove("a") is None and v.get("a") is None


def test_save_and_load_round_trip_keeps_origin_and_tier(tmp_path):
    v = Vault([Record("a", "note", "low", "mine"), Record("q1", "note", "low", "from pack", 1, ORIGIN)])
    p = tmp_path / "vault.json"
    v.save(p)
    again = Vault.load(p)
    assert again.get("q1").origin == ORIGIN and again.get("q1").trust_tier == 1 and again.get("a").trust_tier == 3


def test_duplicate_id_rejected():
    with pytest.raises(ValueError):
        Vault([Record("a", "note", "low", "x"), Record("a", "note", "low", "y")])
