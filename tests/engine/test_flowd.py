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
