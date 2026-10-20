"""Tavily web search: the only network a pack can use, and only from a PUBLIC step.

The engine calls this on the requester's side with the requester's key. A pack never sees the key and
has no socket of its own. Results are trimmed (title, url, a short snippet) and are treated as data,
never as instructions. See the scope rules in pack/workflow.py and the query check in flowd.py.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Callable

URL = "https://api.tavily.com/search"
MAX_RESULTS = 3
SNIPPET = 300
MAX_QUERY = 200


class SearchError(Exception):
    pass


def load_tavily_key(env_file: Path | str = ".env") -> str:
    try:
        lines = Path(env_file).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise SearchError("no .env file with TAVILY_API_KEY") from e
    for line in lines:
        if line.startswith("TAVILY_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
    raise SearchError("TAVILY_API_KEY not set in .env")


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _clean(s: str, n: int) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


class TavilySearch:
    def __init__(self, api_key: str, *, post: Callable[..., dict] = _post):
        self._key, self._post = api_key, post

    def search(self, query: str) -> list[dict]:
        query = _clean(query, MAX_QUERY)
        if not query:
            raise SearchError("empty query")
        try:
            out = self._post(URL, {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
                             {"query": query, "max_results": MAX_RESULTS})
            raw = out["results"]
        except SearchError:
            raise
        except Exception as e:  # report the type only, never the key
            raise SearchError(f"web search failed: {type(e).__name__}") from e
        return [{"title": _clean(r.get("title"), 120), "url": _clean(r.get("url"), 200),
                 "snippet": _clean(r.get("content"), SNIPPET)} for r in raw[:MAX_RESULTS]]
