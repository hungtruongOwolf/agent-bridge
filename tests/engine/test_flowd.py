import pytest

from bridge.engine.flowd import Engine, ModelReply, Outcome
from bridge.engine.journal import Journal
from bridge.guard.result_guard import ResultGuard
from bridge.memory.broker import Lens, MemoryBroker
from bridge.memory.vault import Record, Vault
from bridge.pack.workflow import parse

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary"],
    "properties": {"summary": {"type": "string", "maxLength": 300}},
}

WF = """
name: private-analyst
start: read
budget: {tokens: 1000}
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], prompt: sales, memory: lens, next: analyze}
  - {id: analyze, kind: llm, prompt: Summarize, reads: [read], next: check}
  - {id: check, kind: gate, check: has_summary, reads: [analyze], next: done, on_fail: bad}
  - {id: done, kind: return, reads: [analyze]}
  - {id: bad, kind: return}
"""


class Scripted:
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def complete(self, prompt, inputs):
        self.seen.append(inputs)
        return self.replies.pop(0)


def build(model, wf=WF, **lens_kw):
    vault = Vault([
        Record("n1", "note", "low", "Sales pipeline: three big accounts at risk"),
        Record("f1", "finance", "high", "Bank account 000111222"),
    ])
    broker = MemoryBroker(vault, Lens(types=frozenset({"note"}), **lens_kw), run_seed="s")
    eng = Engine(parse(wf), model=model, broker=broker, guard=ResultGuard(SCHEMA),
                 journal=Journal(), checks={"has_summary": lambda i: bool(i["analyze"].get("summary"))})
    return eng, broker


def test_happy_path_completes_and_journals():
    eng, _ = build(Scripted(ModelReply({"summary": "Accounts at risk."}, tokens=50)))
    r = eng.run()
    assert r.outcome is Outcome.COMPLETE and r.result == {"summary": "Accounts at risk."}
    kinds = [e["kind"] for e in eng.journal.entries]
    assert kinds[0] == "run_started" and kinds[-1] == "run_finished"
    assert kinds.count("step_committed") == 3
    eng.journal.verify()


def test_step_sees_only_what_it_reads():
    model = Scripted(ModelReply({"summary": "ok"}))
    eng, _ = build(model)
    eng.run()
    assert list(model.seen[0]) == ["read"]
    assert model.seen[0]["read"][0]["id"] == "n1"


def test_failed_gate_routes_to_on_fail_and_run_fails_cleanly():
    eng, _ = build(Scripted(ModelReply({"summary": ""})))
    r = eng.run()
    assert r.outcome is Outcome.FAILED_PACK and r.result is None


def test_pack_copying_a_record_verbatim_is_denied():
    eng, _ = build(Scripted(ModelReply({"summary": "Sales pipeline: three big accounts at risk"})))
    # short record: under the overlap limit so it passes; make a long one fail
    eng.guard = ResultGuard(SCHEMA, max_overlap=10)
    assert eng.run().outcome is Outcome.FAILED_PACK


def test_budget_exhaustion_ends_partial_without_another_model_call():
    wf = WF.replace("budget: {tokens: 1000}", "budget: {tokens: 10}")
    # a second llm step is needed to hit the budget (no loops yet)
    two = wf.replace("next: check}", "next: analyze2}").replace(
        "  - {id: check,", "  - {id: analyze2, kind: llm, prompt: again, reads: [analyze], next: check}\n  - {id: check,")
    model = Scripted(ModelReply({"summary": "a"}, tokens=50), ModelReply({"summary": "b"}, tokens=50))
    eng, _ = build(model, wf=two)
    r = eng.run()
    assert r.outcome is Outcome.PARTIAL_BUDGET and len(model.replies) == 1  # second call never made


def test_pack_touching_a_decoy_is_killed_and_nothing_is_delivered():
    wf = """
name: thief
start: peek
steps:
  - {id: peek, kind: tool, tool: memory_search, tools: [memory_search], prompt: bank, next: grab}
  - {id: grab, kind: return, reads: [peek]}
"""
    eng, broker = build(Scripted(), wf=wf)
    # the pack asks the broker about a type outside its lens, then reads the bait id
    decoy = broker.search("bank", type="finance").records[0]["id"]
    wf2 = wf.replace("tool: memory_search", "tool: memory_read").replace("tools: [memory_search]", "tools: [memory_read]") \
            .replace("prompt: bank", f"prompt: {decoy}")
    eng2 = Engine(parse(wf2), model=Scripted(), broker=broker, guard=ResultGuard(SCHEMA), journal=Journal())
    r = eng2.run()
    assert r.outcome is Outcome.KILLED and r.result is None
    assert any(e["kind"] == "incident" for e in eng2.journal.entries)


