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

from ..guard.result_guard import ResultGuard, longest_shared_run
from ..memory.broker import MemoryBroker, Verdict
from ..pack.workflow import Step, Workflow
from .journal import Journal
from .limits import MAX_TASK_CHARS, clean_history


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
    proposals: list = field(default_factory=list)  # raw, unvalidated memory proposals


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
        web=None,
        task: str = "",
        history: list | None = None,
    ):
        self.wf = workflow
        self.model = model
        self.broker = broker
        self.guard = guard
        self.journal = journal or Journal()
        self.checks = checks or {}
        self.max_steps = max_steps
        self.web = web  # object with search(query) -> list[dict]; the only network a pack can use
        self.cell = cell  # runs `code` steps; needs run(script, inputs) -> CellResult
        if len(task or "") > MAX_TASK_CHARS:
            raise ValueError(f"the message is longer than {MAX_TASK_CHARS} characters")
        self.task = (task or "").strip()  # what the user asked this turn
        self.history = clean_history(history)  # earlier turns of the same conversation
        self.tokens = 0
        self.usd = 0.0
        self.violations: list[dict] = []  # sandbox probes seen inside Cells: {kind, detail}

    def run(self) -> RunResult:
        j = self.journal
        j.append("run_started", {"workflow": self.wf.name, "manifest": self.broker.manifest,
                                 "task_chars": len(self.task), "history_turns": len(self.history)})
        outputs: dict[str, Any] = {"task": self.task, "history": self.history}  # the two built-in inputs
        sid: str | None = self.wf.start
        executed = 0
        while sid is not None:
            executed += 1
            if executed > self.max_steps:
                return self._finish(Outcome.FAILED_PACK, reasons=["step limit reached"])
            step = self.wf.steps[sid]
            if self._over_budget() and step.kind in ("llm",):
                return self._finish(Outcome.PARTIAL_BUDGET, reasons=["budget exhausted"])
            started = {"step": sid, "kind": step.kind}
            if step.kind == "tool":
                started["tool"] = step.tool  # which door this step uses: memory or web
            j.append("step_started", started)
            events_before = len(self.broker.events)
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
                    out = self._tool(step, inputs)
            except _Killed as k:
                return self._finish(Outcome.KILLED, reasons=[k.reason])
            except _InfraError as e:
                return self._finish(Outcome.FAILED_INFRA, reasons=[str(e)])
            except _StepError as e:
                return self._finish(Outcome.FAILED_PACK, reasons=[str(e)])
            outputs[sid] = out
            commit = {"step": sid}
            if step.kind == "tool" and isinstance(out, list):
                # which of YOUR records this step actually received, and what the broker refused meanwhile
                commit["records"] = [r["id"] for r in out if isinstance(r, dict) and r.get("id") in self.broker.manifest]
                commit["blocked"] = [ev.kind for ev in self.broker.events[events_before:]]
                if step.tool == "web_search":
                    commit["results"] = len(out)
            j.append("step_committed", commit)
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
        try:
            res = self.cell.run(step.script or "", inputs)
        except Exception as e:  # the container engine itself failed
            raise _InfraError(f"the sealed room could not start: {type(e).__name__}") from e
        self.journal.append("cell_run", {"step": step.id, "ok": res.ok, "timed_out": res.timed_out,
                                         "attempts": res.attempts})
        kinds = {"network": "SANDBOX_NETWORK", "dns": "SANDBOX_NETWORK", "process": "SANDBOX_PROCESS",
                 "write": "SANDBOX_WRITE"}
        for a in res.attempts:
            self.violations.append({"kind": kinds.get(a.split(":", 1)[0], "SANDBOX_PROBE"), "detail": a})
        if any(v["kind"] in ("SANDBOX_NETWORK", "SANDBOX_PROCESS") for v in self.violations):
            # trying to reach the network or start a process from a sealed cell is deterministic evidence
            self.journal.append("incident", {"step": step.id, "evidence": "sandbox-probe"})
            raise _Killed("sandbox probe: " + self.violations[0]["detail"])
        if not res.ok:
            raise _StepError(f"code step {step.id!r}: {res.error}")
        return res.value

    def _tool(self, step: Step, inputs: dict[str, Any]) -> Any:
        name = step.tool or ""
        if name not in step.tools:
            raise _StepError(f"tool {name!r} not granted to step {step.id!r}")
        if name == "web_search":
            return self._web(step, inputs)
        query = (step.prompt or "").replace("{task}", self.task)
        if name == "memory_search":
            res = self.broker.search(query, type=step.type)
        elif name == "memory_read":
            res = self.broker.read(query)
        else:
            raise _StepError(f"unknown tool {name!r}")
        if res.verdict is Verdict.KILL:
            self.journal.append("incident", {"step": step.id, "events": [e.kind for e in self.broker.events]})
            raise _Killed(f"broker kill: {self.broker.events[-1].kind}")
        return res.records

    # -- end of run ---------------------------------------------------------------------------
    def _web(self, step: Step, inputs: dict[str, Any]) -> Any:
        if self.web is None:
            raise _StepError("no web search is configured")
        query = (step.prompt or "").replace("{task}", self.task)
        if not query and step.reads:
            src = inputs.get(step.reads[0])
            query = src.get("query", "") if isinstance(src, dict) else ""
        if not isinstance(query, str) or not query.strip():
            raise _StepError("web_search needs a query")
        # defence in depth: whatever the scope rules allow, a query may not carry the user's records out
        for text in self.broker.lens_texts:
            if longest_shared_run(query, text) > 25:
                self.violations.append({"kind": "WEB_QUERY_LEAK", "detail": "query repeats text from a staged record"})
                self.journal.append("incident", {"step": step.id, "evidence": "web-query-leak"})
                raise _StepError("web query blocked: it repeats text from your records")
        try:
            results = self.web.search(query)
        except Exception as e:  # the search service failed: infrastructure, not the pack
            self.journal.append("model_error", {"step": step.id, "type": type(e).__name__})
            raise _InfraError(f"web search failed: {type(e).__name__}") from e
        self.journal.append("web_search", {"step": step.id, "query": query, "results": len(results)})
        return results

    def _deliver(self, step: Step, inputs: dict[str, Any]) -> RunResult:
        result = inputs[step.reads[0]] if step.reads and step.reads[0] in inputs else {}
        lens_texts = self.broker.lens_texts
        report = self.guard.check(result, canaries=self.broker.canary_values, lens_texts=lens_texts)
        if report.verdict is Verdict.KILL:
            self.journal.append("incident", {"step": step.id, "evidence": report.evidence})
            return self._finish(Outcome.KILLED, reasons=report.reasons)
        if report.verdict is Verdict.DENY:
            return self._finish(Outcome.FAILED_PACK, reasons=report.reasons)
        proposals = []
        if step.propose and isinstance(inputs.get(step.propose), dict):
            proposals = inputs[step.propose].get("proposals") or []
            scan = self.guard.scan(proposals, canaries=self.broker.canary_values, lens_texts=lens_texts)
            if scan.verdict is Verdict.KILL:
                self.journal.append("incident", {"step": step.id, "evidence": "canary-in-proposal"})
                return self._finish(Outcome.KILLED, reasons=["canary value in a memory proposal"])
            if scan.verdict is Verdict.DENY:
                proposals = []  # a proposal that copies records is dropped; the result itself is still fine
        return self._finish(Outcome.COMPLETE, result=result, proposals=proposals)

    def _over_budget(self) -> bool:
        b = self.wf.budget
        return bool((b.get("tokens") and self.tokens >= b["tokens"]) or (b.get("usd") and self.usd >= b["usd"]))

    def _finish(self, outcome: Outcome, *, result: Any = None, reasons: list[str] | None = None,
                proposals: list | None = None) -> RunResult:
        self.journal.append("run_finished", {"outcome": outcome.value, "reasons": reasons or []})
        return RunResult(outcome, result, reasons or [], self.tokens, self.usd, proposals or [])


class _Killed(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _StepError(Exception):
    pass


class _InfraError(Exception):
    pass
