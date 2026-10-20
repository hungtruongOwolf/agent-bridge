# 01. Workflow engines and patterns: what makes an agent harness a reliable automated workflow

Date: 2026-10-07. Scope: external facts from primary docs (fetched this run); everything about agent-bridge is our own proposal. Items not read from a primary source are marked UNVERIFIED.

## Summary

The owner's feedback is right: architecture-v2 section 5 defines the harness as "prompts, skills, planner/worker/returner policies, tool config" with a fixed three-phase `phases:` block. That is a static prompt bundle plus three hard-coded stages. It has no steps, branches, loops, verification gates, checkpoints, retries or budgets, so it cannot run a hard, long task reliably.

Across the sources, the same small set of properties separates a reliable workflow from a long prompt:

1. Control flow lives in code or data, not in the model's head (Anthropic: workflows are "predefined code paths"; agents are LLM-directed). The model is used inside steps; the engine owns sequencing, loops and stopping.
2. Every step has typed input and output, so the engine can validate, gate and memoize it.
3. State is external and durable (checkpoint per step), so a run can resume after a crash, a context reset or a human wait without redoing finished work.
4. Retries, timeouts and budgets are declared per step and enforced by the engine, not requested in a prompt.
5. Verification is a first-class step (gate/evaluator), separate from the producer, with an explicit loop budget.
6. Human checkpoints are a step type that suspends the run durably (not a blocking prompt).
7. Long tasks need context hygiene: fresh context per step or subtask, small structured hand-offs, progress files, compaction.

Recommendation in one line: make a pack's harness a **declarative workflow graph (YAML, validated by JSON Schema, executed by a small durable engine we own)** whose node types are `agent`, `tool`, `gate`, `branch`, `loop`, `map`, `human`, `subflow`; permissions stay in the manifest and are enforced by the sidecar below the engine, so the workflow DSL cannot widen them. Escape hatch: tier-1 packs may supply code steps that run only inside the Cell.

## Key facts with sources

### A. Anthropic patterns and long-running guidance

- Workflows vs agents: workflows are "systems where LLMs and tools are orchestrated through predefined code paths"; agents are "systems where LLMs dynamically direct their own processes and tool usage". Five workflow patterns: prompt chaining (with "programmatic validation gates at intermediate checkpoints"), routing, parallelization (sectioning and voting), orchestrator-workers (subtasks "determined by the orchestrator based on the specific input"), evaluator-optimizer ("clear evaluation criteria" and measurable value from iteration). Autonomous agents should use "stopping conditions (maximum iterations)", pause for human feedback "at checkpoints or when encountering blockers", and get ground truth from tool results at each step. Source: https://www.anthropic.com/engineering/building-effective-agents
- Long-running harness: a first Initializer session sets up the environment (feature list JSON of 200+ items all initially "failing", `claude-progress.txt`, `init.sh`, git); every later Coding session makes incremental progress and leaves structured updates. Failure modes and fixes listed by Anthropic: premature completion -> structured feature checklist; undocumented progress -> git commits; incomplete testing -> browser automation checks; environment confusion -> init script plus progress log. Guardrail wording: "It is unacceptable to remove or edit tests". Source: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Multi-agent research system: orchestrator-worker; Opus lead plus Sonnet subagents beat single-agent Opus by 90.2% on their internal eval; token use alone explained 80% of variance in a browsing benchmark; multi-agent used about 15x chat tokens, so only for high-value tasks; effort-scaling rules embedded in prompts; resumable checkpoints; rainbow deployments for in-flight agents; LLM-as-judge plus human review. Source: https://www.anthropic.com/engineering/built-multi-agent-research-system
- Context engineering: compaction (summarize and reinitiate), structured note-taking outside the window, sub-agents returning "a condensed, distilled summary (often 1,000-2,000 tokens)", just-in-time retrieval via lightweight identifiers, and context rot (recall degrades as tokens grow). Source: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

### B. Durable-execution engines

