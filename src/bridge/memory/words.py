"""Shared word handling: lower-case words without filler, reduced to a rough stem so 'prefer' finds 'prefers'."""
from __future__ import annotations

import re

STOPWORDS = frozenset("""a an and are as at be been but by can could did do does for from had has have how i if in into is it its
me my of on or our please should so tell that the their them then there these they this to up us was we were what when where which who
whom why will with would you your about any anything give show""".split())


def stem(w: str) -> str:
    """A rough stem. Two passes, so 'meetings' and 'meeting' both end up as 'meet' (plural first, then -ing/-ed)."""
    for _ in range(2):
        for suffix in ("ing", "ed", "es", "s"):
            if len(w) > len(suffix) + 2 and w.endswith(suffix):
                w = w[: -len(suffix)]
                break
        else:
            break
    return w


def surface(s: str) -> list[str]:
    """The words of a text as written (lower case, no filler), in order."""
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOPWORDS]


def tokens(s: str) -> set[str]:
    return {stem(w) for w in surface(s)}
