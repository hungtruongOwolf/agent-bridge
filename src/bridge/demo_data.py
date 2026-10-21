"""`bridge demo-data`: build a state folder that shows every case the application handles, so a demo starts full instead of empty.

    bridge demo-data --state .bridge-demo
    bridge serve --state .bridge-demo --vault examples/vault-library.json

Everything is made by using the application the way a person would (real chats answered by the real model, real payments through
the test provider), spread over the last two weeks. Nothing is written into the files by hand, so what the demo shows is what the
application really does. Money is test money.

What it leaves behind:
  chats         five conversations: an account review with follow-ups, meeting actions, an answer marked not helpful, a question
                about secret notes the helper cannot see, and a helper caught copying notes
  payments      paid in full, paid by files read, deposit only after "not helpful", refunded after a caught cheat, a monthly plan
                with included answers, and one answer still waiting for a decision
  memory        a lived-in library, notes edited several times (earlier versions), notes in the trash, shelf notes, a long note,
                one suggestion accepted from a helper, one refused, and some still waiting
  my helpers    three helpers you built: one priced by files, one monthly plan, one still a draft
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from .engine.nebius import NebiusModel, load_api_key
from .engine.tavily import TavilySearch, load_tavily_key
from .sandbox.cell import DockerCell, docker_available
from .world import DEMO_PACKS, open_world, seed as seed_world

DAY = 86400
CARRY = ("author.key", "certifier.key", "registry.json", "attestations.json", "candidates", "published")  # a certified marketplace to start from


class Clock:
    """Demo time: starts two weeks ago and moves forward when told to; `live()` hands over to the real clock for the last steps."""

    def __init__(self):
        self.t, self.on = time.time() - 13 * DAY, False

    def __call__(self) -> float:
        return time.time() if self.on else self.t

    def days(self, n: float) -> None:
        self.t += n * DAY

    def live(self) -> None:
        self.on = True


def _key(app, helper_id: str) -> str:
    recs = [r for r in app.world.registry.installable() if r.id == helper_id]
    if not recs:
        raise RuntimeError(f"the helper {helper_id} is not on the market")
    return max(recs, key=lambda r: r.version).key


def _say(app, tid: str, text: str, log) -> dict:
    out = app.chat.send({"id": tid, "text": text})
    m = out["thread"]["messages"][-1]
    log(f"    {text[:56]:<56} -> {m['role']}: {m['text'][:70]!r}")
    return m


def _chat(app, helper_id: str, title: str, shelves: list[str], log, budget: int = 600) -> str:
    t = app.chat.create({"agent_key": _key(app, helper_id), "title": title, "shelves": shelves})
    app.chat.settings({"id": t["id"], "budget_cents": budget})
    log(f"  chat '{title}' with {helper_id}")
    return t["id"]


def _wait_tested(app, log, limit_s: int = 1500) -> None:
    start = time.time()
    while time.time() - start < limit_s:
        states = [j.get("state") for j in app.studio.jobs.values()]
        if states and all(s != "running" for s in states):
            log(f"  testing finished: {states}")
            return
        time.sleep(5)
    log("  testing did not finish in time; the helpers stay 'being tested'")


def build(state: Path, packs: Path, vault: Path, env: Path, *, source: Path | None = None, fresh: bool = False, log=print) -> None:
    from .web.server import App

    state = Path(state)
    if fresh and state.exists():
        shutil.rmtree(state)
    state.mkdir(parents=True, exist_ok=True)
    model = NebiusModel(load_api_key(env))
    cell = DockerCell() if docker_available() else None
    web = TavilySearch(load_tavily_key(env))
    if source and (Path(source) / "registry.json").exists() and not (state / "registry.json").exists():
        for name in CARRY:  # the packs were already tested once: reuse their results instead of testing them again
            src = Path(source) / name
            if src.is_dir():
                shutil.copytree(src, state / name, dirs_exist_ok=True)
            elif src.exists():
                shutil.copy2(src, state / name)
        log(f"marketplace copied from {source}")
    world = open_world(state)
    if not world.registry.records:
        seed_world(world, Path(packs), model, model.model, cell=cell, web=web, log=log)

    for name in ("exfil-kit", "data-thief"):  # two helpers that copy notes: the market tests them and shows them as flagged
        if not any(r.id == name for r in world.registry.records.values()):
            rec = world.registry.publish(Path(packs) / name, world.author_key, DEMO_PACKS[name])
            try:
                world.market.add_attestation(world.certifier.certify(Path(packs) / name, model, model.model, cell=cell, web=web))
                log(f"tested {name}: {world.market.status(rec)}")
            except ValueError as e:
                log(f"could not test {name}: {e}")

    clock = Clock()
    app = App(world, Path(packs), Path(vault), Path(env), cell=cell, clock=clock, demo_author_email="")
    app.model_factory = lambda: model
    mem = app.memory

    log("\nmemory")
    for hid, label in (("work/accounts", "Customer deals: who we sell to and what was promised."),
                       ("work/meetings", "Notes from meetings, newest first."),
                       ("personal", "Private life. Never shared with a helper."),
                       ("people/customers", "The people at our customers.")):
        mem.set_label(hid, label)
    notes = {r["id"]: r for r in mem.list(shelf="work/accounts/acme", limit=50)}
    first = next(iter(notes))
    for step in ("Acme asked for a price hold until the end of the month.", "Acme confirmed the price hold in writing; the renewal date is unchanged."):
        mem.update(first, text=step)  # every change keeps the earlier text, so "Earlier versions" has something to show
        clock.days(1)
    pitch = ("Pitch outline for the hackathon demo.\n\n## The problem\nPeople hand their notes to AI tools and cannot see what is taken, "
             "kept or shared.\n\n## The idea\nA helper runs on your own machine and sees only the shelves you open. Secret notes never leave. "
             "A guard checks every answer before it reaches you.\n\n## The demo\nOpen a chat, tick a shelf, ask a question, watch the helper "
             "work in the glass room, then read where the answer came from.\n\n## Money\nYou pay per answer in test money. Nothing is charged until "
             "an answer exists, and you can mark it not helpful.\n\n## What is next\nMore helpers from other authors, certified before they are listed.")
    mem.add("note", pitch, "low", "projects/hackathon", "Pitch outline")
    for rid in [i["id"] for i in mem.list(shelf="recipes", limit=10)][:2]:
        mem.delete(rid)  # two notes in the trash, so "put it back" can be shown

    # ---- 1. an account review: deal-brief, three turns, follow-ups use the conversation so far ------------------------------
    log("\nchats and payments")
    clock.days(0.5)
    a = _chat(app, "deal-brief", "Weekly account review", ["work/accounts", "people/customers"], log)
    for q in ("Give me a briefing on my accounts.", "Which of them needs attention first?", "What did we promise Acme?"):
        _say(app, a, q, log)
        clock.days(0.2)
    waiting = list(app.quarantine.pending())  # helpers suggested facts to remember: say yes to the first, no to the second, leave the rest
    if waiting:
        mem.accept_proposal(waiting[0].id)
    if len(waiting) > 1:
        mem.reject_proposal(waiting[1].id)

    # ---- 2. meeting actions: a helper for a different subject --------------------------------------------------------------
    clock.days(3)
    b = _chat(app, "action-finder", "What did I agree in meetings?", ["work/meetings"], log)
    for q in ("What are my action items from last week?", "Who owns the security questionnaire?"):
        _say(app, b, q, log)
        clock.days(0.1)

    # ---- 3. an answer marked "not helpful": deposit only --------------------------------------------------------------------
    clock.days(2)
    c = _chat(app, "quick-skim", "Quick check on Globex", ["work/accounts/globex"], log)
    m = _say(app, c, "Anything risky with Globex?", log)
    app.chat.reject({"id": c, "message_id": next(x["id"] for x in app.chat.view(c)["messages"] if x["role"] == "helper")})
    log("    marked not helpful")

    # ---- 4. a question about secret notes: the helper cannot see them --------------------------------------------------------
    clock.days(2)
    d = _chat(app, "private-analyst", "My money", ["money", "personal"], log)
    _say(app, d, "What is my bank balance?", log)

    # ---- 5. a helper caught copying notes: stopped by the guard, money returned ------------------------------------------------
    clock.days(1)
    out = app.runs.run({"key": _key(app, "quick-skim"), "types": ["note", "contact"], "task": "Summarise my accounts.", "model": "leak"})
    log(f"  a helper that copies notes was stopped: {out['outcome']}, payment {out['payment']['state']}")

    # ---- 6. my helpers: one priced by files, one monthly plan, one draft ---------------------------------------------------------
    log("\nmy helpers")
    clock.days(0.5)
    s = app.studio
    for hid, title, does, speciality in (
            ("client-pulse", "Client pulse", "Tells you where each client stands, from your notes.", "Sales accounts"),
            ("meeting-digest", "Meeting digest", "Turns your meeting notes into short actions.", "Meeting notes"),
            ("idea-sorter", "Idea sorter", "Groups your loose ideas into themes.", "My helper")):
        h = s.create(hid, "starter")
        manifest = dict(h["manifest"])
        manifest.update(summary=does, speciality=speciality)
        manifest["skills"] = [{"name": title, "does": does, "try_asking": ["Where does each client stand?" if hid == "client-pulse" else "What should I do after these meetings?"]}]
        s.save(hid, {"manifest": manifest})
        log(f"  created {hid}")
    s.publish("client-pulse", {"plan": "per_file", "price_usd": 0.5, "base_usd": 0.05, "per_file_cents": 5}, "pulse.author@example.com")
    s.publish("meeting-digest", {"plan": "monthly", "monthly_usd": 5, "included_answers": 5}, "digest.author@example.com")
    _wait_tested(app, log)

    clock.days(1)
    f = _chat(app, "client-pulse", "Where do my clients stand?", ["work/accounts"], log)
    if _say(app, f, "Where does each client stand?", log)["role"] != "helper":  # a helper can fail on a long question: it is not charged, and you ask again
        _say(app, f, "In one sentence, where does Acme stand?", log)
    clock.days(0.2)
    g = _chat(app, "meeting-digest", "Meeting digest (monthly plan)", ["work/meetings"], log, budget=1500)
    for q in ("What should I do after these meetings?", "And what is due this week?", "Who is waiting on me?"):
        _say(app, g, q, log)  # the first answer buys the plan; the next ones are included
        clock.days(0.2)

    # ---- 7. today: the last answer is left waiting for a decision -------------------------------------------------------------
    clock.live()
    h = _chat(app, "deal-brief", "What changed this week?", ["work/accounts", "work/meetings"], log)
    _say(app, h, "What changed in my accounts this week?", log)

    for r in app.world.registry.installable():
        if r.id in ("deal-brief", "private-analyst", "action-finder"):
            app.world.registry.star(r.key, "you")
    print_summary(app, log)


def print_summary(app, log) -> None:
    pay = app.payments.summary()
    states: dict[str, int] = {}
    for r in app.ledger.rows.values():
        states[r.state] = states.get(r.state, 0) + 1
    log("\nready:")
    log(f"  {len(app.threads.threads)} chats, {app.memory.overview()['total']} notes, {len(app.ledger.rows)} payments {states}")
    log(f"  spent {pay['captured']}¢, on hold {pay['on_hold']}¢, paid out {pay['paid_out']}¢; {len(app.quarantine.pending())} suggestions waiting")
    log("  start it with:  bridge serve --state <that folder> --vault examples/vault-library.json")
