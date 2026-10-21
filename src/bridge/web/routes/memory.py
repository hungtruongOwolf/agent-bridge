"""My memory: reading shelves and notes, and every change to them."""
from __future__ import annotations

from ..api.router import Request, Router


def _ids(r: Request):
    return [x for x in r.arg("ids").split(",") if x][:100] if "ids" in r.query else None


def register(router: Router, app) -> None:
    m = app.memory
    router.add("GET", "/api/memory", lambda r: {"items": m.list(shelf=r.arg("shelf") or None, ids=_ids(r), q=r.arg("q")[:200],
                                                                  offset=int(r.arg("offset", "0") or 0), limit=int(r.arg("limit", "30") or 30))})
    router.add("GET", "/api/memory/trash", lambda r: {"items": m.trash()})
    router.add("GET", "/api/memory/history", lambda r: {"versions": m.history(r.arg("id"))})
    router.add("GET", "/api/memory/tree", lambda r: m.overview())
    router.add("GET", "/api/memory/export", lambda r: m.export_backup(), token=True)  # a backup holds secret notes, so it needs the page's own token

    # every change comes in as {"action": ..., ...}; one table says which action calls what
    actions = {
        "add": lambda b: m.add(str(b.get("type", "note")), str(b.get("text", "")), str(b.get("sensitivity", "low")), str(b.get("shelf", "")), str(b.get("title", ""))),
        "add_many": lambda b: m.add_many(b.get("items"), str(b.get("sensitivity", "low")), str(b.get("type", "note")), str(b.get("shelf", ""))),
        "update": lambda b: m.update(str(b.get("id", "")), text=b.get("text"), sensitivity=b.get("sensitivity"), type=b.get("type"), path=b.get("shelf"), title=b.get("title")),
        "delete": lambda b: m.delete(str(b.get("id", ""))),
        "restore": lambda b: m.restore(str(b.get("id", ""))),
        "empty_trash": lambda b: m.empty_trash(),
        "restore_version": lambda b: m.restore_version(str(b.get("id", "")), b.get("index")),
        "bulk": lambda b: m.bulk(b.get("ids"), str(b.get("op", "")), shelf=b.get("shelf"), level=b.get("level")),
        "restore_backup": lambda b: m.restore_backup(b.get("backup")),
        "move_shelf": lambda b: m.move_shelf(str(b.get("from", "")), str(b.get("to", ""))),
        "shelf_note": lambda b: m.set_label(str(b.get("shelf", "")), b.get("text", "")),
    }

    def change(r: Request):
        fn = actions.get(r.body.get("action"))
        if fn is None:
            raise ValueError("that is not something memory can do")
        return fn(r.body)

    router.add("POST", "/api/memory", change)
