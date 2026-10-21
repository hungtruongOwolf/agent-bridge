"""Plain-language wording shared by the server and the page, so no technical term reaches a person."""

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