- Temporal: workflow code is replayed against the Event History; "the Workflow Execution picks up where the last recorded event occurred"; determinism is required of workflow code; side effects belong in Activities; Signals deliver external input. Source: https://docs.temporal.io/workflow-execution
- Temporal retry policy defaults: initial interval 1s, backoff coefficient 2.0, max interval 100x initial, max attempts unlimited, plus non-retryable error types. Source: https://docs.temporal.io/encyclopedia/retry-policies
- Temporal activity timeouts: Schedule-To-Start, Start-To-Close (strongly recommended), Schedule-To-Close (covers retries), plus Heartbeat timeout to detect silent worker failure. Activities "should be designed to be safely executed multiple times"; long activities "should either complete within a few minutes or it should heartbeat". Sources: https://docs.temporal.io/encyclopedia/detecting-activity-failures , https://docs.temporal.io/activity-definition
- Inngest: `step.run()` results are memoized; on replay "the SDK skips the callback and returns the saved result"; "a retry repeats only the step that failed"; `step.waitForEvent()` pauses without consuming compute and returns null on timeout. Sources: https://www.inngest.com/docs/learn/how-functions-are-executed
- LangGraph: checkpointer persists a state snapshot per step per `thread_id`, enabling "human-in-the-loop, time travel, and fault tolerance"; checkpoints accumulate and cost latency. Source: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph interrupts: `interrupt()` plus `Command(resume=...)` needs a checkpointer; on resume the whole node restarts from the top, so "side effects called before [interrupt] should (ideally) be idempotent". Source: https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph graph model: shared state with per-key reducers (default replace, e.g. add to accumulate), conditional edges, `Send` for map-reduce fan-out, `Command(update, goto)`, recursion limit as a cap on super-steps (default 1000 in v1.0.6). Source: https://docs.langchain.com/oss/python/langgraph/graph-api
- Mastra: typed steps (`inputSchema`/`outputSchema`), `stateSchema` with `setState` persisted across suspend/resume, statuses `suspended`, `paused`, `failed`, `success`, `tripwire`, `restart()` from last active step. Control-flow detail (branch, parallel, dountil, foreach) was NOT in the fetched page: UNVERIFIED beyond `.then()`. Source: https://mastra.ai/docs/workflows/overview
- OpenAI Agents SDK: primitives agents/handoffs/guardrails plus sessions and tracing; `max_turns` with `MaxTurnsExceeded` and error handlers (`max_turns`, `model_refusal`, `invalid_final_output`) returning controlled fallbacks; `RunState` to resume paused runs; input guardrails run in parallel by default or blocking, only for the first agent; output guardrails only for the agent producing final output; tool guardrails wrap every call; tripwires halt the run. Sources: https://openai.github.io/openai-agents-python/running_agents/ , https://openai.github.io/openai-agents-python/guardrails/

### C. Batch/DAG orchestrators

- Argo Workflows: loops via `withItems`, `withParam` (dynamic JSON from earlier step), `withSequence`; `retryStrategy` with `limit`, `retryPolicy` (Always/OnFailure/OnError/OnTransientError), `backoff`, and an `expression` over `lastRetry.exitCode/status/duration/message` that is ANDed with the policy; `onExit` handler always runs and can branch on `workflow.status`. Sources: https://argo-workflows.readthedocs.io/en/latest/walk-through/loops/ , https://argo-workflows.readthedocs.io/en/latest/retries/ , https://argo-workflows.readthedocs.io/en/latest/walk-through/exit-handlers/
- Dagster: asset checks with `blocking=True` mean "if the check fails, the downstream asset won't be materialized" (a gate as a first-class object attached to an output). WARN/ERROR severity details not in the fetched page: UNVERIFIED. Source: https://dagster.io/docs/guides/test/asset-checks
- n8n: error workflow, retry-on-fail, continue-on-error, wait/merge nodes: NOT VERIFIED (docs.n8n.io error-handling pages returned 404 on every path tried). Treat any n8n claim as UNVERIFIED.

### D. Claude Code building blocks (relevant to what a pack may reuse)

