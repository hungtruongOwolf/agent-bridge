"""Small stand-ins for the model and the web search: built on first use, so a helper that never needs them never needs their keys."""
from __future__ import annotations

import json

from ...engine.flowd import ModelReply


class LeakyModel:
    """Simulates a compromised model step that copies everything it can see."""

    def complete(self, prompt, inputs):
        return ModelReply({"summary": json.dumps(inputs, ensure_ascii=False), "risk": "high"}, tokens=100)


class LazyModel:
    """Builds the real model client on first use, so a pack with no model step never needs a key."""

    def __init__(self, factory):
        self._factory, self._model = factory, None

    def complete(self, prompt, inputs):
        if self._model is None:
            self._model = self._factory()
        return self._model.complete(prompt, inputs)

    @property
    def provider(self):
        return getattr(self._model, "provider", "the thinking service")


class LazySearch:
    """Builds the Tavily client on first use, so packs that never search need no Tavily key."""

    def __init__(self, factory):
        self._factory, self._client = factory, None

    def search(self, query):
        if self._client is None:
            self._client = self._factory()
        return self._client.search(query)

    def product_search(self, query):
        """Channel3 products when CHANNEL3_API_KEY is set, otherwise the labelled recorded catalog (built on first use)."""
        if getattr(self, "_products", None) is None:
            from ...engine.channel3 import product_source
            self._products = product_source()
        return self._products.search(query)
