"""A small router: each address is declared once, with the method it answers, what it needs, and the function that serves it.
Handlers are plain functions of (request) that return something JSON-friendly, or a Reply for anything else.
Nothing here knows about sockets; `transport.py` does that."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Request:
    method: str
    path: str
    query: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    headers: Any = None
    params: dict = field(default_factory=dict)  # the :name parts of the address

    def arg(self, name: str, default: str = "") -> str:
        v = self.query.get(name, default)
        return v if isinstance(v, str) else default


@dataclass
class Reply:
    """An answer that is not plain JSON (a small page), or JSON with a status other than 200."""
    status: int = 200
    body: Any = None
    ctype: str = "application/json; charset=utf-8"


class HttpError(Exception):
    """Raised by a handler to answer with a particular status and message."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class Route:
    method: str
    pattern: str
    fn: Callable[[Request], Any]
    token: bool  # needs the page's own token (every POST does; a few private GETs do too)
    regex: re.Pattern


def _compile(pattern: str) -> re.Pattern:
    return re.compile("^" + re.sub(r":([a-z_]+)", r"(?P<\1>[^/]+)", re.escape(pattern).replace("\\:", ":")) + "$")


class Router:
    def __init__(self):
        self.routes: list[Route] = []

    def add(self, method: str, pattern: str, fn: Callable[[Request], Any], *, token: bool | None = None) -> None:
        method = method.upper()
        self.routes.append(Route(method, pattern, fn, method != "GET" if token is None else token, _compile(pattern)))

    def get(self, pattern: str, *, token: bool = False):
        def wrap(fn):
            self.add("GET", pattern, fn, token=token)
            return fn
        return wrap

    def post(self, pattern: str):
        def wrap(fn):
            self.add("POST", pattern, fn)
            return fn
        return wrap

    def find(self, method: str, path: str) -> tuple[Route, dict] | None:
        for r in self.routes:
            if r.method == method.upper():
                m = r.regex.match(path)
                if m:
                    return r, m.groupdict()
        return None

    def table(self) -> list[tuple[str, str]]:
        """Every address the API answers, for the docs and for tests."""
        return sorted((r.method, r.pattern) for r in self.routes)
