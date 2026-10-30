"""Channel3 product search (https://www.trychannel3.com): real product data for the Deal Finder helper.

Like Tavily this is public network access on the requester's side with the requester's key. A pack never sees the key
and has no socket. Only a PUBLIC step may use it (see the scope rules in pack/workflow.py). Results are trimmed and are
data for the model, never instructions.

What the official docs confirm (channel3.ai/docs, read 2026-10-30):
  - POST https://api.trychannel3.com/v1/search, header `x-api-key`, JSON body {query, limit (default 20, max 30), filters}
  - response {products: [...], next_page_token}; a product has `title`, `brands[{id,name}]`, `offers[]`; each offer has
    `url`, `domain`, `price{price, compare_at_price, currency}`, `availability` (InStock | OutOfStock), `condition`
  - filters default to new items that are in stock; 401 = missing/invalid key, 402 = free credits used up
  - 1,000 free credits a month, one search = one credit, extra credits $0.007 each (docs pricing page)
NOT confirmed by the docs (treated carefully below): the body of a 429 response, and where exactly the owner creates a key
(the docs pages read do not say). Nothing here has been run against the live service: tests use fake HTTP.

`RecordedProducts` is a small fixed catalog, labelled "Recorded product data" in every result. It lets seeding, the
Certifier and offline demos work without a key; it must never be passed off as live data.
"""
from __future__ import annotations

import json
import os
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .tavily import SearchError

URL = "https://api.trychannel3.com/v1/search"
LIVE_LABEL = "Channel3"
RECORDED_LABEL = "Recorded product data"
LIMIT = 10  # products asked for (the docs allow up to 30)
MAX_PRODUCTS = 10
MAX_QUERY = 200
MAX_RESPONSE_BYTES = 2_000_000
TIMEOUT = 20


class Channel3Error(SearchError):
    """Carries a plain sentence that is safe to show to the person."""