- Subagents: markdown with frontmatter (`tools`, `model`, `permissionMode`, `maxTurns` returning partial results, `skills`, `memory`, `hooks`, `isolation: worktree`, `background`); fresh context window with no parent history (forks excepted); nesting up to 3 layers by default, 20 concurrent; resumable by agent ID. Source: https://code.claude.com/docs/en/sub-agents
- Skills: SKILL.md frontmatter (`disable-model-invocation`, `allowed-tools`, `context: fork`); progressive disclosure (descriptions always loaded, body on invoke); after compaction only the first 5,000 tokens per skill and 25,000 total are re-attached. Source: https://code.claude.com/docs/en/skills
- Hooks: events (SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop, PermissionRequest, SessionEnd...), handler types command/http/mcp_tool/prompt/agent; exit code 2 blocks, other non-zero is non-blocking; JSON `decision`/`permissionDecision` with `updatedInput`; Stop hook can block "finishing" (a verification gate at the harness level). Source: https://code.claude.com/docs/en/hooks
- Agent SDK: library exposing the Claude Code loop with hooks, subagents, MCP, permissions, sessions (resume or fork), skills, plugins. Exact options for max turns, max budget and file checkpointing were not in the fetched page: UNVERIFIED. Source: https://code.claude.com/docs/en/agent-sdk/overview
- The "workflow script" style (code-defined control flow with parallel, pipeline, verify): the Anthropic page describing it (linked from the Agent SDK overview as "dynamic workflows in Claude Code") redirected cross-host to claude.dev, which we did not follow; details UNVERIFIED. The style is known to us from this session's own harness (scripts that spawn subagents in parallel, then verify), which is not a primary external source.

## What a declarative agent-workflow DSL needs (derived)

| Need | Evidence | DSL element |
|---|---|---|
| Fixed sequence with checks between | prompt chaining, Dagster blocking checks | `then` edges plus `gate` node |
| Classification into branches | routing, LangGraph conditional edges | `branch` node, `when` expression over typed state |
| Parallel independent work, voting | parallelization, LangGraph `Send`, Argo `withParam` | `map` (dynamic list) and `parallel` (static list) with `max_concurrency`, `join: all/any/quorum` |
| Dynamic decomposition | orchestrator-workers | `plan` agent step emits a typed list; `map` consumes it (bounded fan-out cap) |
| Generate-then-critique loop | evaluator-optimizer, OpenAI max_turns | `loop` with `until` gate, `max_iterations`, and `on_exhausted` policy |
| Verification | evaluator, guardrails, hooks Stop, asset checks | `gate` node: deterministic check first, LLM judge second, always a different context than the producer |
| Human checkpoint | interrupts, `waitForEvent`, suspended status | `human` node: suspends durably, has timeout and default action |
| Shared state | LangGraph reducers, Mastra stateSchema | typed `state` blackboard with per-key reducers, plus an artifacts directory |
| Checkpoint/resume | Temporal replay, Inngest memoization, LangGraph checkpointer | per-step journal, memoized outputs, resume from last incomplete step |
| Idempotency | LangGraph interrupt rule, Temporal activities | step `idempotency_key`; side-effecting steps declare `effects` and run at most once per key |
| Retries | Temporal, Argo | `retry: {max, backoff, retry_on, non_retryable}` per step |
| Timeouts | Temporal four timeouts, heartbeat | `timeout` per step plus `heartbeat` for long agent steps |
| Budgets | LangGraph recursion limit, max_turns, 15x token cost | `budget` at run, scope and step: tokens, USD, wall time, steps, iterations |
| Structured outputs | Mastra schemas, OpenAI final output rules | every step has `output_schema`; invalid output counts as a failure and triggers retry or repair |
| Cleanup and failure path | Argo `onExit` | `on_exit` and per-step `on_fail` edges (compensate, escalate, or abort) |
| Context management | context engineering post, subagents, long-running harness | `context` policy per step: fresh / inherit / summary-only; `handoff` schema size cap; progress file; compaction trigger |

## Fit for agent-bridge

