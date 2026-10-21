"""Capability set of a pack, and the rule that widening it needs a major version.

A requester approves a pack by what it can do: which tools, whether it reads memory, whether it
reaches the web or runs code, and how much it may spend. A new version that quietly gains any of
those would change what the requester approved, so the registry refuses it unless the major
version goes up. Changing prompt text alone never widens anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .workflow import Workflow


def capabilities(wf: Workflow) -> dict:
    steps = wf.steps.values()
    return {
        "tools": sorted({t for s in steps for t in s.tools}),
        "memory_lens": any(s.memory == "lens" for s in steps),
        "memory_types": sorted({s.type for s in steps if s.type}),
        "web": any(s.tool == "web_search" for s in steps),
        "code": any(s.kind == "code" for s in steps),
        "propose_memory": any(s.propose for s in steps),
        "budget_tokens": wf.budget.get("tokens"),
        "budget_usd": wf.budget.get("usd"),
    }


def widening(old: dict, new: dict) -> list[str]:
    """Reasons `new` can do more than `old` (empty list means it did not widen)."""
    out = []
    for t in sorted(set(new["tools"]) - set(old["tools"])):
        out.append(f"new tool {t}")
    for key in ("memory_lens", "web", "code", "propose_memory"):
        if new[key] and not old[key]:
            out.append(f"now uses {key}")
    for t in sorted(set(new["memory_types"]) - set(old["memory_types"])):
        out.append(f"now asks about record type {t}")
    for key in ("budget_tokens", "budget_usd"):
        o, n = old[key], new[key]
        if n is None and o is not None:
            out.append(f"{key} limit removed")
        elif n is not None and o is not None and n > o:
            out.append(f"{key} raised from {o} to {n}")
        elif n is not None and o is None:
            pass  # adding a limit only narrows what the pack may spend
    return out


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> "Version":
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(text))
        if not m:
            raise ValueError(f"version must look like 1.2.3, got {text!r}")
        return cls(*map(int, m.groups()))
