"""Plain-language wording shared by the server and the page, so no technical term reaches a person."""

from ..memory.tree import pretty

BLOCKED = {
    "OFF_LENS_QUERY": "asked for files you keep locked",
    "UNKNOWN_ID": "tried to open a file it was never given",
    "CANARY_HIT": "grabbed a decoy file that only a snoop would touch",
    "READ_BUDGET": "asked for more files than it is allowed",
    "SANDBOX_NETWORK": "tried to send a message out of its sealed room",
    "SANDBOX_PROCESS": "tried to start another program",
    "SANDBOX_WRITE": "tried to write outside its own notebook",
    "WEB_QUERY_LEAK": "tried to put your files into a web search",
}


def blocked_phrase(kinds) -> str:
    seen, out = set(), []
    for k in kinds:
        p = BLOCKED.get(k)
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return " and ".join(out) if out else "did something it should not"


def stopped_message(helper: str, kinds) -> str:
    return (f"The guard stopped {helper}: it {blocked_phrase(kinds)}. Nothing was delivered and your files were not exposed. "
            "You were not charged for this answer.")


def failure_message(outcome: str, reason: str = "") -> str:
    if outcome == "FAILED_INFRA":
        return "The thinking service did not answer this time, so there is no answer. You were not charged. Try again in a moment."
    if outcome == "PARTIAL_BUDGET":
        return "The helper ran out of its working budget before it could finish. You were not charged for this answer."
    return "The helper could not give an answer I can trust, so I am not passing it on. You were not charged for this answer."


def answer_text(result: dict) -> str:
    """Turn any helper's structured answer into readable text: the summary first, then every other field with a plain label.
    'risk' is shown separately as a tag, so it is left out here."""
    if not isinstance(result, dict):
        return str(result)
    lines = [str(result.get("summary", "")).strip()]
    for key, val in result.items():
        if key in ("summary", "risk") or val in (None, "", []):
            continue
        label = key.replace("_", " ").capitalize()
        if isinstance(val, list):
            lines.append(label + ":" + chr(10) + chr(10).join("• " + str(x) for x in val))
        else:
            lines.append(f"{label}: {val}")
    return (chr(10) * 2).join(x for x in lines if x)


def how_made(steps: list[dict], vault_texts: dict[str, str] | None = None) -> list[str]:
    """What happened during one answer, in plain sentences, from the run's own record (never from the helper's claims)."""
    out: list[str] = []
    kind_of: dict[str, str] = {}
    for e in steps:
        ev, sid = e.get("event"), e.get("step", "")
        if ev == "step_started":
            kind_of[sid] = e.get("kind", "")
        elif ev == "step_committed" and "records" in e:
            n = len(e["records"])
            shelves = " and ".join(pretty(p) for p in e.get("shelves", [])[:3])
            out.append((f"Looked through the files you share and read {n} of them, from " + shelves + "." if shelves else f"Looked through the files you share and read {n} of them.")
                       if n else "Looked through the files you share and found nothing that matches.")
            if e.get("blocked"):
                out.append("It also " + blocked_phrase(e["blocked"]) + ", which the guard refused.")
        elif ev == "model_call":
            n, to = len(e.get("sent_records") or []), e.get("sent_to") or "the thinking service"
            out.append(f"Sent {n} of your files to {to} to write the answer." if n else f"Asked {to} to write or check something; none of your files went with it."
                       if "sent_records" in e else "Asked the thinking service to write or check something.")
        elif ev == "web_search":
            out.append(f"Looked something up on the public web (“{e.get('query', '')}”). Your files were not part of that search.")
        elif ev == "cell_run":
            out.append("Ran its own small program in a sealed room with no internet." + (" It ran too long and was stopped." if e.get("timed_out") else ""))
        elif ev == "step_committed" and kind_of.get(sid) == "gate":
            out.append("Checked its own answer: " + ("it passed." if e.get("passed") else "it did not pass."))
        elif ev == "incident":
            out.append("The guard raised an alarm.")
    out.append("The guard checked the final answer before it reached you.")
    return out
