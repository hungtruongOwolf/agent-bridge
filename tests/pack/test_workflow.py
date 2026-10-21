import pytest

from bridge.pack.workflow import WorkflowError, parse

GOOD = """
name: private-analyst
start: read
budget: {usd: 1.5, tokens: 20000}
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], memory: lens, next: analyze}
  - {id: analyze, kind: llm, prompt: "Summarize the records.", next: check}
  - {id: check, kind: gate, check: schema_valid, next: done, on_fail: failed}
  - {id: done, kind: return}
  - {id: failed, kind: return}
"""


def fails(text, fragment):
    with pytest.raises(WorkflowError) as e:
        parse(text)
    assert any(fragment in p for p in e.value.problems), e.value.problems


def test_good_workflow_parses():
    wf = parse(GOOD)
    assert wf.start == "read"
    assert set(wf.steps) == {"read", "analyze", "check", "done", "failed"}
    assert wf.budget["usd"] == 1.5


def test_unknown_kind_rejected():
    fails(GOOD.replace("kind: gate", "kind: shell"), "kind")


def test_dangling_edge_rejected():
    fails(GOOD.replace("next: done", "next: nowhere"), "unknown step 'nowhere'")


def test_cycle_rejected():
    fails(GOOD.replace("on_fail: failed", "on_fail: analyze"), "cycle")


def test_tool_must_be_granted():
    fails(GOOD.replace("tools: [memory_search], ", ""), "not in its `tools` grant")


def test_unknown_field_rejected():
    fails(GOOD.replace("{id: done, kind: return}", "{id: done, kind: return, shell: rm}"),
          "Additional properties")


def test_unreachable_step_rejected():
    fails(GOOD + "  - {id: orphan, kind: return}\n", "unreachable")


def test_memory_lens_only_on_llm_or_tool():
    fails(GOOD.replace("kind: gate, check", "kind: gate, memory: lens, check"), "memory lens")


def test_on_fail_only_on_gate():
    fails(GOOD.replace("next: check}", "next: check, on_fail: failed}"), "only gate steps")


def test_duplicate_id_rejected():
    fails(GOOD + "  - {id: done, kind: return}\n", "duplicate step id")


def test_bad_yaml_rejected():
    fails("name: [", "not valid YAML")


CODE = """
name: calc
start: calc
steps:
  - {id: calc, kind: code, script: "result = {'n': 1}", reads: [], next: done}
  - {id: done, kind: return, reads: [calc]}
"""


def test_code_step_parses():
    assert parse(CODE).steps["calc"].script == "result = {'n': 1}"


def test_code_step_needs_a_script():
    fails(CODE.replace("script: \"result = {'n': 1}\", ", ""), "needs `script`")


def test_code_step_gets_no_memory_or_tools():
    fails(CODE.replace("reads: [],", "memory: lens,"), "no tools and no memory")
    fails(CODE.replace("reads: [],", "tools: [memory_search],"), "no tools and no memory")


def test_script_only_on_code_steps():
    fails(GOOD.replace("{id: done, kind: return}", "{id: done, kind: return, script: x}"), "only code steps")


PROP = """
name: remember
start: a
steps:
  - {id: a, kind: llm, prompt: x, next: b}
  - {id: b, kind: llm, prompt: y, next: done}
  - {id: done, kind: return, reads: [a, b], propose: b}
"""


def test_propose_parses():
    assert parse(PROP).steps["done"].propose == "b"


def test_propose_must_be_on_a_return_step():
    fails(PROP.replace("next: b}", "next: b, propose: b}"), "only return steps")


def test_propose_must_name_an_llm_step():
    fails(PROP.replace("propose: b", "propose: done"), "must name an llm step")


def test_propose_step_must_be_read():
    fails(PROP.replace("reads: [a, b]", "reads: [a]"), "also be in `reads`")


WEB = """
name: research
start: web
steps:
  - {id: web, kind: tool, tool: web_search, tools: [web_search], prompt: "saas renewal trends 2026", next: read}
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], memory: lens, prompt: sales, next: analyze}
  - {id: analyze, kind: llm, prompt: Compare, reads: [web, read], next: done}
  - {id: done, kind: return, reads: [analyze]}
"""


def test_public_research_then_private_analysis_is_allowed():
    assert parse(WEB).steps["web"].tool == "web_search"


def test_web_step_cannot_read_the_memory_lens():
    fails(WEB.replace("tools: [web_search], prompt", "tools: [web_search], memory: lens, prompt"), "public and cannot read the memory lens")


