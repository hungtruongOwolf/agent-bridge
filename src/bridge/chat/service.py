"""Chat with a hired helper: many turns in one thread, with the person in control of what the helper can see.

One turn:
  1. check the message and the spending limit;
  2. the previous answer counts as good (its money is settled) unless you already said it was not;
  3. run the helper with your question, the last few turns, and only the files this chat shares;
  4. turn the outcome into a message, record which files it used, and keep the money in step with it.
The helper never gets more than the thread's settings allow, and a turn that goes wrong never leaves the chat stuck.
"""
from __future__ import annotations

from ..engine.limits import clean_history
from ..memory.broker import Lens as RunLens
from ..memory.broker import MemoryBroker
from ..payments.ledger import TERMINAL, PendingError, StateError
from ..payments.provider import ProviderError
from .plain import failure_message, stopped_message
from .threads import ThreadError, clean_lens


class ChatBusy(ThreadError):
    """A message is already being answered in this chat."""


class ChatService:
    def __init__(self, app):
        self.app = app
        self.store = app.threads
        self.running: dict[str, bool] = {}  # chats with an answer being written right now (this process)

    # ---- helpers --------------------------------------------------------------------------------
    def run_lens(self, t) -> RunLens:
        return RunLens(types=frozenset(t.lens.types), max_sensitivity=t.lens.max_sensitivity,
                       include=frozenset(t.lens.include), exclude=frozenset(t.lens.exclude))

    def _agent(self, t) -> dict:
        try:
            rec, _ = self.app.resolve_agent(t.agent_key)
        except ValueError:
            return {"id": "gone", "name": "This helper", "version": "", "status": "gone", "price_cents": 0, "available": False}
        return {"id": rec.id, "name": rec.id.replace("-", " ").title(), "version": rec.version,
                "status": self.app.world.market.status(rec), "price_cents": max(1, round(rec.listing.price_usd * 100)),
                "available": True, "key": rec.key}

    def money(self, t) -> dict:
        """What this chat has cost, and what is still undecided, in cents."""
        spent = held = 0
        for rid in t.runs:
            row = self.app.ledger.rows.get(rid)
            if row is None:
                continue
            taken = row.captured()
            spent += taken
            if row.state not in TERMINAL and row.state != "AWAITING_APPROVAL":
                held += max(0, row.price - taken - sum(c["amount"] for c in row.captures if c["id"] in row.refunded))
        left = max(0, t.budget_cents - spent - held)
        return {"limit": t.budget_cents, "spent": spent, "held": held, "left": left}

    def _projected(self, t) -> int:
        """Cost so far if every undecided answer counts as good (the next message makes them so)."""
        total = 0
        for rid in t.runs:
            row = self.app.ledger.rows.get(rid)
            if row is None:
                continue
            total += row.price if row.state in ("RESULT_READY", "SETTLED", "RUNNING", "AUTHORIZED") else row.captured()
        return total

    def view(self, thread_id: str) -> dict:
        t = self.store.get(thread_id)
        msgs = []
        for m in t.messages:
            d = {k: getattr(m, k) for k in ("id", "role", "text", "at", "run_id", "outcome", "risk", "files", "blocked", "proposals", "price", "pay")}
            row = self.app.ledger.rows.get(m.run_id) if m.run_id else None
            d["payment"] = None if row is None else {
                "state": row.state, "price": row.price, "captured": row.captured(),
                "can_reject": row.state == "RESULT_READY", "accept_by": row.accept_by}
            msgs.append(d)
        return {"id": t.id, "title": t.title, "agent": self._agent(t), "lens": {
                    "types": t.lens.types, "max_sensitivity": t.lens.max_sensitivity, "include": t.lens.include, "exclude": t.lens.exclude},
                "history_turns": t.history_turns, "budget": self.money(t), "messages": msgs, "busy": t.busy}

    def history(self, t) -> list[dict]:
        """Earlier turns for the next run. Answers written from a file that is locked now are left out."""
        vault = self.app.memory.vault()
        shared = set(MemoryBroker(vault, self.run_lens(t), run_seed="history").manifest)
        banned = {m.id for m in t.messages if m.role == "helper" and any(f not in shared for f in m.files)}
        turns = [m for m in t.messages if m.role in ("user", "helper") and m.id not in banned]
        out = [{"role": m.role, "text": m.text} for m in turns]
        return out[-t.history_turns:] if t.history_turns else []

    # ---- thread management ----------------------------------------------------------------------
    def create(self, body: dict) -> dict:
        key = str(body.get("agent_key", ""))
        self.app.resolve_agent(key)  # refuses helpers that are gone or revoked
        lens = None
        if any(k in body for k in ("types", "max_sensitivity", "include", "exclude")):
            lens = clean_lens(body.get("types", ["note", "contact"]), body.get("max_sensitivity", "medium"),
                              body.get("include", []), body.get("exclude", []))
        t = self.store.create(key, str(body.get("title", "")), lens)
        return self.view(t.id)

    def settings(self, body: dict) -> dict:
        if body.get("reset_busy"):  # a restart-proof escape hatch: only when no approval is waiting for this chat
            tid = str(body.get("id", ""))
            with self.app.lock:
                waiting = any(p.get("thread_id") == tid for p in self.app.pending.values())
            if not waiting and not self.running.get(tid):
                self.store.end(tid)
        keys = ("title", "types", "max_sensitivity", "include", "exclude", "history_turns", "budget_cents")
        self.store.settings(str(body.get("id", "")), **{k: body[k] for k in keys if k in body})
        return self.view(str(body["id"]))

    def delete(self, body: dict) -> dict:
        tid = str(body.get("id", ""))
        if self.store.get(tid).busy:
            raise ChatBusy("wait for the answer to arrive before deleting this chat")
        self.store.delete(tid)
        return {"deleted": tid}

    def forget(self, body: dict) -> dict:
        self.store.forget(str(body.get("id", "")), str(body.get("message_id", "")))
        return self.view(str(body["id"]))

    def clear(self, body: dict) -> dict:
        tid = str(body.get("id", ""))
        if self.store.get(tid).busy:
            raise ChatBusy("wait for the answer to arrive before clearing this chat")
        self.store.clear(tid)
        return self.view(tid)

    # ---- what the helper will see ----------------------------------------------------------------
    def context(self, thread_id: str, draft: str = "") -> dict:
        t = self.store.get(thread_id)
        vault = self.app.memory.vault()
        lens = self.run_lens(t)
        broker = MemoryBroker(vault, lens, run_seed="preview")
        shared_ids = set(broker.manifest)
        shared, locked = [], []
        for r in vault.all():
            item = {"id": r.id, "type": r.type, "sensitivity": r.sensitivity, "text": r.text}
            if r.id in shared_ids:
                shared.append(item)
            else:
                item["why"] = ("You held this one back." if r.id in lens.exclude else
                               "Its drawer is closed." if r.type not in lens.types else
                               "Too private for the level you chose." if r.sensitivity != "low" else "Not shared.")
                item.pop("text")
                locked.append(item)
        likely = [x["id"] for x in broker.search(draft, fallback=True).records] if draft.strip() else []
        hist = self.history(t)
        return {"thread": t.id, "helper": self._agent(t), "shared": shared, "locked": locked, "likely": likely,
                "history": hist, "history_turns": t.history_turns, "budget": self.money(t),
                "goes_to_the_brain": ("To write an answer, your message, the files that match it and the last " + str(t.history_turns) +
                                      " messages of this chat are sent to the thinking service (Nemotron on Nebius), through your own assistant. "
                                      "The helper itself cannot send anything anywhere.")}

    # ---- sending a message -----------------------------------------------------------------------
    def send(self, body: dict) -> dict:
        tid, text = str(body.get("id", "")), body.get("text")
        try:
            t = self.store.begin(tid, text)
        except ThreadError as e:
            if "still working" in str(e):
                raise ChatBusy(str(e)) from e
            raise
        try:
            rec, pack_dir = self.app.resolve_agent(t.agent_key)
            price = max(1, round(rec.listing.price_usd * 100))
            with self.app.lock:
                if self._projected(t) + price > t.budget_cents:
                    raise ThreadError(f"This chat has a spending limit of {t.budget_cents}¢ and another answer ({price}¢) would go past it. "
                                      "Raise the limit in the chat settings to keep going.")
            run_id = self.app.new_run_id()
            row = self.app.hire(rec, run_id)
            self.store.track(tid, run_id)
            params = {"rec": rec, "pack_dir": pack_dir, "lens": self.run_lens(t), "task": text.strip(),
                      "history": clean_history(self.history(t)), "simulate": bool(body.get("simulate")), "thread_id": tid}
            if row.state == "AWAITING_APPROVAL":  # the chat stays busy until you approve or cancel
                with self.app.lock:
                    self.app.pending[run_id] = params
                return {"needs_approval": True, "run_id": run_id, "approve_url": row.approve_url, "price": price, "thread": self.view(tid)}
            return self.finish_turn(run_id, params)
        except BaseException:
            self.store.end(tid)
            raise

    def finish_turn(self, run_id: str, params: dict) -> dict:
        tid = params["thread_id"]
        started = False
        try:
            t = self.store.get(tid)
            params = dict(params, lens=self.run_lens(t), history=clean_history(self.history(t)))  # settings changed while waiting count
            self._accept_previous(t, run_id)
            self.store.add(tid, "user", params["task"])
            started = True
            self.running[tid] = True
            try:
                out = self.app.job(run_id, params)
            finally:
                self.running.pop(tid, None)
            self._record_answer(t, run_id, out, params["rec"])
            view = self.view(tid)
            return {"thread": view, "report": out}
        except BaseException:
            if not started:  # never leave a hold open for a run that did not start
                with self.app.lock:
                    try:
                        self.app.ledger.fail_infra(run_id, self.app.clock(), "the message could not be started")
                    except Exception:
                        pass
            raise
        finally:
            self.store.end(tid)

    def _accept_previous(self, t, new_run_id: str) -> None:
        """Sending a new message means the last answer was good enough: settle its money."""
        with self.app.lock:
            for rid in reversed([r for r in t.runs if r != new_run_id]):
                row = self.app.ledger.rows.get(rid)
                if row is not None and row.run_id != new_run_id and row.state == "RESULT_READY":
                    try:
                        self.app.ledger.accept(row.run_id, self.app.clock())
                        self.app.ledger.release_payouts(self.app.clock())
                    except (StateError, ProviderError, PendingError):
                        pass  # settled some other way, or the provider is slow: the deadline settles it later
                if row is not None:
                    break

    def _record_answer(self, t, run_id: str, out: dict, rec) -> None:
        helper = rec.id.replace("-", " ").title()
        pay = self.app.ledger.rows[run_id]
        kinds = [e["kind"] for e in out.get("broker_events", [])]
        common = dict(run_id=run_id, outcome=out["outcome"], files=list(out.get("records_handed", [])), blocked=kinds,
                      price=pay.price, pay=pay.state)
        if out["outcome"] == "COMPLETE":
            risk = out["result"].get("risk")
            self.store.add(t.id, "helper", out["result"]["summary"], risk=None if risk in (None, "n/a") else risk,
                           proposals=len(out.get("proposals", [])), **common)
        elif out["outcome"] == "KILLED":
            self.store.add(t.id, "system", stopped_message(helper, kinds), **common)
        else:
            self.store.add(t.id, "system", failure_message(out["outcome"]), **common)

    # ---- deciding on an answer --------------------------------------------------------------------
    def reject(self, body: dict) -> dict:
        tid, mid = str(body.get("id", "")), str(body.get("message_id", ""))
        t = self.store.get(tid)
        m = next((x for x in t.messages if x.id == mid), None)
        if m is None or not m.run_id:
            raise ThreadError("that message is not an answer you can mark as not helpful")
        with self.app.lock:
            try:
                self.app.ledger.reject(m.run_id, self.app.clock(), "not helpful")
            except StateError as e:
                raise ThreadError("that answer was already counted as good") from e
            self.app.ledger.release_payouts(self.app.clock())
        return self.view(tid)

    def cancel_pending(self, body: dict) -> dict:
        """Give up on a message that was waiting for you to approve the hold."""
        run_id = str(body.get("run_id", ""))
        with self.app.lock:
            params = self.app.pending.pop(run_id, None)
        if params is None:
            raise ThreadError("nothing is waiting for approval under that id")
        with self.app.lock:
            try:
                self.app.ledger.fail_infra(run_id, self.app.clock(), "you did not approve the hold")
            except StateError:
                pass
        if not params.get("thread_id"):
            return {"cancelled": run_id}
        self.store.end(params["thread_id"])
        return self.view(params["thread_id"])
