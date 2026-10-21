"""Conversations with a hired helper.

A thread is one continuous chat with one helper. It owns the settings that decide what that helper can see:
which file types and which single files are shared, how private is too private, how many earlier messages the
helper is shown, and how much the chat may spend. Messages record which files each answer used, so you can always
see where an answer came from. The store keeps everything in one JSON file, written atomically.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..engine.limits import MAX_HISTORY_TURNS, MAX_TASK_CHARS
from ..memory.vault import SENSITIVITY, TYPE_RE

MAX_THREADS = 200
MAX_MESSAGES = 400
MAX_BUDGET_CENTS = 10_000
DEFAULT_BUDGET_CENTS = 200
DEFAULT_HISTORY_TURNS = 4
MAX_TITLE = 60


class ThreadError(ValueError):
    """The request cannot be done; the message says why in plain words."""


@dataclass
class Message:
    id: str
    role: str  # "user" | "helper" | "system"
    text: str
    at: float
    run_id: str | None = None
    outcome: str | None = None
    risk: str | None = None
    files: list = field(default_factory=list)  # ids of the files this answer was written from
    blocked: list = field(default_factory=list)  # things the helper tried that were refused
    proposals: int = 0  # suggestions to remember that came with this answer
    price: int = 0
    pay: str | None = None  # state of the money for this answer (RESULT_READY, SETTLED, ...)


@dataclass
class Lens:
    types: list = field(default_factory=lambda: ["note", "contact"])
    max_sensitivity: str = "medium"
    include: list = field(default_factory=list)
    exclude: list = field(default_factory=list)


@dataclass
class Thread:
    id: str
    title: str
    agent_key: str
    created: float
    updated: float
    lens: Lens = field(default_factory=Lens)
    history_turns: int = DEFAULT_HISTORY_TURNS
    budget_cents: int = DEFAULT_BUDGET_CENTS
    messages: list = field(default_factory=list)
    busy: bool = False  # a message is being answered right now


def clean_lens(types, max_sensitivity, include, exclude) -> Lens:
    if not isinstance(types, (list, tuple)) or not all(isinstance(t, str) and TYPE_RE.match(t) for t in types):
        raise ThreadError("choose file types from the drawers")
    if max_sensitivity not in SENSITIVITY:
        raise ThreadError("choose how private the files may be: everyday, personal or secret")
    ids = []
    for name, v in (("include", include), ("exclude", exclude)):
        if not isinstance(v, (list, tuple)) or not all(isinstance(i, str) and 0 < len(i) <= 40 for i in v) or len(v) > 200:
            raise ThreadError(f"the list of files to {name} is not valid")
        ids.append(sorted(set(v)))
    include, exclude = ids  # a file named in both lists is held back: saying no always wins
    return Lens(sorted(set(types)), max_sensitivity, [i for i in include if i not in exclude], exclude)


class ThreadStore:
    def __init__(self, path: Path | None = None, clock=None):
        import time
        self.path = Path(path) if path else None
        self.clock = clock or time.time
        self.lock = threading.RLock()
        self.threads: dict[str, Thread] = {}
        if self.path and self.path.exists():
            for raw in json.loads(self.path.read_text(encoding="utf-8")):
                raw["lens"] = Lens(**raw["lens"])
                raw["messages"] = [Message(**m) for m in raw["messages"]]
                raw["busy"] = False  # nothing can be mid-answer after a restart
                self.threads[raw["id"]] = Thread(**raw)

    def _save(self) -> None:
        if self.path:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps([asdict(t) for t in self.threads.values()], indent=1), encoding="utf-8")
            os.replace(tmp, self.path)

    def get(self, thread_id: str) -> Thread:
        t = self.threads.get(thread_id)
        if t is None:
            raise ThreadError("that chat does not exist any more")
        return t

    def create(self, agent_key: str, title: str = "", lens: Lens | None = None) -> Thread:
        with self.lock:
            if len(self.threads) >= MAX_THREADS:
                raise ThreadError(f"you have {MAX_THREADS} chats; delete some before starting a new one")
            now = self.clock()
            t = Thread(id="t_" + secrets.token_hex(4), title=(title.strip() or "New chat")[:MAX_TITLE], agent_key=agent_key,
                       created=now, updated=now, lens=lens or Lens())
            self.threads[t.id] = t
            self._save()
            return t

    def summaries(self) -> list[dict]:
        with self.lock:
            rows = sorted(self.threads.values(), key=lambda t: t.updated, reverse=True)
            return [{"id": t.id, "title": t.title, "agent_key": t.agent_key, "updated": t.updated, "messages": len(t.messages),
                     "last": next((m.text[:80] for m in reversed(t.messages) if m.role != "system"), "")} for t in rows]

    def settings(self, thread_id: str, *, title=None, types=None, max_sensitivity=None, include=None, exclude=None,
                 history_turns=None, budget_cents=None) -> Thread:
        with self.lock:
            t = self.get(thread_id)
            if title is not None:
                if not isinstance(title, str) or not title.strip():
                    raise ThreadError("a chat needs a name")
                t.title = title.strip()[:MAX_TITLE]
            if any(x is not None for x in (types, max_sensitivity, include, exclude)):
                t.lens = clean_lens(t.lens.types if types is None else types,
                                    t.lens.max_sensitivity if max_sensitivity is None else max_sensitivity,
                                    t.lens.include if include is None else include,
                                    t.lens.exclude if exclude is None else exclude)
            if history_turns is not None:
                if not isinstance(history_turns, int) or isinstance(history_turns, bool) or not 0 <= history_turns <= MAX_HISTORY_TURNS:
                    raise ThreadError(f"the helper can remember between 0 and {MAX_HISTORY_TURNS} earlier messages")
                t.history_turns = history_turns
            if budget_cents is not None:
                if not isinstance(budget_cents, int) or isinstance(budget_cents, bool) or not 0 <= budget_cents <= MAX_BUDGET_CENTS:
                    raise ThreadError(f"the spending limit must be between 0 and {MAX_BUDGET_CENTS // 100} dollars")
                t.budget_cents = budget_cents
            t.updated = self.clock()
            self._save()
            return t

    def begin(self, thread_id: str, text: str) -> Thread:
        """Mark the chat busy and check the message. Raises ThreadError if the chat cannot take a message now."""
        with self.lock:
            t = self.get(thread_id)
            if t.busy:
                raise ThreadError("this chat is still working on your last message")
            if not isinstance(text, str) or not text.strip():
                raise ThreadError("write a message first")
            if len(text) > MAX_TASK_CHARS:
                raise ThreadError(f"messages can be up to {MAX_TASK_CHARS} characters; this one is {len(text)}")
            if len(t.messages) >= MAX_MESSAGES:
                raise ThreadError("this chat is full; start a new one")
            t.busy = True
            return t

    def end(self, thread_id: str) -> None:
        with self.lock:
            t = self.threads.get(thread_id)
            if t:
                t.busy = False

    def add(self, thread_id: str, role: str, text: str, **fields) -> Message:
        with self.lock:
            t = self.get(thread_id)
            m = Message(id="m_" + secrets.token_hex(4), role=role, text=text, at=self.clock(), **fields)
            t.messages.append(m)
            t.updated = m.at
            self._save()
            return m

    def forget(self, thread_id: str, message_id: str) -> None:
        """Remove one message from the conversation, so the helper never sees it again."""
        with self.lock:
            t = self.get(thread_id)
            before = len(t.messages)
            t.messages = [m for m in t.messages if m.id != message_id]
            if len(t.messages) == before:
                raise ThreadError("that message is not in this chat")
            self._save()

    def clear(self, thread_id: str) -> None:
        with self.lock:
            self.get(thread_id).messages = []
            self._save()

    def delete(self, thread_id: str) -> None:
        with self.lock:
            if self.threads.pop(thread_id, None) is None:
                raise ThreadError("that chat does not exist any more")
            self._save()

    def save(self) -> None:
        with self.lock:
            self._save()

    def history_for(self, thread_id: str) -> list[dict]:
        """The earlier turns the next run will be shown: the last `history_turns` user and helper messages."""
        with self.lock:
            t = self.get(thread_id)
            turns = [{"role": m.role, "text": m.text} for m in t.messages if m.role in ("user", "helper")]
            return turns[-t.history_turns:] if t.history_turns else []