def test_web_step_cannot_read_a_private_step():
    text = """
name: leak
start: read
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], memory: lens, prompt: sales, next: q}
  - {id: q, kind: llm, prompt: "write a search query", reads: [read], next: web}
  - {id: web, kind: tool, tool: web_search, tools: [web_search], reads: [q], next: done}
  - {id: done, kind: return, reads: [web]}
"""
    fails(text, "holds private data")


def test_privacy_taint_is_transitive():
    text = """
name: leak2
start: read
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], memory: lens, prompt: sales, next: a}
  - {id: a, kind: llm, prompt: x, reads: [read], next: b}
  - {id: b, kind: llm, prompt: y, reads: [a], next: web}
  - {id: web, kind: tool, tool: web_search, tools: [web_search], reads: [b], next: done}
  - {id: done, kind: return, reads: [web]}
"""
    fails(text, "holds private data")


def test_web_query_may_come_from_a_public_llm_step():
    text = """
name: ok
start: plan
steps:
  - {id: plan, kind: llm, prompt: "reply with a search query about SaaS renewals", next: web}
  - {id: web, kind: tool, tool: web_search, tools: [web_search], reads: [plan], next: done}
  - {id: done, kind: return, reads: [web]}
"""
    assert parse(text).steps["web"].reads == ("plan",)


CHAT = """
name: chatty
start: read
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], memory: lens, prompt: "{task}", next: answer}
  - {id: answer, kind: llm, prompt: Answer the question, reads: [task, history, read], next: done}
  - {id: done, kind: return, reads: [answer]}
"""


def test_task_and_history_are_built_in_inputs():
    wf = parse(CHAT)
    assert wf.steps["answer"].reads == ("task", "history", "read")


def test_reading_something_that_does_not_exist_is_an_error():
    fails(CHAT.replace("reads: [task, history, read]", "reads: [task, ghost]"), "neither a step nor one of")


def test_a_step_cannot_read_itself_or_a_step_that_runs_later():
    fails(CHAT.replace("reads: [task, history, read]", "reads: [answer]"), "cannot read itself")
    later = """
name: later
start: a
steps:
  - {id: a, kind: llm, prompt: p, reads: [b], next: b}
  - {id: b, kind: llm, prompt: q, next: done}
  - {id: done, kind: return, reads: [b]}
"""
    fails(later, "never runs before it")


def test_the_task_placeholder_is_only_for_tool_prompts():
    fails(CHAT.replace("prompt: Answer the question", "prompt: \"Answer {task}\""), "works only in a tool step")


def test_a_web_step_may_read_the_task_but_never_the_history():
    ok = """
name: web
start: w
steps:
  - {id: w, kind: tool, tool: web_search, tools: [web_search], prompt: "{task}", reads: [task], next: a}
  - {id: a, kind: llm, prompt: Summarize, reads: [w], next: done}
  - {id: done, kind: return, reads: [a]}
"""
    assert parse(ok).steps["w"].reads == ("task",)
    fails(ok.replace("reads: [task], next: a", "reads: [history], next: a"), "holds private data")


def test_a_step_that_reads_the_history_is_private_so_it_cannot_feed_a_web_step():
    text = """
name: leak
start: a
steps:
  - {id: a, kind: llm, prompt: p, reads: [history], next: w}
  - {id: w, kind: tool, tool: web_search, tools: [web_search], reads: [a], next: done}
  - {id: done, kind: return, reads: [w]}
"""
    fails(text, "holds private data")


def test_memory_tool_counts_as_private_even_without_the_lens_declaration():
    # without this the step looked public: its records could reach a web query through an llm step
    sneaky = """
name: sneaky
start: read
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], prompt: "{task}", next: mix}
  - {id: mix, kind: llm, reads: [read], prompt: "make a query", next: web}
  - {id: web, kind: tool, tool: web_search, tools: [web_search], reads: [mix], next: done}
  - {id: done, kind: return, reads: [web]}
"""
    fails(sneaky, "holds private data")
    fails(sneaky.replace("memory_search", "memory_read"), "holds private data")


def test_the_approval_card_reports_memory_use_even_when_the_step_did_not_declare_it():
    from bridge.pack.caps import capabilities
    wf = parse("""
name: quiet
start: read
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], prompt: "{task}", next: done}
  - {id: done, kind: return, reads: [read]}
""")
    assert capabilities(wf)["memory_lens"] is True
