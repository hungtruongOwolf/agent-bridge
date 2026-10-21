"""The overall state, running helpers, memory suggestions, and the PayPal return pages."""
from __future__ import annotations

from ...chat.plain import how_made
from ..api.router import HttpError, Reply, Request, Router


def _return_page(approved: bool) -> Reply:
    word = "approved" if approved else "cancelled"
    note = ("You approved the hold. This tab can be closed: the console carries on by itself."
            if approved else "You cancelled. Nothing was held or charged. You can close this tab.")
    script = ("<script>try{const c=new BroadcastChannel('agent-bridge-paypal');c.postMessage('" + word + "');c.close();}catch(e){}"
              "try{localStorage.setItem('agent-bridge-paypal','" + word + ":'+Date.now())}catch(e){}</script>")
    html = ("<!doctype html><meta charset=utf-8><title>agent-bridge</title>"
            "<body style='font:16px system-ui;padding:40px'>" + note + script + "</body>")
    return Reply(200, html.encode(), "text/html; charset=utf-8")


def register(router: Router, app) -> None:
    runs, memory = app.runs, app.memory

    router.add("GET", "/api/state", lambda r: app.state())
    router.add("GET", "/paypal/return", lambda r: _return_page(True))
    router.add("GET", "/paypal/cancel", lambda r: _return_page(False))

    def report(r: Request):
        with app.lock:
            rep = runs.reports.get(r.params["run_id"])
        if rep is None:
            raise HttpError(404, "unknown run")
        return rep

    def how(r: Request):
        with app.lock:
            rep = runs.reports.get(r.arg("run_id"))
        if rep is None:
            raise HttpError(404, "the details of this answer are no longer kept")
        return {"steps": how_made(rep["steps"])}

    router.add("GET", "/api/report/:run_id", report)
    router.add("GET", "/api/how", how)
    router.add("GET", "/api/match", lambda r: {"matches": app.world.market.match(r.arg("q")[:300])})
    router.add("GET", "/api/agent", lambda r: app.world.market.profile(r.arg("key")))

    router.add("POST", "/api/run", lambda r: runs.run(r.body))
    router.add("POST", "/api/run/continue", lambda r: runs.continue_run(r.body))
    router.add("POST", "/api/star", lambda r: {"stars": app.world.registry.star(str(r.body["key"]), app.requester)})

    def decide(r: Request):
        action, pid = r.body.get("action"), str(r.body.get("id", ""))
        if action == "accept":
            return memory.accept_proposal(pid)
        if action == "reject":
            return memory.reject_proposal(pid)
        raise ValueError("action must be accept or reject")

    router.add("POST", "/api/proposal", decide)
    router.add("POST", "/api/revert", lambda r: memory.revert_run(str(r.body.get("run_id", ""))))
