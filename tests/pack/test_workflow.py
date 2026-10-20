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
