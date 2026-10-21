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


def test_a_person_can_edit_a_record_and_a_foreign_one_becomes_theirs():
    v = Vault([Record("q1", "note", "low", "from a helper", 1, ORIGIN)])
    r = v.update("q1", now=50.0, text="my own wording")
    assert r.text == "my own wording" and r.trust_tier == 3 and r.edited and r.updated == 50.0
    assert r.origin == ORIGIN  # where it came from is never erased


def test_changing_only_the_sensitivity_does_not_count_as_an_edit_of_the_text():
    v = Vault([Record("q1", "note", "low", "from a helper", 1, ORIGIN)])
    r = v.update("q1", now=5.0, sensitivity="high")
    assert r.sensitivity == "high" and not r.edited and r.trust_tier == 1


def test_updating_nothing_or_a_missing_record():
    v = Vault([Record("a", "note", "low", "x")])
    assert v.update("a", now=1.0) is v.get("a")
    with pytest.raises(KeyError):
        v.update("nope", now=1.0, text="x")


def test_record_rules_are_enforced_on_every_path():
    with pytest.raises(ValueError, match="some text"):
        Record("a", "note", "low", "   ")
    with pytest.raises(ValueError, match="at most"):
        Record("a", "note", "low", "x" * 2001)
    with pytest.raises(ValueError, match="type must be"):
        Record("a", "Not A Type", "low", "x")
    v = Vault([Record("a", "note", "low", "x")])
    with pytest.raises(ValueError):
        v.update("a", now=1.0, text="")
    assert v.get("a").text == "x"


def test_new_ids_never_collide():
    v = Vault([Record("m1", "note", "low", "a"), Record("m7", "note", "low", "b"), Record("n1", "note", "low", "c")])
    assert v.next_id("m") == "m8" and v.next_id("u") == "u1"


def test_saving_is_atomic_and_old_files_without_timestamps_still_load(tmp_path):
    p = tmp_path / "vault.json"
    Vault([Record("a", "note", "low", "x", created=5.0)]).save(p)
    assert not (tmp_path / "vault.tmp").exists() and Vault.load(p).get("a").created == 5.0
    p.write_text('[{"id": "old", "type": "note", "sensitivity": "low", "text": "legacy", "trust_tier": 3, "origin": null}]', encoding="utf-8")
    assert Vault.load(p).get("old").created == 0.0
