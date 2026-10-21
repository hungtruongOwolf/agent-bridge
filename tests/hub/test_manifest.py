import copy

import pytest
import yaml
from pathlib import Path

from bridge.hub.manifest import profile_fields, validate

EX = Path(__file__).resolve().parent.parent.parent / "examples" / "packs"
GOOD = yaml.safe_load((EX / "private-analyst" / "pack.yaml").read_text(encoding="utf-8"))


def broken(**changes):
    m = copy.deepcopy(GOOD)
    for k, v in changes.items():
        if v is None:
            m.pop(k, None)
        else:
            m[k] = v
    return m


def test_every_example_pack_can_be_listed():
    for d in EX.iterdir():
        assert validate(yaml.safe_load((d / "pack.yaml").read_text(encoding="utf-8"))) == [], d.name


def test_a_pack_with_no_skills_cannot_be_listed():
    assert any("skills" in p for p in validate(broken(skills=None)))
    assert any("1 to 5" in p for p in validate(broken(skills=[])))


def test_a_skill_must_say_what_it_does_and_give_example_questions():
    vague = [{"name": "Helps", "does": "Helps.", "try_asking": ["Hi"]}]
    problems = validate(broken(skills=vague))
    assert any("does must say" in p for p in problems)
    none = [{"name": "Spot risk", "does": "Names accounts that look likely to leave.", "try_asking": []}]
    assert any("try_asking" in p for p in validate(broken(skills=none)))


def test_two_skills_cannot_share_a_name_and_there_is_a_cap():
    s = {"name": "Spot risk", "does": "Names accounts that look likely to leave.", "try_asking": ["Which accounts?"]}
    assert any("same name" in p for p in validate(broken(skills=[s, dict(s)])))
    many = [dict(s, name=f"Skill number {i}") for i in range(6)]
    assert any("1 to 5" in p for p in validate(broken(skills=many)))


def test_limits_and_needs_are_short_lists():
    assert any("limits" in p for p in validate(broken(limits=["x"] * 6)))
    assert any("needs" in p for p in validate(broken(needs="note")))


def test_a_one_word_summary_is_refused():
    assert any("summary" in p for p in validate(broken(summary="Nice")))


def test_the_listing_keeps_only_the_vetted_fields():
    f = profile_fields(GOOD)
    assert [s["name"] for s in f["skills"]][0] == "Spot accounts at risk"
    assert f["needs"] == ["note", "contact"] and f["speciality"] == "Sales accounts" and len(f["limits"]) == 3
    assert set(f) == {"skills", "speciality", "needs", "limits"}


def test_non_mapping_manifests_do_not_crash():
    for bad in (None, [], "text", 5):
        assert validate(bad) == ["pack.yaml must be a mapping"]
