import pytest

from bridge.pack.caps import Version, capabilities, widening
from bridge.pack.workflow import parse

BASE = """
name: base
start: read
budget: {tokens: 5000}
steps:
  - {id: read, kind: tool, tool: memory_search, tools: [memory_search], memory: lens, prompt: sales, next: a}
  - {id: a, kind: llm, prompt: "Summarize", reads: [read], next: done}
  - {id: done, kind: return, reads: [a]}
"""


def caps(text):
    return capabilities(parse(text))


def test_capabilities_of_a_plain_pack():
    c = caps(BASE)
    assert c["tools"] == ["memory_search"] and c["memory_lens"] and not c["web"] and not c["code"]
    assert c["budget_tokens"] == 5000


def test_prompt_changes_never_widen():
    assert widening(caps(BASE), caps(BASE.replace("Summarize", "Summarize in two sentences, naming accounts"))) == []


def test_narrowing_is_fine():
    assert widening(caps(BASE), caps(BASE.replace("tokens: 5000", "tokens: 3000"))) == []
    assert widening(caps(BASE), caps(BASE.replace("budget: {tokens: 5000}\n", ""))) != []  # removing a limit widens


def test_new_tool_and_budget_raise_widen():
    more = BASE.replace("tools: [memory_search]", "tools: [memory_search, memory_read]").replace("tokens: 5000", "tokens: 9000")
    reasons = widening(caps(BASE), caps(more))
    assert "new tool memory_read" in reasons and any("raised from 5000 to 9000" in r for r in reasons)


def test_gaining_web_or_code_widens():
    web = BASE.replace("start: read", "start: w").replace("steps:\n", "steps:\n  - {id: w, kind: tool, tool: web_search, tools: [web_search], prompt: q, next: read}\n")
    assert "now uses web" in widening(caps(BASE), caps(web))


def test_asking_for_a_new_record_type_widens():
    typed = BASE.replace("memory: lens, prompt: sales", "memory: lens, type: finance, prompt: sales")
    assert "now asks about record type finance" in widening(caps(BASE), caps(typed))


def test_version_parse_and_order():
    assert Version.parse("1.2.3") < Version.parse("1.10.0") < Version.parse("2.0.0")
    with pytest.raises(ValueError):
        Version.parse("1.2")
    with pytest.raises(ValueError):
        Version.parse("v1.2.3")
