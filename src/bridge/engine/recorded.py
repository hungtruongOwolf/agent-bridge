"""The recorded model: answers helper steps from templates, with no model service and no key.

Used by judge mode so anyone can run the whole application without keys. It reads the notes the helper was handed
(the `read` input) and writes a short answer in its own words from a fixed list of phrases, so the Result Guard
sees a paraphrase, never a copy. It is NOT a language model and says so wherever it matters (`provider`).

It knows three kinds of step, told apart by what the step asks for:
  proposals      "reply as JSON {"proposals": ...}"  -> one short thing worth remembering, taken from the analysis
  action_items   meeting-notes helpers               -> who owns what, from lines such as "Sam owns the questionnaire"
  anything else  summary and risk                    -> the accounts that matter, with the reasons it can recognise
A step that tells the model to copy everything word for word gets exactly that, which is how the guard is shown to work.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .flowd import ModelReply

PROVIDER = "the recorded model (no model service)"

# (pattern, phrase, weight): weight above zero means trouble, below zero means good news
RULES = (
    (r"security questionnaire", "wants a security questionnaire done before it renews", 1),
    (r"(one|single) invoice", "asked for a single invoice across its subsidiaries", 0),
    (r"tickets? (dropped|fell)|dropped by half|drop(ped)? by half", "has far fewer support tickets since the onboarding fix, which helps the renewal", -1),
    (r"budgets? (were |was |is |are )?cut|cut this quarter", "had its renewal budget cut", 2),
    (r"price hold", "asked for a price hold", 0),
    (r"at risk", "is flagged as at risk", 2),
    (r"\bred\b", "is rated red on the scorecard", 2),
    (r"amber", "is rated amber on the scorecard", 1),
    (r"delay|slip|postpone", "may see its renewal slip", 1),
    (r"competitor|switch(ing)? to", "is looking at a competitor", 2),
    (r"churn|cancel|leave|walk away", "may leave", 2),
    (r"discount", "is pushing for a discount", 1),
    (r"escalat|complain|unhappy|angry", "has raised complaints", 2),
    (r"upsell|expand|expansion|new seats", "may buy more", -1),
    (r"signed|renewed|green", "looks healthy", -1),
)
RISK_WORDS = re.compile(r"risk|worr|attention|churn|danger|trouble|leave|problem|renew|first|urgent|concern", re.I)
NOT_NAMES = {"the", "a", "an", "we", "i", "our", "my", "sales", "accounts", "account", "meeting", "meetings", "notes", "note", "revenue", "due",
             "planning", "friday", "monday", "tuesday", "wednesday", "thursday", "saturday", "sunday", "january", "february", "march", "april",
             "may", "june", "july", "august", "september", "october", "november", "december", "pitch", "pipeline", "end", "next", "this", "that",
             "they", "their", "it", "his", "her", "he", "she", "sam", "bill", "contact", "email", "phone", "call", "ask", "follow", "send",
             "support", "security", "price", "renewal", "todo", "action", "actions", "weekly", "quarter", "q1", "q2", "q3", "q4", "new", "old"}
MONEY = re.compile(r"\$?\s?(\d+(?:\.\d+)?)\s?([kKmM])\b")


def _texts(value: Any) -> list[str]:
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return [value["text"]]
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


def _names(text: str) -> list[str]:
    return [w for w in re.findall(r"\b[A-Z][a-z]{2,}(?: Corp)?\b", text) if w.split()[0].lower() not in NOT_NAMES]


def _score(text: str, task: str) -> int:
    words = {w for w in re.findall(r"[a-z]{4,}", task.lower())}
    return sum(1 for w in words if w in text.lower())


def _facts(text: str) -> list[tuple[str, int]]:
    return [(phrase, w) for pat, phrase, w in RULES if re.search(pat, text, re.I)]


def _first_words(text: str, n: int = 6) -> str:
    return " ".join(text.split()[:n]).rstrip(".,;:").lower()


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


class RecordedModel:
    """Deterministic: the same notes and question always give the same answer."""

    provider = PROVIDER
    model = "recorded"

    def complete(self, prompt: str, inputs: dict[str, Any]) -> ModelReply:
        out = self._answer(prompt, inputs)
        return ModelReply(out, tokens=max(40, len(json.dumps(out)) // 3))

    # -- steps -------------------------------------------------------------------------------
    def _answer(self, prompt: str, inputs: dict[str, Any]) -> dict:
        low = prompt.lower()
        if "word for word" in low:  # a helper that tells its model to copy: it does, and the guard stops it
            return {"summary": json.dumps(inputs, ensure_ascii=False)[:2000], "risk": "high"}
        if "proposals" in low:
            return {"proposals": [{"type": "note", "text": self._remember(inputs)}]}
        task = str(inputs.get("task", ""))
        notes = _texts(inputs.get("read"))
        if "action_items" in low:
            return self._actions(notes)
        return self._brief(task, notes)

    def _remember(self, inputs: dict[str, Any]) -> str:
        analysis = inputs.get("analyze")
        text = str(analysis.get("summary", "")) if isinstance(analysis, dict) else ""
        first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0] if text.strip() else "Worth a second look at the accounts in this answer."
        first = re.sub(r"https?://\S+", "", first).strip()
        return first[:118].rstrip(" ,;") + ("." if not first[:118].endswith((".", "!", "?")) else "")

    def _brief(self, task: str, notes: list[str]) -> dict:
        risky = bool(RISK_WORDS.search(task))
        if not notes:
            return {"summary": "I could not find anything about that in the files you shared. Open a shelf that covers it and ask again.", "risk": "n/a"}
        if re.search(r"biggest|largest|most valuable|top account", task, re.I):
            best = None
            for t in notes:
                for num, unit in MONEY.findall(t):
                    v = float(num) * (1000 if unit.lower() == "k" else 1_000_000)
                    names = _names(t)
                    if names and (best is None or v > best[0]):
                        best = (v, names[0], f"{num}{unit.lower()}")
            if best:
                return {"summary": f"The biggest looks like {best[1]}, with about {best[2]} in play according to your notes.", "risk": "n/a"}
            return {"summary": "Your notes do not give amounts, so I cannot say which one is biggest.", "risk": "n/a"}
        ranked = sorted(notes, key=lambda t: -_score(t, task))
        by_name: dict[str, list[tuple[str, int]]] = {}
        order: list[str] = []
        for t in ranked[:6]:
            names = _names(t)
            who = names[0] if names else None
            facts = _facts(t)
            if who is None:
                continue
            if who not in by_name:
                by_name[who] = []
                order.append(who)
            for f in facts:
                if f not in by_name[who]:
                    by_name[who].append(f)
            if not facts and not by_name[who]:
                by_name[who].append((f"has a note that starts \"{_first_words(t.split(who, 1)[-1], 5)}\"", 0))
        sentences, total = [], 0
        for who in order[:3]:
            facts = sorted(by_name[who], key=lambda f: -abs(f[1]))[:3]
            if not facts:
                continue
            total += sum(w for _, w in facts)
            sentences.append(f"{who} {_join([p for p, _ in facts])}.")
        if not sentences:
            sentences = [f"Your notes mention {_first_words(notes[0], 8)}, but nothing in them points to a clear risk."]
        text = " ".join(sentences)[:590]
        if not risky:
            return {"summary": text, "risk": "n/a"}
        return {"summary": text, "risk": "high" if total >= 4 else ("medium" if total >= 1 else "low")}

    def _actions(self, notes: list[str]) -> dict:
        items: list[str] = []
        for t in notes:
            for who, what in re.findall(r"\b([A-Z][a-z]+) (?:owns|will|is going to|has to) ([^.]{4,80})", t):
                item = f"{who}: {what.strip()}"[:50].rstrip(" ,;")
                if item not in items:
                    items.append(item)
        items = items[:6]
        summary = f"{len(items)} action{'s' if len(items) != 1 else ''} found in the notes." if items else "No clear actions in these notes."
        return {"summary": summary, "action_items": items}