def test_canary_in_final_result_kills_even_if_the_read_was_never_logged_as_kill():
    eng, broker = build(Scripted())
    decoy_text = broker.search("x", type="finance").records[0]["text"]
    eng.model = Scripted(ModelReply({"summary": f"leaked: {decoy_text}"}))
    r = eng.run()
    assert r.outcome is Outcome.KILLED and r.result is None


def test_ungranted_tool_is_refused_by_the_engine_itself():
    eng, _ = build(Scripted())
    step = eng.wf.steps["read"]
    object.__setattr__(step, "tools", ())  # bypass the parser to prove the engine re-checks
    r = eng.run()
    assert r.outcome is Outcome.FAILED_PACK and "not granted" in r.reasons[0]


def test_tool_step_can_ask_for_a_type_outside_the_lens_and_gets_bait():
    wf = """
name: prober
start: ask
steps:
  - {id: ask, kind: tool, tool: memory_search, tools: [memory_search], prompt: bank, type: finance, next: out}
  - {id: out, kind: return, reads: [ask]}
"""
    eng, broker = build(Scripted(), wf=wf)
    eng.run()
    assert [e.kind for e in broker.events] == ["OFF_LENS_QUERY"]


CODE_WF = """
name: calc
start: read
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], prompt: sales, next: calc}
  - {id: calc, kind: code, script: "result = {'summary': 'n=' + str(len(inputs['read']))}", reads: [read], next: done}
  - {id: done, kind: return, reads: [calc]}
"""


class FakeCell:
    def __init__(self, ok=True, value=None, error=""):
        self.ok, self.value, self.error, self.calls = ok, value, error, []

    def run(self, script, inputs):
        from bridge.sandbox.cell import CellResult
        self.calls.append((script, inputs))
        return CellResult(self.ok, self.value, self.error)


def test_code_step_runs_in_the_cell_with_only_its_reads():
    eng, _ = build(Scripted(), wf=CODE_WF)
    eng.cell = FakeCell(value={"summary": "n=1"})
    r = eng.run()
    assert r.outcome is Outcome.COMPLETE and r.result == {"summary": "n=1"}
    script, inputs = eng.cell.calls[0]
    assert list(inputs) == ["read"]
    assert any(e["kind"] == "cell_run" for e in eng.journal.entries)


def test_cell_failure_fails_the_run_without_delivering():
    eng, _ = build(Scripted(), wf=CODE_WF)
    eng.cell = FakeCell(ok=False, error="cell exceeded 30s")
    r = eng.run()
    assert r.outcome is Outcome.FAILED_PACK and "exceeded" in r.reasons[0]


def test_code_step_without_a_cell_fails_closed():
    eng, _ = build(Scripted(), wf=CODE_WF)
    r = eng.run()
    assert r.outcome is Outcome.FAILED_PACK and "no Cell" in r.reasons[0]


def test_model_failure_is_an_infra_failure_not_a_pack_failure():
    class Down:
        def complete(self, prompt, inputs):
            raise TimeoutError("provider down")

    eng, _ = build(Down())
    r = eng.run()
    assert r.outcome is Outcome.FAILED_INFRA and "TimeoutError" in r.reasons[0]
    assert any(e["kind"] == "model_error" for e in eng.journal.entries)
    assert eng.journal.entries[-1]["kind"] == "run_finished"


PROPOSE_WF = """
name: remember
start: read
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], prompt: sales, next: analyze}
  - {id: analyze, kind: llm, prompt: Summarize, reads: [read], next: remember}
  - {id: remember, kind: llm, prompt: What is worth remembering, reads: [read], next: done}
  - {id: done, kind: return, reads: [analyze, remember], propose: remember}
"""


class Two:
    def __init__(self, a, b):
        self.r = [a, b]

    def complete(self, prompt, inputs):
        return self.r.pop(0)


def test_proposals_are_returned_separately_from_the_result():
    prop = {"proposals": [{"type": "note", "text": "Acme renewal at risk"}]}
    eng, _ = build(Two(ModelReply({"summary": "ok"}), ModelReply(prop)), wf=PROPOSE_WF)
    r = eng.run()
    assert r.outcome is Outcome.COMPLETE and r.result == {"summary": "ok"}
    assert r.proposals == prop["proposals"]


def test_canary_inside_a_proposal_kills_the_run():
    eng, broker = build(Scripted(), wf=PROPOSE_WF)
    decoy = broker.search("x", type="finance").records[0]["text"]
    eng.model = Two(ModelReply({"summary": "ok"}), ModelReply({"proposals": [{"type": "note", "text": decoy}]}))
    r = eng.run()
    assert r.outcome is Outcome.KILLED and r.result is None and r.proposals == []


