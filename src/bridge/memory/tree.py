"""A tree of shelves over the vault, so memory can be huge and still be searched by deciding, not by scanning.

Every record sits on a shelf ("work/clients"). A shelf knows how many files lie under it and which words those files
use most, like the index page of a small wiki. Looking for something means walking down from the root: at each level
only the shelves whose summary fits the question are opened, and the rest are never touched. The walk is recorded,
so a person can always see which shelves were opened for an answer.

The same tree is built twice with different contents: the whole vault for the person's own manager screen, and only the
closed set of shared files for a helper, so a helper's tree can never hint at what was not shared.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import log

from .vault import Record
from .words import stem, surface, tokens

BEAM = 3  # shelves opened per level while walking down
MAX_FRONTIER = 6  # and never more than this many open at once


def pretty(path: str) -> str:
    return " › ".join(p.title() for p in path.split("/")) if path else "Everything"


@dataclass
class Shelf:
    path: str
    own: list = field(default_factory=list)  # ids of the files lying directly on this shelf
    children: list = field(default_factory=list)  # paths of the shelves directly below
    count: int = 0  # files on this shelf and everything below it
    df: Counter = field(default_factory=Counter)  # word stem -> how many files below use it

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1] if self.path else ""


class MemoryTree:
    def __init__(self, records, labels: dict | None = None):
        self.labels = labels or {}
        self.records: dict[str, Record] = {}
        self.nodes: dict[str, Shelf] = {"": Shelf("")}
        self._tok: dict[str, set] = {}
        self._types: set = set()  # word stems of the kinds of file, which say nothing about a shelf's subject
        self._shown: dict[str, str] = {}  # stem -> a readable form of it, for the keyword lists
        for r in records:
            self.records[r.id] = r
            toks = set()
            for w in surface(r.text):
                st = stem(w)
                toks.add(st)
                self._shown.setdefault(st, w)
            toks |= tokens(r.type)
            self._types |= tokens(r.type)
            self._tok[r.id] = toks
            self._node(r.shelf).own.append(r.id)
        for path in sorted(self.nodes, key=lambda p: -(p.count("/") + 1) if p else 0):  # deepest first: children before parents
            node = self.nodes[path]
            node.children.sort()
            node.count = len(node.own) + sum(self.nodes[c].count for c in node.children)
            for rid in node.own:
                node.df.update(self._tok[rid])
            for c in node.children:
                node.df.update(self.nodes[c].df)

    def _node(self, path: str) -> Shelf:
        """The shelf at `path`, created together with every shelf above it."""
        if path in self.nodes:
            return self.nodes[path]
        parent = self._node(path.rsplit("/", 1)[0] if "/" in path else "")
        node = self.nodes[path] = Shelf(path)
        parent.children.append(path)
        return node

    # -- the index page of a shelf --------------------------------------------------------------
    def keywords(self, path: str, n: int = 6) -> list[str]:
        node = self.nodes.get(path)
        if node is None:
            return []
        name_stems = {stem(w) for w in surface(path.replace("/", " "))}
        ranked = sorted(((c, st) for st, c in node.df.items() if st not in name_stems and st not in self._types and len(st) > 2), key=lambda t: (-t[0], t[1]))
        return [self._shown.get(st, st) for _, st in ranked[:n]]

    def outline(self, path: str = "") -> list[dict]:
        """What lies directly below a shelf: one line per child shelf, then the files lying on this shelf itself."""
        node = self.nodes.get(path)
        if node is None:
            return []
        out = []
        for c in node.children:
            ch = self.nodes[c]
            out.append({"path": c, "name": ch.name.title(), "count": ch.count, "keywords": self.keywords(c),
                        "label": self.labels.get(c, ""), "has_children": bool(ch.children)})
        return out

    def shelves(self) -> list[str]:
        return sorted(p for p in self.nodes if p)

    # -- finding things by walking down ------------------------------------------------------------
    def _score(self, node: Shelf, q: set) -> float:
        s = sum(1 + log(1 + node.df[w]) for w in q if node.df.get(w))
        name = tokens(node.path.replace("/", " ") + " " + self.labels.get(node.path, ""))
        return s + 3 * len(q & name) if s or q & name else 0

    def route(self, query: str, limit: int = 5) -> tuple[list[Record], list[str]]:
        """Walk down from the root, opening only the shelves that fit the question.

        Returns the best files and the shelves that were opened on the way (the decision path)."""
        q = tokens(query)
        if not q:
            return [], []
        frontier, opened, found = [""], [], {}
        while frontier:
            nxt = []
            for path in frontier:
                node = self.nodes[path]
                opened.append(path)
                for rid in node.own:
                    hit = len(q & self._tok[rid])
                    if hit:
                        found[rid] = hit
                scored = sorted(((self._score(self.nodes[c], q), c) for c in node.children), key=lambda t: (-t[0], t[1]))
                nxt.extend(c for sc, c in scored[:BEAM] if sc > 0)
            frontier = nxt[:MAX_FRONTIER]
        best = sorted(found.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return [self.records[rid] for rid, _ in best], opened

    def newest(self, limit: int = 5) -> list[Record]:
        """For a vague question ('anything new?'): the most recently written files."""
        return sorted(self.records.values(), key=lambda r: (-(r.updated or r.created), r.id))[:limit]
