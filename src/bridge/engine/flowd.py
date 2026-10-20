"""flowd: runs a validated Workflow step by step.

The pack supplies the program; this engine is trusted platform code. Rules it enforces:
  - a step sees only the outputs it declares in `reads` (no shared blackboard);
  - a step may only call tools in its own `tools` grant;
  - memory is reached only through the MemoryBroker, never directly;
  - `code` steps run only inside a Cell (no network, only their declared reads);
  - every step start and commit is journaled;
  - when the budget is exhausted the run ends as PARTIAL with no further model call;
  - the final result goes through the Result Guard; a canary hit or a broker kill ends
    the run as KILLED and nothing is delivered.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol

from ..guard.result_guard import ResultGuard
from ..memory.broker import MemoryBroker, Verdict
from ..pack.workflow import Step, Workflow
from .journal import Journal


class Outcome(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_BUDGET = "PARTIAL_BUDGET"
    FAILED_PACK = "FAILED_PACK"  # bad output, gate chain ended in a failing return, step error
    FAILED_INFRA = "FAILED_INFRA"  # the model call failed: not the pack's fault, nobody is struck
    KILLED = "KILLED"


@dataclass
class ModelReply:
    content: Any  # dict for structured steps, str otherwise
    tokens: int = 0
    usd: float = 0.0


class Model(Protocol):
    def complete(self, prompt: str, inputs: dict[str, Any]) -> ModelReply: ...


@dataclass
class RunResult:
    outcome: Outcome
    result: Any = None
    reasons: list[str] = field(default_factory=list)
    tokens: int = 0
    usd: float = 0.0


class Engine:
    def __init__(
        self,
        workflow: Workflow,
        *,
        model: Model,
        broker: MemoryBroker,
        guard: ResultGuard,
        journal: Journal | None = None,
        checks: dict[str, Callable[[Any], bool]] | None = None,
        max_steps: int = 100,
        cell=None,
    ):
        self.wf = workflow
        self.model = model
        self.broker = broker
        self.guard = guard
        self.journal = journal or Journal()
        self.checks = checks or {}
        self.max_steps = max_steps
        self.cell = cell  # runs `code` steps; needs run(script, inputs) -> CellResult
        self.tokens = 0
        self.usd = 0.0

    def run(self) -> RunResult:
        j = self.journal
        j.append("run_started", {"workflow": self.wf.name, "manifest": self.broker.manifest})
        outputs: dict[str, Any] = {}
        sid: str | None = self.wf.start
        executed = 0
        while sid is not None:
            executed += 1
            if executed > self.max_steps:
                return self._finish(Outcome.FAILED_PACK, reasons=["step limit reached"])
            step = self.wf.steps[sid]
            if self._over_budget() and step.kind in ("llm",):
                return self._finish(Outcome.PARTIAL_BUDGET, reasons=["budget exhausted"])
            j.append("step_started", {"step": sid, "kind": step.kind})
            inputs = {r: outputs[r] for r in step.reads if r in outputs}

            if step.kind == "return":
                return self._deliver(step, inputs)

            if step.kind == "gate":
                check = self.checks.get(step.check or "")
                if check is None:
                    return self._finish(Outcome.FAILED_PACK, reasons=[f"unknown check {step.check!r}"])
                ok = bool(check(inputs))
                j.append("step_committed", {"step": sid, "passed": ok})
                sid = step.next if ok else step.on_fail
                continue

            try:
                if step.kind == "llm":
                    out = self._llm(step, inputs)
                elif step.kind == "code":
                    out = self._code(step, inputs)
                else:
                    out = self._tool(step)
            except _Killed as k:
                return self._finish(Outcome.KILLED, reasons=[k.reason])
            except _InfraError as e:
                return self._finish(Outcome.FAILED_INFRA, reasons=[str(e)])
            except _StepError as e:
                return self._finish(Outcome.FAILED_PACK, reasons=[str(e)])
            outputs[sid] = out
            j.append("step_committed", {"step": sid})
            sid = step.next
        return self._finish(Outcome.FAILED_PACK, reasons=["workflow ended without return"])

    # -- step kinds ---------------------------------------------------------------------------
    def _llm(self, step: Step, inputs: dict[str, Any]) -> Any:
        try:
            reply = self.model.complete(step.prompt or "", inputs)
        except Exception as e:  # any model/network failure is infrastructure, never the pack's fault
            self.journal.append("model_error", {"step": step.id, "type": type(e).__name__})
            raise _InfraError(f"model call failed: {type(e).__name__}") from e
        self.tokens += reply.tokens
        self.usd += reply.usd
        self.journal.append("model_call", {"step": step.id, "tokens": reply.tokens, "usd": reply.usd})
        return reply.content

    def _code(self, step: Step, inputs: dict[str, Any]) -> Any:
        if self.cell is None:
            raise _StepError("no Cell available to run code steps")
        res = self.cell.run(step.script or "", inputs)
        self.journal.append("cell_run", {"step": step.id, "ok": res.ok, "timed_out": res.timed_out})
        if not res.ok:
            raise _StepError(f"code step {step.id!r}: {res.error}")
        return res.value

    def _tool(self, step: Step) -> Any:
        name = step.tool or ""
        if name not in step.tools:
            raise _StepError(f"tool {name!r} not granted to step {step.id!r}")
        if name == "memory_search":
            res = self.broker.search(step.prompt or "", type=step.type)
        elif name == "memory_read":
            res = self.broker.read(step.prompt or "")
        else:
            raise _StepError(f"unknown tool {name!r}")
        if res.verdict is Verdict.KILL:
            self.journal.append("incident", {"step": step.id, "events": [e.kind for e in self.broker.events]})
            raise _Killed(f"broker kill: {self.broker.events[-1].kind}")
        return res.records

    # -- end of run ---------------------------------------------------------------------------
    def _deliver(self, step: Step, inputs: dict[str, Any]) -> RunResult:
        result = inputs[step.reads[0]] if step.reads and step.reads[0] in inputs else {}
        lens_texts = self.broker.lens_texts
        report = self.guard.check(result, canaries=self.broker.canary_values, lens_texts=lens_texts)
        if report.verdict is Verdict.KILL:
            self.journal.append("incident", {"step": step.id, "evidence": report.evidence})
            return self._finish(Outcome.KILLED, reasons=report.reasons)
        if report.verdict is Verdict.DENY:
            return self._finish(Outcome.FAILED_PACK, reasons=report.reasons)
        return self._finish(Outcome.COMPLETE, result=result)

    def _over_budget(self) -> bool:
        b = self.wf.budget
        return bool((b.get("tokens") and self.tokens >= b["tokens"]) or (b.get("usd") and self.usd >= b["usd"]))

    def _finish(self, outcome: Outcome, *, result: Any = None, reasons: list[str] | None = None) -> RunResult:
        self.journal.append("run_finished", {"outcome": outcome.value, "reasons": reasons or []})
        return RunResult(outcome, result, reasons or [], self.tokens, self.usd)


class _Killed(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _StepError(Exception):
    pass


class _InfraError(Exception):
    pass
