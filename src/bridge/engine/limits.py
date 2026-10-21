"""Size limits for what a person types and what a conversation carries into a run."""
MAX_TASK_CHARS = 1000          # one message from the user
MAX_HISTORY_TURNS = 10         # past messages (user and helper) a run may be given
MAX_HISTORY_TEXT = 600         # characters kept per past message


def clean_history(history) -> list[dict]:
    """Keep the last turns only, as plain {role, text}, each cut to a safe length."""
    out = []
    for h in (history or [])[-MAX_HISTORY_TURNS:]:
        if isinstance(h, dict) and h.get("role") in ("user", "helper") and isinstance(h.get("text"), str):
            out.append({"role": h["role"], "text": h["text"][:MAX_HISTORY_TEXT]})
    return out