What fits unchanged:
- Manifest-as-request, enforcement below the model. The workflow engine is just another untrusted-pack-controlled piece of logic; permissions stay in the sidecar and Cell. A workflow graph cannot widen tools or network, because each node's effective permission is the intersection (declared AND requester policy AND mode ceiling), same rule as architecture-v2 section 5.2.
- Detectors D8 (phase/tool-sequence violation) and D1-D14 map onto node boundaries: node transitions become the natural place to evaluate sequence policies, which is stronger than today's three phases.
- Eval and Certifier: graph structure makes per-node and per-gate scoring possible (which step failed), which the improvement loop (5.5) can target; optimizer may edit prompts and demos inside nodes, not the graph's permissions or budgets caps.

What must change in v2:
1. `phases: {plan, work, return}` becomes a special case. A pack declares `workflow:` (graph). The three-phase pack is a built-in template (`builtin-plan-work-return`), kept for the simplest packs.
2. Memory access is per node, not per phase: `memory.read` lens narrowing per node (e.g. only the `analyze` node sees the finance lens). This reduces blast radius and gives the Broker an exact node id for read accounting.
3. Persistence of run state must live outside the Cell's disposable tmpfs in the Pull case, but a pack must not get a durable store (4.7). Resolve by making the **engine, journal and checkpoint store requester-owned and in the sidecar/supervisor side**; the pack sees only per-step inputs and returns per-step outputs. Resume then does not depend on pack-writable storage.
4. Budgets and iteration caps are enforced by the engine on the requester side; the pack cannot raise them. Receipts then carry only bucketed cost, consistent with 3.4.
5. Human checkpoints reuse the approval card/phone relay, but are a workflow node; they also solve approval-fatigue by being declared, not ad hoc.

## Recommendation

### 1. Execution model