def test_proposal_copying_a_record_is_dropped_but_the_result_survives():
    eng, _ = build(Scripted(), wf=PROPOSE_WF)
    eng.guard = ResultGuard(SCHEMA, max_overlap=10)
    copy = {"proposals": [{"type": "note", "text": "Sales pipeline: three big accounts at risk"}]}
    eng.model = Two(ModelReply({"summary": "fine"}), ModelReply(copy))
    r = eng.run()
    assert r.outcome is Outcome.COMPLETE and r.proposals == []


def test_run_without_propose_has_no_proposals():
    eng, _ = build(Scripted(ModelReply({"summary": "ok"})))
    assert eng.run().proposals == []


class FakeWeb:
    def __init__(self, results=None):
        self.queries, self.results = [], results or [{"title": "T", "url": "https://x.example", "snippet": "renewals are slowing"}]

    def search(self, query):
        self.queries.append(query)
        return self.results


WEB_WF = """
name: research
start: web
steps:
  - {id: web, kind: tool, tool: web_search, tools: [web_search], prompt: "saas renewal budget trends 2026", next: read}
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], memory: lens, prompt: sales, next: analyze}
  - {id: analyze, kind: llm, prompt: Compare, reads: [web, read], next: done}
  - {id: done, kind: return, reads: [analyze]}
"""


def test_public_web_step_feeds_a_private_analysis():
    model = Scripted(ModelReply({"summary": "Renewals are slowing; Acme at risk."}))
    eng, _ = build(model, wf=WEB_WF)
    eng.web = FakeWeb()
    r = eng.run()
    assert r.outcome is Outcome.COMPLETE and eng.web.queries == ["saas renewal budget trends 2026"]
    assert set(model.seen[0]) == {"web", "read"} and model.seen[0]["web"][0]["snippet"] == "renewals are slowing"
    assert any(e["kind"] == "web_search" for e in eng.journal.entries)


def test_web_step_without_a_search_backend_fails_closed():
    eng, _ = build(Scripted(), wf=WEB_WF)
    r = eng.run()
    assert r.outcome is Outcome.FAILED_PACK and "no web search" in r.reasons[0]


def test_query_copying_a_staged_record_is_blocked_before_it_leaves():
    leaky = WEB_WF.replace("saas renewal budget trends 2026", "Sales pipeline: three big accounts at risk")
    eng, _ = build(Scripted(), wf=leaky)
    eng.web = FakeWeb()
    r = eng.run()
    assert r.outcome is Outcome.FAILED_PACK and eng.web.queries == []  # nothing was sent
    assert [v["kind"] for v in eng.violations] == ["WEB_QUERY_LEAK"]


def test_query_from_a_public_llm_step_is_used():
    wf = """
name: planner
start: plan
steps:
  - {id: plan, kind: llm, prompt: "write a query", next: web}
  - {id: web, kind: tool, tool: web_search, tools: [web_search], reads: [plan], next: out}
  - {id: out, kind: return, reads: [web]}
"""
    eng, _ = build(Scripted(ModelReply({"query": "saas churn benchmarks"})), wf=wf)
    eng.web = FakeWeb()
    eng.run()
    assert eng.web.queries == ["saas churn benchmarks"]


def test_journal_says_which_door_a_step_used_and_which_records_it_received():
    eng, _ = build(Scripted(ModelReply({"summary": "ok"})))
    eng.run()
    started = {e["data"]["step"]: e["data"] for e in eng.journal.entries if e["kind"] == "step_started"}
    committed = {e["data"]["step"]: e["data"] for e in eng.journal.entries if e["kind"] == "step_committed"}
    assert started["read"]["tool"] == "memory_search" and "tool" not in started["analyze"]
    assert committed["read"]["records"] == ["n1"] and committed["read"]["blocked"] == []


def test_the_decoy_returned_for_an_off_lens_query_is_not_listed_as_a_received_record():
    wf = """
name: prober
start: ask
steps:
  - {id: ask, kind: tool, tool: memory_search, tools: [memory_search], prompt: bank, type: finance, next: out}
  - {id: out, kind: return, reads: [ask]}
"""
    eng, _ = build(Scripted(), wf=wf)
    eng.run()
    c = next(e["data"] for e in eng.journal.entries if e["kind"] == "step_committed" and e["data"]["step"] == "ask")
    assert c["records"] == [] and c["blocked"] == ["OFF_LENS_QUERY"]


def test_web_steps_record_how_many_results_came_back():
    eng, _ = build(Scripted(ModelReply({"summary": "ok"})), wf=WEB_WF)
    eng.web = FakeWeb()
    eng.run()
    c = next(e["data"] for e in eng.journal.entries if e["kind"] == "step_committed" and e["data"]["step"] == "web")
    assert c["results"] == 1 and c["records"] == []


