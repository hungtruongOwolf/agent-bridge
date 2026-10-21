"""Conversations: the list, one chat, sending, settings, and the floor picture."""
from __future__ import annotations

from ..api.router import Router


def register(router: Router, app) -> None:
    chat, threads = app.chat, app.threads
    router.add("GET", "/api/threads", lambda r: {"threads": threads.summaries()})
    router.add("GET", "/api/thread", lambda r: chat.view(r.arg("id")))
    router.add("GET", "/api/thread/context", lambda r: chat.context(r.arg("id"), r.arg("draft")[:1000]))
    router.add("GET", "/api/thread/progress", lambda r: chat.progress(r.arg("id")))
    router.add("GET", "/api/office", lambda r: chat.office())
    router.add("POST", "/api/threads", lambda r: chat.create(r.body))
    for name, fn in (("settings", chat.settings), ("send", chat.send), ("cancel", chat.cancel_pending),
                     ("reject", chat.reject), ("forget", chat.forget), ("clear", chat.clear), ("delete", chat.delete)):
        router.add("POST", "/api/thread/" + name, lambda r, fn=fn: fn(r.body))
