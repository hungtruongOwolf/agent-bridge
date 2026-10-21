"""Result Guard: the last check before a pack's output reaches the requester.

The output channel of a foreign pack is the one exit we cannot close, so we bound it:
a declared schema, a size cap, and a scan for canary values and for long verbatim copies
of the records the pack was allowed to read (a sign it is dumping memory, not answering).

Verdicts:
  ALLOW  deliver the result
  DENY   the result is dropped (schema/size/overlap problem); the run is not an incident
  KILL   a canary value appears in the output: deterministic evidence of theft
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from jsonschema import Draft202012Validator

from ..memory.broker import Verdict


@dataclass
class GuardReport:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    evidence: str | None = None


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (_strings(k) + _strings(v))]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def longest_shared_run(haystack: str, needle: str, cap: int = 200) -> int:
    """Length of the longest substring of `needle` found verbatim in `haystack` (normalised)."""
    h, n = _norm(haystack), _norm(needle)
    best = 0
    for i in range(len(n)):
        lo = best + 1
        while lo <= min(cap, len(n) - i) and n[i : i + lo] in h:
            best = lo
            lo += 1
    return best


def unbounded(schema: dict, path: str = "result") -> list[str]:
    """Places in an output schema where the answer could be any length: a string with no maxLength, a list with no
    maxItems, or an object that allows extra fields. Free room in the answer is room to carry something out."""
    out: list[str] = []
    kind = schema.get("type")
    if kind == "string" and "maxLength" not in schema and "enum" not in schema and "const" not in schema:
        out.append(path)
    elif kind == "array":
        if "maxItems" not in schema:
            out.append(path + "[]")
        out += unbounded(schema.get("items") or {}, path + "[]")
    elif kind == "object":
        if schema.get("additionalProperties") not in (False, None) or "additionalProperties" not in schema:
            out.append(path + " (extra fields allowed)")
        for k, v in (schema.get("properties") or {}).items():
            out += unbounded(v, f"{path}.{k}")
    elif kind is None and not any(k in schema for k in ("enum", "const")):
        out.append(path + " (no type)")
    return out


class ResultGuard:
    def __init__(self, schema: dict, *, max_bytes: int = 8192, max_overlap: int = 60):
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(schema)
        self._max_bytes = max_bytes
        self._max_overlap = max_overlap

    def scan(self, result, *, canaries: list[str], lens_texts: list[str]) -> GuardReport:
        """Canary and verbatim-copy checks only (used for the result and for memory proposals)."""
        blob = _norm(json.dumps(result, ensure_ascii=False, sort_keys=True))
        for c in canaries:
            if c and _norm(c) in blob:
                return GuardReport(Verdict.KILL, ["canary value in output"], evidence="canary")
        for s in _strings(result):
            for src in lens_texts:
                run = longest_shared_run(s, src)
                if run > self._max_overlap:
                    return GuardReport(Verdict.DENY, [f"{run} characters copied verbatim from a record"])
        return GuardReport(Verdict.ALLOW)

    def check(self, result, *, canaries: list[str], lens_texts: list[str]) -> GuardReport:
        text = json.dumps(result, ensure_ascii=False, sort_keys=True)
        canary = self.scan(result, canaries=canaries, lens_texts=[])  # canary first, whatever else is wrong
        if canary.verdict is Verdict.KILL:
            return canary
        if len(text.encode()) > self._max_bytes:
            return GuardReport(Verdict.DENY, [f"result larger than {self._max_bytes} bytes"])
        errs = list(self._validator.iter_errors(result))
        if errs:  # name the field and the rule only: an error message would repeat the offending value (your data)
            return GuardReport(Verdict.DENY, ["schema: " + (".".join(map(str, e.path)) or "result") + " breaks " + str(e.validator)
                                              for e in errs[:3]])
        return self.scan(result, canaries=[], lens_texts=lens_texts)