- **Engine**: a small durable step engine ("bridge-flow") in the supervisor side, written in a single language with the sidecar. Model: event-sourced journal per run (`step_started`, `step_succeeded{output_hash}`, `step_failed{error_class}`, `human_requested`, `human_resolved`, `budget_tick`, `gate_result`), memoized replay like Inngest/Temporal: on resume, completed steps return recorded outputs, only the first incomplete step re-executes. Determinism is not demanded of the graph (it is data, not code), only of the engine's own scheduling; agent steps are treated as non-deterministic activities whose result is recorded once.
- **Why own it rather than adopt Temporal/LangGraph**: the engine must run on a requester laptop (Windows 11 Home/WSL2), inside the trust boundary, with no extra server and no pack-controlled code in the control plane. Temporal needs a server (UNVERIFIED for a laptop-size embedded mode); LangGraph is a Python library whose graphs are code the pack author would supply (tier-1 only). Reuse their concepts, not their runtimes. A LangGraph or Temporal adapter can be a tier-1 runner later.
- **Step types** (all with `input`, `output_schema`, `retry`, `timeout`, `budget`, `context`):
  - `agent`: one bounded LLM loop (max_turns, tools subset, model class); output must validate against schema; returns structured result plus a capped hand-off summary.
  - `tool`: deterministic tool call through the Tool Broker; no LLM.
  - `gate`: ordered checks; first deterministic (schema, regex, file exists, tests pass, citations present), then optional LLM judge in a fresh context with only the artifact and rubric; result `pass | fail | needs_human`; `fail` routes to `on_fail`.
  - `branch`: `when` expressions (a restricted expression language, no code execution) over state.
  - `loop`: body subgraph, `until` (gate or expression), `max_iterations` (required), `stagnation: {no_progress_after: n}`, `on_exhausted: escalate | accept_best | fail`.
  - `map`: fan-out over a state list with `max_items`, `max_concurrency`, per-item isolation context, `join` policy and a reducer.
  - `human`: durable suspend; `prompt_schema`, `timeout`, `on_timeout: deny | default | fail` (default deny for high sensitivity).
  - `subflow`: call another declared workflow (including a certified third-party pack's published sub-workflow later), depth cap.
- **State**: typed blackboard `state` (JSON-schema'd keys with reducers: replace, append, merge, max) plus an `artifacts/` directory of files with content hashes. Steps declare `reads` and `writes` keys; engine rejects undeclared writes. State lives on the supervisor side; each step receives a projection.
- **Long-task hygiene** (from Anthropic long-running guidance): the engine writes a machine-readable `progress.json` (feature/task list with status, like the 200-item failing list) and a short human `progress.md`; each `agent` step starts in a fresh context seeded from: step prompt, the typed inputs, progress summary, and retrieved references by id (just-in-time). Completion is decided by the engine from the task list and gates, never by the model saying "done" (counters premature-completion failure). Tests/gates cannot be edited by the step that they check (gate specs are outside the writable set).
- **Failure semantics**: error classes `transient` (network to model), `invalid_output` (schema fail: one repair attempt with the validator error, then retry), `gate_fail`, `budget_exceeded`, `policy_denied` (sidecar deny/strike, not retried), `fatal` (kill ladder from section 7, never retried). Retry only `transient` and `invalid_output`; exponential backoff with jitter; non-retryable list honored (Temporal/Argo pattern). A defense kill short-circuits everything and runs `on_exit` for cleanup only on the requester side.
- **Idempotency**: steps with external effects (`effects: [write_file_out, propose_memory, spend]`) get an idempotency key `(run_id, step_id, input_hash)`; the engine refuses a second effect execution for the same key (mirrors LangGraph's warning that a resumed node re-runs from the start).
- **Budgets**: hierarchical: run -> scope -> step, units `usd`, `tokens`, `wall_s`, `steps`, `iterations`, `tool_calls`; soft threshold (warn, switch to cheaper model class or summarize) and hard threshold (abort scope with `on_budget`). Price cap from the escrow AUTHORIZE is the outer limit: engine hard-stops before exceeding it.
- **Timeouts and liveness**: `timeout` per step; agent steps emit heartbeats (each model/tool call through the sidecar is a heartbeat), so a stuck pack is detected without trusting it.
- **Human checkpoints**: three kinds: `approve` (before irreversible or high-sensitivity step, also approval-card re-use), `ask` (blocker needs requester input; typed schema), `review` (accept/reject a deliverable, binds to payment Accept). Resume from phone relay.
- **Resume across context resets and crashes**: because run state is outside the model, "resume" = replay journal. A run can be paused by the user, by a human node, by a budget soft-stop, or by a detector pause, and resumed later (policy re-check at resume: revocation list, version).
- **Concurrency and fan-out safety**: caps from architecture: `max_concurrency` default small; total spawn cap and depth cap (Claude Code uses depth 3 and 20 concurrent as reference defaults, source D above; ours are our own choice).

### 2. Concrete DSL sketch (our proposal, YAML, canonicalized to JSON for signing)

```yaml
workflow:
  version: 1
  budget: {usd: 3.00, wall_s: 5400, steps: 200}
  state:
    schema: schemas/state.json
    keys:
      tasks:    {type: list, reducer: append}
      findings: {type: list, reducer: append}
      report:   {type: object, reducer: replace}
  entry: plan
  nodes:
    plan:
      type: agent
      prompt: prompts/plan.md
      tools: []
      memory: {read: false}
      output_schema: schemas/plan.json        # emits tasks[]
      writes: [tasks]
      next: analyze
    analyze:
      type: map
      over: state.tasks
      max_items: 12
      max_concurrency: 3
      join: all
      body:
        type: agent
        prompt: prompts/analyze.md
        tools: [read_file, py_sandbox]
        memory: {read: [project-atlas], max_sensitivity: medium}
        context: fresh
        output_schema: schemas/finding.json
        retry: {max: 2, on: [transient, invalid_output], backoff: {initial_s: 2, factor: 2, max_s: 60}}
        timeout: {step_s: 600}
        budget: {usd: 0.20, turns: 15}
      writes: [findings]
      next: draft
    draft:
      type: loop
      max_iterations: 3
      stagnation: {no_improvement_after: 2}
      body: [write, check]
      until: check.verdict == "pass"
      on_exhausted: escalate
      next: approve_send
    write:
      type: agent
      prompt: prompts/write.md
      reads: [findings, check.feedback]
      writes: [report]
      output_schema: schemas/report.json
    check:
      type: gate
      checks:
        - {kind: schema, schema: schemas/report.json}
        - {kind: regex, field: report.body, must_match: "\\[src:\\w+\\]"}
        - {kind: llm_judge, rubric: rubrics/report.md, context: fresh, model_class: small}
      on_fail: write
    approve_send:
      type: human
      kind: review
      show: [report]
      timeout: {s: 86400, on_timeout: fail}
      next: end
  on_exit:
    - {type: tool, tool: emit_receipt_fields}   # supervisor-generated, fixed schema (3.4)
```

Rules the validator enforces: every cycle must pass through a `loop` or have `max_iterations`; every `map` has `max_items`; every `agent` has `output_schema`, `timeout` and a turn cap; reachable-from-entry; no node may reference tools or memory scope beyond the manifest ceiling; expression language is non-Turing-complete; total worst-case budget (product of caps) must not exceed the manifest's declared max price.

### 3. Built-in templates (so authors do not start from a blank graph)

1. `plan-work-return` (today's three-phase, the simplest).
2. `plan-map-reduce` (orchestrator-workers with gates).
3. `generate-verify-refine` (evaluator-optimizer).
4. `long-task` (initializer plus incremental sessions with task list, progress file, per-task gate and commit; Anthropic long-running shape).
5. `route-then-specialist` (routing).

### 4. Quality loop for the workflow itself (how to measure and improve it)

- Metrics per workflow version, computed by the Certifier from journals: task success against private suite, pass^k reliability, cost per success, wall time, retry rate per node, gate fail rate per node, loop iterations distribution, budget-exhaustion rate, human-checkpoint rate, resume success rate (kill the engine mid-run in the suite and require identical outcome: a "chaos resume" test).
- Structural tests the Certifier runs: determinism of replay (same journal gives same state), idempotency of effects after forced restart, budget enforcement (a pack that tries to loop forever must stop at cap), gate bypass attempts (a pack that writes the checked artifact after the gate must be caught).
- Improvement targets: optimizer (DSPy/GEPA per architecture 5.5) edits node prompts and demos; a second, human-reviewed class of edit changes graph topology (adding a gate, splitting a node). Topology changes that do not alter permissions are MINOR; permission or budget-cap widening is MAJOR (consistent with 5.2).
- Pack ranking can include "gate-backed success" (success verified by deterministic gates) separately from LLM-judged success.

### 5. Behavioral-flow problems found while reading architecture-v2 (owner asked for a careful check)

These come from our own reading of the file, not from external sources.

1. **Fixed phases vs hard tasks**: section 5.2 `phases` has one `work` phase with one tool list and one memory lens; a long task cannot narrow access per subtask nor loop or verify. Fix: workflow graph, per-node lens (above).
2. **No resume story**: 6.2 step 9 destroys the Cell and wipes T at end; a crash or kill mid-run loses everything, and kill is a normal outcome of the defense ladder. Fix: requester-side journal; define which outcomes are resumable (crash, budget soft-stop, human wait) vs terminal (kill/quarantine/revoke).
3. **Who decides "done"**: the pack's returner phase decides completion; acceptance checks (`refund.acceptance_checks`) run only after. Fix: gate nodes inside the workflow plus engine-owned completion.
4. **Payment/run-state coupling**: PayPal AUTHORIZE holds at a capped price (6.2 step 3) but nothing says what happens when the cap is reached mid-run, or on partial capture for a half-finished long task. Fix: budget hierarchy with outer cap = authorization; define milestone captures at declared `milestone` gates (partial capture on acceptance already exists) and a clear "stopped at cap, partial result delivered" state.
5. **Human wait vs sandbox lifetime and token expiry**: one-time run token, Biscuit expiry and the PayPal authorization window (sandbox tokens expire in 3-8 hours per section 9) can lapse while a `human` node waits; resume must re-mint capability and re-check revocation, and the authorization may have to be re-created. Needs an explicit "resume re-approval" rule (diff-based re-approval exists only for version change).
6. **Strike/pause semantics with the workflow**: D6/D8 "pause" currently freezes the Cell; with a graph, a pause should be a node-level suspension with the human question as a `human` event and a default-timeout rule (6/D6 default kill for high-sensitivity). Align the two so there is one pause mechanism.
7. **Detector authority vs retries**: a naive retry policy would re-run a step after a deny/kill and re-trigger the strike; policy-denied and fatal must be non-retryable and must not be replayed on resume.
8. **Memory proposals during a loop**: `memory.proposes` max 5 items per run; with loops/maps a pack could spam Q or re-propose on each iteration. Fix: proposals are idempotent by content hash and counted per run across iterations.
9. **Fan-out explosion and cost**: orchestrator-workers multiply token use (Anthropic reports about 15x chat); without caps a malicious or sloppy pack burns the requester's Nebius budget. The Model Proxy has token/USD caps, but caps per run, per node and per map item are not defined in v2. Fix: hierarchical budgets (above) enforced in sidecar.
10. **Covert channel through control flow**: branching on data and loop counts can encode data in observable step counts and timings that reach receipts/duration buckets. 3.4 already buckets duration and tokens; also bucket step counts and never expose node-level timing to authors.
11. **Hosted resume and attestation**: Hosted host owns the engine, so journal tampering/suppression is possible (existing "host can suppress incidents" gap). Keep the same label; for long Hosted runs add periodic signed journal checkpoints returned to the requester so a requester can at least detect rollbacks.
12. **Certifier scoring of non-deterministic graphs**: v2 scores per (pack version, model) but loops/maps make cost and latency heavy-tailed; LCB should be computed per task with a cost ceiling and report timeouts as failures.
13. **Improvement loop can alter graph**: 5.5 says the optimizer edits only H-plane files and prompts; once the graph is data in the pack, define explicitly that graph topology edits require human review and that budget caps and `max_iterations` never increase automatically.
14. **Reader/Scribe vs nodes**: the Reader/Scribe split (4.3) applies to the local agent, but the same Rule of Two should apply inside a pack workflow: a node that sees foreign content (web/doc) should not be the node that has the highest-privilege tool. The validator can lint this (node with network-class or write tool must not read tainted state keys).

## Risks

- Building our own engine is a large own-code item (journal, scheduler, expression evaluator, validator). Mitigation: keep v1 DSL small (agent, tool, gate, branch, loop, map, human), keep the engine a library with a conformance suite (replay, idempotency, budget), stage subflows and quorum joins later.
- DSL expressiveness vs safety: more power means more review burden and more covert channels. Keep expressions non-Turing-complete; require `max_*` bounds; code steps only in tier 1.
- Portability of graphs across models is poor (v2 cites PromptBridge); per-node model class and overlays may need per-model certification of the whole graph, increasing Certifier cost.
- LLM-judge gates can be gamed by the pack (it writes the artifact); keep deterministic checks first, judge in fresh context with private rubrics, and keep gate specs outside pack-writable state.
- Checkpoint growth (LangGraph warns checkpoints accumulate): journal stores hashes plus content in a size-capped artifact store with retention.
- Evidence gaps: n8n, Dagster severity, Mastra branch/parallel/loop semantics, Agent SDK budget options and the Anthropic "dynamic workflows" post are UNVERIFIED in this run; the architecture does not depend on them. Ranking weights, caps and thresholds above are our own proposals.
- Pause/resume across hours interacts with payment authorizations and capability expiry (item 5 above); not yet designed.

## Sources

- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/built-multi-agent-research-system
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://docs.temporal.io/workflow-execution
- https://docs.temporal.io/encyclopedia/retry-policies
- https://docs.temporal.io/encyclopedia/detecting-activity-failures
- https://docs.temporal.io/activity-definition
- https://www.inngest.com/docs/learn/how-functions-are-executed
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/graph-api
- https://mastra.ai/docs/workflows/overview
- https://openai.github.io/openai-agents-python/running_agents/
- https://openai.github.io/openai-agents-python/guardrails/
- https://argo-workflows.readthedocs.io/en/latest/walk-through/loops/
- https://argo-workflows.readthedocs.io/en/latest/retries/
- https://argo-workflows.readthedocs.io/en/latest/walk-through/exit-handlers/
- https://dagster.io/docs/guides/test/asset-checks
- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/skills
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/agent-sdk/overview