def load_channel3_key(env_file: Path | str = ".env") -> str:
    key = os.environ.get("CHANNEL3_API_KEY", "").strip()
    if key:
        return key
    try:
        lines = Path(env_file).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise Channel3Error("CHANNEL3_API_KEY is not set") from e
    for line in lines:
        if line.startswith("CHANNEL3_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
    raise Channel3Error("CHANNEL3_API_KEY is not set")


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise Channel3Error("Channel3 sent back more data than this helper accepts")
    return json.loads(raw)


def _clean(s, n: int) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def _explain(e: Exception) -> str:
    """A plain sentence for what went wrong. Never includes the key or the raw server text."""
    if isinstance(e, Channel3Error):
        return str(e)
    code = getattr(e, "code", None)
    if isinstance(e, (socket.timeout, TimeoutError)) or isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
        return "Channel3 took too long to answer"
    if code in (401, 403):
        return "Channel3 did not accept the key (check CHANNEL3_API_KEY)"
    if code == 402:
        return "the free Channel3 searches for this month are used up"
    if code == 429:
        return "Channel3 says there have been too many searches; try again in a minute"
    if code is not None:
        return f"Channel3 had a problem (HTTP {int(code)})"
    if isinstance(e, urllib.error.URLError):
        return "Channel3 could not be reached"
    if isinstance(e, ValueError):
        return "Channel3 sent back something that was not readable"
    return f"the product search failed ({type(e).__name__})"


def _normalize(p: dict, source: str) -> dict | None:
    """One product with its best offer: the cheapest one that is in stock, else the first one."""
    offers = [o for o in (p.get("offers") or []) if isinstance(o, dict)]
    if not offers:
        return None

    def price_of(o):
        pr = o.get("price")
        v = pr.get("price") if isinstance(pr, dict) else None
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else float("inf")

    in_stock = [o for o in offers if o.get("availability") == "InStock"]
    best = min(in_stock or offers, key=price_of) if (in_stock or offers) else None
    pr = best.get("price") if isinstance(best.get("price"), dict) else {}
    price = pr.get("price")
    brands = p.get("brands") or []
    brand = brands[0].get("name") if brands and isinstance(brands[0], dict) else ""
    return {"title": _clean(p.get("title"), 120), "brand": _clean(brand, 60),
            "price": round(float(price), 2) if isinstance(price, (int, float)) and not isinstance(price, bool) else None,
            "currency": _clean(pr.get("currency"), 8), "availability": _clean(best.get("availability"), 20),
            "merchant": _clean(best.get("domain"), 80), "url": _clean(best.get("url"), 300), "source": source}


class Channel3Search:
    def __init__(self, api_key: str, *, post: Callable[..., dict] = _post, get: Callable[..., dict] | None = None):
        # `get` is accepted so a caller can inject both; the search endpoint is a POST and nothing here uses it.
        self._key, self._post, self._get = api_key, post, get

    def search(self, query: str) -> list[dict]:
        query = _clean(query, MAX_QUERY)
        if not query:
            raise Channel3Error("there was nothing to search for")
        try:
            out = self._post(URL, {"x-api-key": self._key, "Content-Type": "application/json"}, {"query": query, "limit": LIMIT})
            raw = out["products"]
            if not isinstance(raw, list):
                raise ValueError("products is not a list")
        except Exception as e:  # report a plain sentence only, never the key
            raise Channel3Error(_explain(e)) from e
        found = [n for n in (_normalize(p, LIVE_LABEL) for p in raw[:MAX_PRODUCTS * 3] if isinstance(p, dict)) if n]
        return found[:MAX_PRODUCTS]


# -- recorded product data (offline) ----------------------------------------------------------------------
# Made-up listings on `.example` domains (reserved, never real shops). Prices are illustrative, not a quote.
_CATALOG = [
    ("Trailhead 28L Daypack", "Northpeak", 59.0, "backpack hiking daypack bag", "northpeak-shop.example"),
    ("Summit Lite 35L Pack", "Northpeak", 94.5, "backpack hiking pack bag travel", "northpeak-shop.example"),
    ("City Commuter Backpack", "Urbanloop", 74.0, "backpack laptop commute bag school", "urbanloop.example"),
    ("Everyday Canvas Backpack", "Fieldwork", 39.9, "backpack canvas school bag cheap", "fieldwork-goods.example"),
    ("ANC Wireless Headphones X2", "Sonaris", 129.0, "headphones wireless noise cancelling bluetooth audio", "sonaris-audio.example"),
    ("Studio Over-Ear Headphones", "Sonaris", 79.0, "headphones wired over-ear audio music", "sonaris-audio.example"),
    ("PocketBuds Earbuds", "Tonehill", 34.0, "earbuds wireless bluetooth audio cheap", "tonehill-store.example"),
    ("Run 5 Running Shoes", "Stridewell", 88.0, "running shoes sneakers trainers", "stridewell.example"),
    ("TrailGrip Trail Shoes", "Stridewell", 112.0, "trail running shoes hiking sneakers", "stridewell.example"),
    ("Barista Pour-Over Kettle", "Kettlecraft", 46.0, "kettle coffee pour over gooseneck kitchen", "kettlecraft.example"),
    ("Burr Coffee Grinder Mini", "Kettlecraft", 52.0, "coffee grinder burr kitchen", "kettlecraft.example"),
    ("Desk Lamp Aura", "Lumio", 29.0, "desk lamp light led office", "lumio-home.example"),
    ("Ergo Office Chair", "Sitwell", 189.0, "office chair desk ergonomic furniture", "sitwell.example"),
    ("Standing Desk Mat", "Sitwell", 36.0, "desk mat standing office comfort", "sitwell.example"),
]
_STOP = {"a", "an", "the", "for", "to", "me", "i", "want", "need", "buy", "find", "under", "below", "less", "than", "my",
         "budget", "of", "and", "or", "with", "good", "best", "some", "usd", "dollars", "around", "about", "please", "get"}


class RecordedProducts:
    """Fixed sample catalog with the same shape as Channel3Search results. Always labelled as recorded."""

    label = RECORDED_LABEL

    def __init__(self):
        self.queries: list[str] = []

    def search(self, query: str) -> list[dict]:
        query = _clean(query, MAX_QUERY)
        self.queries.append(query)
        if not query:
            raise Channel3Error("there was nothing to search for")
        words = {w for w in re.findall(r"[a-z]+", query.lower()) if w not in _STOP and len(w) > 2}
        words |= {w[:-1] for w in words if w.endswith("s") and len(w) > 3}  # crude plural fold: "shoes" also finds "shoe"
        scored = []
        for title, brand, price, tags, domain in _CATALOG:
            hay = set(tags.split()) | set(re.findall(r"[a-z]+", title.lower()))
            hit = len(words & hay)
            if hit:
                scored.append((-hit, price, title, brand, domain))
        scored.sort()
        return [{"title": t, "brand": b, "price": p, "currency": "USD", "availability": "InStock", "merchant": d,
                 "url": f"https://{d}/{re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')}", "source": RECORDED_LABEL}
                for _, p, t, b, d in scored[:MAX_PRODUCTS]]


def product_source(env_file: Path | str = ".env"):
    """The live client when a key exists, otherwise the clearly labelled recorded catalog."""
    try:
        return Channel3Search(load_channel3_key(env_file))
    except SearchError:
        return RecordedProducts()


class WebTools:
    """One object for the engine's `web` slot: Tavily-style `search` plus `product_search`. Either part may be missing."""

    def __init__(self, search=None, products=None):
        self._search, self._products = search, products

    def search(self, query):
        if self._search is None:
            raise Channel3Error("no web search is configured")
        return self._search.search(query)

    def product_search(self, query):
        if self._products is None:
            raise Channel3Error("no product source is configured")
        return self._products.search(query)
