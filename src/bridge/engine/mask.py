"""Masker: hides contact details and long numbers from the model service, and puts them back in the answer.

Before a step's inputs go to the model, every email address, phone number and long account-style number is swapped for a
placeholder such as [EMAIL_1]. The same value always gets the same placeholder during one run. When the reply comes
back, placeholders are swapped for the real values, on the requester's machine, so the answer still shows the real
contact. The model service therefore never reads those values.

Names, places and company facts are NOT hidden: the model needs them to understand the question. This lowers what the
service sees; it does not make the service blind.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

PATTERNS = (
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    ("PHONE", re.compile(r"(?<![\w+])(?:\+\d{1,3}[ .-]?)?(?:\(\d{3}\)\s?|\d{3}[ .-])\d{3}[ .-]\d{4}(?!\w)|(?<![\w+])\+\d[\d ()-]{8,}\d(?!\w)")),
    ("NUMBER", re.compile(r"(?<![\w.])\d{9,}(?![\w])")),
)
_BACK = re.compile(r"\[?\b(EMAIL|PHONE|NUMBER)[_ ](\d+)\b\]?")


class Masker:
    def __init__(self):
        self._token: dict[str, str] = {}   # real value -> placeholder
        self._real: dict[str, str] = {}    # placeholder -> real value
        self._n: Counter = Counter()
        self.last: Counter = Counter()     # what the latest mask() call hid, by kind

    def mask(self, value: Any) -> Any:
        self.last = Counter()
        return self._mask(value)

    def _mask(self, v: Any) -> Any:
        if isinstance(v, str):
            return self._text(v)
        if isinstance(v, list):
            return [self._mask(x) for x in v]
        if isinstance(v, dict):
            return {k: (x if k == "id" else self._mask(x)) for k, x in v.items()}  # record ids are not private and must stay usable
        return v

    def _text(self, s: str) -> str:
        for kind, pat in PATTERNS:
            s = pat.sub(lambda m, kind=kind: self._swap(kind, m.group(0)), s)
        return s

    def _swap(self, kind: str, real: str) -> str:
        tok = self._token.get(real)
        if tok is None:
            self._n[kind] += 1
            tok = f"[{kind}_{self._n[kind]}]"
            self._token[real], self._real[tok] = tok, real
        self.last[kind] += 1
        return tok

    def unmask(self, value: Any) -> Any:
        if not self._real:
            return value
        if isinstance(value, str):
            return _BACK.sub(lambda m: self._real.get(f"[{m.group(1)}_{m.group(2)}]", m.group(0)), value)
        if isinstance(value, list):
            return [self.unmask(x) for x in value]
        if isinstance(value, dict):
            return {k: self.unmask(x) for k, x in value.items()}
        return value
