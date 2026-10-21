"""A profile page for one helper: what it says it can do, what it will touch, and what was actually measured.

Two kinds of statements are kept apart on purpose:
  author says   the skills, example questions and limits written in the pack's manifest (a claim)
  measured      what the Certifier saw when it asked the pack real questions (evidence), per skill
The "what it can touch" lines are not claims at all: they are read from the pack's own program, so they cannot be
left out or invented by the author.
"""
from __future__ import annotations

from .certifier import Attestation
from .registry import PackRecord

ALWAYS_CANNOT = [
    "Send your files to anyone.",
    "Change, move or delete your files.",
    "See files you keep locked or did not choose to share.",
]


def _works_with(rec: PackRecord) -> list[dict]:
    c = rec.caps or {}
    out = []
    if c.get("memory_lens"):
        kinds = ", ".join(rec.needs) if rec.needs else "any kind"
        out.append({"kind": "files", "text": f"Reads the files you choose to share ({kinds}). It cannot see the rest."})
    if c.get("web"):
        out.append({"kind": "web", "text": "Looks things up on the public web. Your files are never sent there"
                    + ("; the words of your question may be." if c.get("web_uses_task") else ", and neither is your question.")})
    if c.get("code"):
        out.append({"kind": "program", "text": "Runs its own small program inside a sealed glass room with no internet."})
    if c.get("propose_memory"):
        out.append({"kind": "memory", "text": "May suggest things for you to remember. Nothing is saved unless you say yes."})
    out.append({"kind": "thinking", "text": "Thinks with the Nemotron model on Nebius, through your own assistant. The text it reads goes to that service. The helper never holds your keys."})
    return out


def _cannot(rec: PackRecord) -> list[str]:
    c = rec.caps or {}
    out = list(ALWAYS_CANNOT)
    if not c.get("web"):
        out.append("Use the internet.")
    if not c.get("code"):
        out.append("Run its own programs.")
    return out


def _measured(att: Attestation | None, status: str, violations: list[str]) -> dict:
    if att is None:
        return {"status": status, "tested": False, "note": "Nobody has tested this helper yet, so it is not ranked."}
    out = {"status": status, "tested": True, "suite": f"{att.suite} v{att.suite_version}", "model": att.model,
           "passes": att.passes, "total": att.total, "infra_failures": att.infra_failures}
    if att.security == "clean":
        out["score"] = round(att.score * 100)
        out["by_skill"] = [{"what": (t.get("goal") or name).capitalize(), "ask": t.get("ask", ""), "passes": t["passes"], "total": t["total"]}
                           for name, t in att.by_task.items()]
    else:
        out["violations"] = violations
    return out


def build(rec: PackRecord, *, attestation: Attestation | None, status: str, versions: list[dict], price_cents: int,
          unit: str, stars: int, price_text: str = "", metered: bool = False, plan: str = "flat") -> dict:
    return {
        "key": rec.key, "id": rec.id, "version": rec.version, "summary": rec.summary, "speciality": rec.speciality,
        "price_cents": price_cents, "price_text": price_text or f"{price_cents}¢ each", "metered": metered, "plan": plan, "unit": unit, "stars": stars,
        "author_says": {"skills": rec.skills, "good_to_know": rec.limits},
        "works_with": _works_with(rec), "cannot": _cannot(rec),
        "measured": _measured(attestation, status, list(attestation.violations) if attestation else []),
        "versions": versions,
    }
