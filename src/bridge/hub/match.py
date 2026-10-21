"""Find the helper whose own words about its skills fit what a person asks for.

Nothing here knows about any particular subject: it compares the words of the question with the words each author wrote
for their skills (name, what it does, example questions) and with the helper's summary and speciality. Skills count
more than the summary, example questions count most (they are what the helper was shown to answer). Measured trust only
breaks near-ties, so a helper cannot buy a place with a good score on something unrelated.
"""
from __future__ import annotations

import math

from ..memory.broker import tokens

WEIGHTS = {"name": 3.0, "example": 3.0, "does": 2.0, "about": 1.0}


def _fit(query: set[str], rec) -> tuple[float, dict]:
    parts = [("about", f"{rec.summary} {rec.speciality or ''}")]
    for s in rec.skills:
        parts.append(("name", s["name"]))
        parts.append(("does", s["does"]))
        parts += [("example", q) for q in s.get("try_asking", [])]
    score, best = 0.0, {"skill": None, "example": None, "hit": 0.0}
    for kind, text in parts:
        hit = len(query & tokens(text))
        if not hit:
            continue
        score += WEIGHTS[kind] * hit
    for s in rec.skills:  # which skill explains the match best
        words = tokens(s["name"] + " " + s["does"]) | {w for q in s.get("try_asking", []) for w in tokens(q)}
        hit = len(query & words)
        if hit > best["hit"]:
            ex = max(s.get("try_asking", [""]), key=lambda q: len(query & tokens(q)), default=None)
            best = {"skill": s["name"], "example": ex, "hit": hit}
    return score, best


def rank(question: str, candidates: list[tuple], limit: int = 3) -> list[dict]:
    """candidates: (record, trust 0..1 or None). Returns the best few with a plain reason each."""
    query = tokens(question)
    rows = []
    for rec, trust in candidates:
        score, best = _fit(query, rec)
        norm = score / math.sqrt(max(1, len(query)))
        rows.append({"rec": rec, "fit": norm, "trust": trust or 0.0, "best": best})
    rows.sort(key=lambda r: (-round(r["fit"], 1), -r["trust"], r["rec"].listing.price_usd, r["rec"].key))
    out = []
    for r in rows[:limit]:
        rec, best = r["rec"], r["best"]
        if r["fit"] > 0 and best["skill"]:
            reason = f"Good at “{best['skill']}”."
        elif r["fit"] > 0:
            reason = "Its description fits what you asked."
        else:
            reason = "Nothing it says matches closely, but it is well tested."
        out.append({"key": rec.key, "id": rec.id, "price_cents": max(1, round(rec.listing.price_usd * 100)), "price_text": rec.listing.text(),
                    "fit": round(r["fit"], 2), "matched": r["fit"] > 0, "reason": reason,
                    "example": best["example"] if r["fit"] > 0 else None,
                    "trust": round(r["trust"] * 100) if r["trust"] else None})
    return out
