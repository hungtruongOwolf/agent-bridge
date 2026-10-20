"""Workflow program: a closed language of typed steps, validated before anything runs.

v1 slice of the design (design-harness-workflow.md): kinds llm, tool, code, gate, return.
Rules enforced here: unique step ids, known kinds, every edge points at a real step,
no cycles (loops are a later step kind), every path ends in `return`, and every step
declares the capabilities it needs (nothing is implicit).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml
from jsonschema import Draft202012Validator

KINDS = ("llm", "tool", "code", "gate", "return")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "start", "steps"],
    "properties": {
        "name": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,63}$"},
        "start": {"type": "string"},
        "budget": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "usd": {"type": "number", "exclusiveMinimum": 0},
                "tokens": {"type": "integer", "minimum": 1},
            },
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "kind"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
                    "kind": {"enum": list(KINDS)},
                    "next": {"type": "string"},
                    "on_fail": {"type": "string"},
                    "prompt": {"type": "string"},
                    "tool": {"type": "string"},
                    "check": {"type": "string"},
                    "script": {"type": "string"},
                    "propose": {"type": "string"},
                    "reads": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "tools": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "memory": {"enum": ["none", "lens"]},
                    "type": {"type": "string"},
                },
            },
        },
    },
}


class WorkflowError(ValueError):
    """The workflow program is invalid. `problems` lists every reason."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Step:
    id: str
    kind: str
    next: str | None = None
    on_fail: str | None = None
    prompt: str | None = None
    tool: str | None = None
    check: str | None = None
    script: str | None = None  # python source for a `code` step; runs in a Cell
    reads: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    memory: str = "none"
    type: str | None = None  # record type a memory tool asks about
    propose: str | None = None  # `return` only: llm step whose output holds memory proposals


@dataclass(frozen=True)
class Workflow:
    name: str
    start: str
    steps: dict[str, Step]
    budget: dict = field(default_factory=dict)


def parse(text: str) -> Workflow:
    """Parse YAML/JSON text into a validated Workflow, or raise WorkflowError."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise WorkflowError([f"not valid YAML: {e}"]) from e
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise WorkflowError([f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors])

    problems: list[str] = []
    steps: dict[str, Step] = {}
    for raw in data["steps"]:
        if raw["id"] in steps:
            problems.append(f"duplicate step id {raw['id']!r}")
            continue
        steps[raw["id"]] = Step(
            id=raw["id"], kind=raw["kind"], next=raw.get("next"), on_fail=raw.get("on_fail"),
            prompt=raw.get("prompt"), tool=raw.get("tool"), check=raw.get("check"), script=raw.get("script"),
            reads=tuple(raw.get("reads", ())), tools=tuple(raw.get("tools", ())),
            memory=raw.get("memory", "none"), type=raw.get("type"), propose=raw.get("propose"),
        )
    if data["start"] not in steps:
        problems.append(f"start {data['start']!r} is not a step")

    for s in steps.values():
        for label, target in (("next", s.next), ("on_fail", s.on_fail)):
            if target is not None and target not in steps:
                problems.append(f"step {s.id!r}: {label} points at unknown step {target!r}")
        if s.kind == "return":
            if s.next or s.on_fail:
                problems.append(f"step {s.id!r}: return must not have next/on_fail")
        elif not s.next:
            problems.append(f"step {s.id!r}: {s.kind} step needs `next`")
        if s.on_fail and s.kind != "gate":
            problems.append(f"step {s.id!r}: only gate steps may have on_fail")
        if s.kind == "tool" and not s.tool:
            problems.append(f"step {s.id!r}: tool step needs `tool`")
        if s.kind == "tool" and s.tool and s.tool not in s.tools:
            problems.append(f"step {s.id!r}: tool {s.tool!r} is not in its `tools` grant")
        if s.kind == "llm" and not s.prompt:
            problems.append(f"step {s.id!r}: llm step needs `prompt`")
        if s.propose:
            if s.kind != "return":
                problems.append(f"step {s.id!r}: only return steps may `propose`")
            elif s.propose not in steps or steps[s.propose].kind != "llm":
                problems.append(f"step {s.id!r}: propose must name an llm step")
            elif s.propose not in s.reads:
                problems.append(f"step {s.id!r}: propose step must also be in `reads`")
        if s.kind == "code":
            if not s.script:
                problems.append(f"step {s.id!r}: code step needs `script`")
            if s.tools or s.memory != "none":
                problems.append(f"step {s.id!r}: code steps get no tools and no memory, only declared reads")
        elif s.script:
            problems.append(f"step {s.id!r}: only code steps may have `script`")
        if s.kind == "gate" and not s.check:
            problems.append(f"step {s.id!r}: gate step needs `check`")
        if s.memory == "lens" and s.kind not in ("llm", "tool"):
            problems.append(f"step {s.id!r}: only llm/tool steps may read the memory lens")

    if not problems:
        problems += _graph_problems(steps, data["start"])
    if problems:
        raise WorkflowError(problems)
    return Workflow(name=data["name"], start=data["start"], steps=steps, budget=data.get("budget", {}))


def _edges(s: Step) -> list[str]:
    return [t for t in (s.next, s.on_fail) if t]


def _graph_problems(steps: dict[str, Step], start: str) -> list[str]:
    problems: list[str] = []
    state: dict[str, int] = {}  # 1 = on the current path, 2 = finished

    def visit(sid: str) -> None:
        if state.get(sid) == 2:
            return
        if state.get(sid) == 1:
            problems.append(f"cycle through step {sid!r} (loops are not available yet)")
            return
        state[sid] = 1
        for t in _edges(steps[sid]):
            visit(t)
        state[sid] = 2

    visit(start)
    for sid in steps:
        if sid not in state:
            problems.append(f"step {sid!r} is unreachable from start")

    # in an acyclic graph, every step must reach a return step
    reaches = {sid for sid, s in steps.items() if s.kind == "return"}
    changed = True
    while changed:
        changed = False
        for sid, s in steps.items():
            if sid not in reaches and any(t in reaches for t in _edges(s)):
                reaches.add(sid)
                changed = True
    for sid in steps:
        if sid in state and sid not in reaches:
            problems.append(f"step {sid!r} cannot reach a return step")
    return problems
