"""My helpers: build, try, publish, price and retire your own helpers."""
from __future__ import annotations

from ..api.router import Router


def register(router: Router, app) -> None:
    s = app.studio
    router.add("GET", "/api/studio", lambda r: s.list())
    router.add("GET", "/api/studio/helper", lambda r: s.get(r.arg("id")))
    router.add("POST", "/api/studio/create", lambda r: s.create(r.body.get("id"), r.body.get("template")))
    router.add("POST", "/api/studio/save", lambda r: s.save(r.body.get("id"), r.body))
    router.add("POST", "/api/studio/delete", lambda r: s.delete(r.body.get("id")))
    router.add("POST", "/api/studio/try", lambda r: s.try_it(r.body.get("id"), r.body.get("task"), r.body.get("shelves")))
    router.add("POST", "/api/studio/publish", lambda r: s.publish(r.body.get("id"), r.body, r.body.get("payout_email", "")))
    router.add("POST", "/api/studio/retest", lambda r: s.retest(r.body.get("key")))
    router.add("POST", "/api/studio/retire", lambda r: s.retire(r.body.get("key")))
    router.add("POST", "/api/studio/price", lambda r: s.set_price(r.body.get("key"), r.body, r.body.get("payout_email", "")))