CHAT_WF = """
name: chat
start: read
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], memory: lens, prompt: "{task}", next: answer}
  - {id: answer, kind: llm, prompt: Answer, reads: [task, history, read], next: done}
  - {id: done, kind: return, reads: [answer]}
"""


def chat_engine(model, task, history=None, wf=CHAT_WF):
    eng, broker = build(model, wf=wf)
    eng.task = task
    from bridge.engine.limits import clean_history
    eng.history = clean_history(history)
    return eng, broker


def test_the_question_and_history_reach_the_model_and_drive_the_memory_search():
    model = Scripted(ModelReply({"summary": "Acme is at risk."}))
    eng, _ = chat_engine(model, "any pipeline news?", [{"role": "user", "text": "hi"}, {"role": "helper", "text": "hello"}])
    r = eng.run()
    seen = model.seen[0]
    assert r.outcome is Outcome.COMPLETE and seen["task"] == "any pipeline news?"
    assert [h["role"] for h in seen["history"]] == ["user", "helper"]
    assert [rec["id"] for rec in seen["read"]] == ["n1"]  # found because the question mentions pipeline


def test_the_run_record_counts_the_message_but_does_not_store_its_text():
    eng, _ = chat_engine(Scripted(ModelReply({"summary": "ok"})), "pipeline secrets of the CEO", [{"role": "user", "text": "earlier"}])
    eng.run()
    start = eng.journal.entries[0]["data"]
    assert start["task_chars"] == len("pipeline secrets of the CEO") and start["history_turns"] == 1
    assert "CEO" not in str(eng.journal.entries)


def test_a_message_longer_than_the_limit_is_refused_up_front():
    from bridge.engine.limits import MAX_TASK_CHARS
    eng, broker = build(Scripted(), wf=CHAT_WF)
    with pytest.raises(ValueError, match="longer than"):
        Engine(eng.wf, model=Scripted(), broker=broker, guard=eng.guard, task="x" * (MAX_TASK_CHARS + 1))


def test_history_is_trimmed_to_recent_short_plain_turns():
    from bridge.engine.limits import MAX_HISTORY_TEXT, MAX_HISTORY_TURNS, clean_history
    many = [{"role": "user", "text": f"m{i}"} for i in range(30)]
    kept = clean_history(many)
    assert len(kept) == MAX_HISTORY_TURNS and kept[-1]["text"] == "m29"
    long_one = clean_history([{"role": "helper", "text": "y" * 5000}])
    assert len(long_one[0]["text"]) == MAX_HISTORY_TEXT
    assert clean_history([{"role": "system", "text": "evil"}, {"role": "user"}, "junk", None]) == []


def test_a_web_search_that_fails_ends_the_run_as_an_infrastructure_problem():
    class Down:
        def search(self, q):
            raise TimeoutError("search service down")

    eng, _ = build(Scripted(), wf=WEB_WF)
    eng.web = Down()
    r = eng.run()
    assert r.outcome is Outcome.FAILED_INFRA and "web search failed" in r.reasons[0]


def test_a_container_engine_that_cannot_start_is_an_infrastructure_problem():
    class Broken:
        def run(self, script, inputs):
            raise FileNotFoundError("wsl.exe")

    eng, _ = build(Scripted(), wf=CODE_WF)
    eng.cell = Broken()
    r = eng.run()
    assert r.outcome is Outcome.FAILED_INFRA and "sealed room" in r.reasons[0]


def test_the_task_can_be_the_web_query_and_is_still_checked_against_your_records():
    wf = """
name: ask-web
start: web
steps:
  - {id: web, kind: tool, tool: web_search, tools: [web_search], prompt: "{task}", reads: [task], next: out}
  - {id: out, kind: return, reads: [web]}
"""
    eng, _ = build(Scripted(), wf=wf)
    eng.web = FakeWeb()
    eng.task = "saas renewal benchmarks"
    eng.run()
    assert eng.web.queries == ["saas renewal benchmarks"]
    eng2, _ = build(Scripted(), wf=wf)
    eng2.web = FakeWeb()
    eng2.task = "Sales pipeline: three big accounts at risk"  # the user pasted a private note into the question
    r = eng2.run()
    assert eng2.web.queries == [] and [v["kind"] for v in eng2.violations] == ["WEB_QUERY_LEAK"]


def test_a_model_call_is_journaled_with_what_it_carried_out():
    class Named(Scripted):
        provider = "Some Provider"

    eng, broker = build(Named(ModelReply({"summary": "ok"}, tokens=5)))
    eng.run()
    call = next(e["data"] for e in eng.journal.entries if e["kind"] == "model_call")
    assert call["sent_records"] == ["n1"] and call["sent_records"] == broker.reads
    assert call["sent_chars"] > 0 and call["sent_parts"] == ["read"] and call["sent_to"] == "Some Provider"
