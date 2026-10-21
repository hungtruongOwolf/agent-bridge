"""What a pack must say about itself before it can be listed, so a person can tell what they are hiring.

A listing that only says "a helpful agent" is not allowed. Every pack names at least one concrete skill,
says what it does in plain words, and gives example questions a person could really ask it. Packs may also
say which file types they work with and what they cannot do. These statements are the author's claims:
the profile page shows them next to what the Certifier actually measured.
"""
from __future__ import annotations

from ..guard.result_guard import unbounded

REQUIRED = ("id", "version", "author", "summary", "skills", "result_schema")
MAX_SKILLS = 5
LIMITS = {"name": (3, 60), "does": (10, 240), "ask": (3, 120), "limit": (3, 140), "summary": (10, 200), "speciality": (2, 60)}


def _text(v, lo: int, hi: int) -> bool:
    return isinstance(v, str) and lo <= len(v.strip()) <= hi


def validate(manifest) -> list[str]:
    """Every reason the manifest cannot be listed; an empty list means it can."""
    if not isinstance(manifest, dict):
        return ["pack.yaml must be a mapping"]
    problems = [f"pack.yaml is missing {f}" for f in REQUIRED if not manifest.get(f)]
    if not _text(manifest.get("summary"), *LIMITS["summary"]) and manifest.get("summary"):
        problems.append("summary must be 10 to 200 characters of plain words")
    if manifest.get("suite") is not None and not (isinstance(manifest["suite"], str) and 2 <= len(manifest["suite"]) <= 60):
        problems.append("suite must be the name of a test suite")
    if manifest.get("speciality") is not None and not _text(manifest["speciality"], *LIMITS["speciality"]):
        problems.append("speciality must be 2 to 60 characters")
    skills = manifest.get("skills")
    if skills is not None:
        if not isinstance(skills, list) or not 1 <= len(skills) <= MAX_SKILLS:
            problems.append(f"skills must list 1 to {MAX_SKILLS} skills")
        else:
            seen = set()
            for i, s in enumerate(skills, 1):
                tag = f"skill {i}"
                if not isinstance(s, dict):
                    problems.append(f"{tag} must be a mapping with name, does and try_asking")
                    continue
                if not _text(s.get("name"), *LIMITS["name"]):
                    problems.append(f"{tag}: name must be 3 to 60 characters")
                elif s["name"].strip().lower() in seen:
                    problems.append(f"{tag}: two skills have the same name")
                else:
                    seen.add(s["name"].strip().lower())
                if not _text(s.get("does"), *LIMITS["does"]):
                    problems.append(f"{tag}: does must say in 10 to 240 characters what it actually does")
                asks = s.get("try_asking")
                if not isinstance(asks, list) or not 1 <= len(asks) <= 3 or not all(_text(a, *LIMITS["ask"]) for a in asks):
                    problems.append(f"{tag}: try_asking needs 1 to 3 example questions of 3 to 120 characters")
    for key, label in (("limits", "limit"), ("needs", "need")):
        v = manifest.get(key)
        if v is not None and (not isinstance(v, list) or len(v) > 5 or not all(isinstance(x, str) and 1 <= len(x) <= 140 for x in v)):
            problems.append(f"{key} must be a list of at most 5 short strings")
    if isinstance(manifest.get("result_schema"), dict):
        loose = unbounded(manifest["result_schema"])
        if loose:  # a listed helper may only say what fits in a stated amount of room
            problems.append("result_schema leaves room for unlimited text at: " + ", ".join(loose[:4]) + " (add maxLength / maxItems, and additionalProperties: false)")
    return problems


def profile_fields(manifest: dict) -> dict:
    """The parts of the manifest a listing keeps (already validated)."""
    return {
        "skills": [{"name": s["name"].strip(), "does": s["does"].strip(), "try_asking": [a.strip() for a in s["try_asking"]]}
                   for s in manifest["skills"]],
        "speciality": (manifest.get("speciality") or "").strip(),
        "needs": [str(n) for n in manifest.get("needs", [])],
        "limits": [str(x) for x in manifest.get("limits", [])],
    }
