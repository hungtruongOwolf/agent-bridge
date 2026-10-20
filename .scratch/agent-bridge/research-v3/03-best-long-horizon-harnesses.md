# 03. What the best real harnesses do to finish hard, long tasks

Date: 2026-10-07. Scope: mechanisms from Claude Code, OpenHands, SWE-agent / mini-swe-agent, Codex CLI, Aider, Cline/Roo, deepagents, deep-research agents, Manus, Cognition, OpenClaw skills. Primary sources only (official docs, repo source read from shallow clones on 2026-10-07, papers at abstract level). Anything not confirmed from a primary source is marked UNVERIFIED. Repo licenses come from `gh api repos/<r>` (SPDX field) on 2026-10-07.

---

## 1. Summary

1. **No serious long-horizon harness is "three fixed phases".** Every one of them is a loop with an environment-grounded verify step, a durable state file outside the context window, hard budgets, and an exit that is decided by something other than the model saying "done". The phases planner -> worker -> returner in architecture-v2 s5.2 is a happy-path skeleton; it has no verify loop, no retry, no stuck handling, no resume. It should become one *workflow graph* among several.
2. **The convergent recipe** (Anthropic harness post, Manus, deepagents, OpenHands, Claude Code, Codex): (a) externalised plan/progress files (JSON feature list, todo, NOTES.md); (b) one unit of work at a time with commit/checkpoint after each; (c) verification through tests or a separate grader that can reject the "done" claim and push the agent back into the loop; (d) context control by tool-result clearing, summarising old turns while offloading the full history to disk, and delegating noisy work to sub-agents that return short summaries; (e) hard caps on steps, wall time, cost, and consecutive format errors; (f) stuck detection on repeated action/observation patterns; (g) human gates only for irreversible or out-of-policy actions.
3. **Two things are genuinely contested:** multi-agent parallelism (Anthropic: orchestrator-workers win on breadth research, 15x tokens; Cognition: single linear thread plus a compression model, parallel agents make conflicting implicit decisions) and how much the harness matters versus the model (mini-swe-agent: ~100-line linear bash loop scores >74% on SWE-bench Verified per its own README, UNVERIFIED independently). The workflow engine must therefore let a pack choose, and the Certifier must measure, rather than we dictate.
4. **For agent-bridge the right move is a "Harness Spec" that is a typed workflow graph** (nodes: plan, act-loop, verify gate, branch, fan-out/fan-in, checkpoint, human gate, summarise/compact, finish; edges conditioned on environment results) executed by a small deterministic **workflow runner inside the Cell**, with every model call, budget, and permission still enforced by the requester-owned sidecar. Existing harnesses (mini-swe-agent, deepagents, OpenHands SDK) become *node implementations* or *runner adapters*, not the product.
5. **Four reference archetypes worth shipping** (s5): private-folder data analyst, code patcher, research/report writer, document processor. Each has a clear, machine-checkable acceptance test, which is what makes certification and refunds objective.
6. **Importable under permissive licenses** (s6): mini-swe-agent (MIT), deepagents (MIT), OpenHands SDK (MIT), Codex CLI (Apache-2.0), Cline (Apache-2.0), Aider (Apache-2.0), GPT-Researcher (Apache-2.0), STORM (MIT), LangGraph (MIT), OpenClaw (MIT). Roo Code and langchain-ai/open_deep_research are archived (frozen but still licensed). Claude Code is proprietary, not redistributable.

---

## 2. Key facts with sources

### 2.1 Planning files, feature lists, progress notes

| Fact | Source |
|---|---|
| Anthropic's long-running-agent harness uses an **initializer agent** (first session only) that creates `init.sh`, a `claude-progress.txt` log, an initial git commit, and a feature-list JSON with 200+ items each `"passes": false`. Coding sessions then work **one feature at a time**, commit with descriptive messages, update the progress file. JSON chosen because the model is less likely to overwrite it inappropriately; prompt says it is unacceptable to remove or edit tests. | https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents |
| Same post lists failure modes and fixes: declaring victory early (feature list forces incremental verification), leaving buggy code (new sessions read progress file + git log and run a basic test first), skipping testing (browser automation via Puppeteer MCP, "as a human user would"), unfamiliar environment (pre-written `init.sh`). | same |
| Manus: **todo.md recitation** pushes the objective into the recent attention span ("lost in the middle"); the **file system is the unlimited external memory**, observations can be dropped from context if retrievable from files. | https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus |
| Anthropic multi-agent research: lead agent **saves its plan to memory** so it survives context truncation at 200k tokens; explicit **effort-scaling rules in the prompt** (1 agent / 3-10 calls for facts, 2-4 subagents for comparisons, 10+ for complex research). | https://www.anthropic.com/engineering/multi-agent-research-system |
| Anthropic context-engineering post: structured note-taking (NOTES.md), compaction, tool-result clearing as the "safest lightest touch", just-in-time retrieval via lightweight identifiers, sub-agents returning 1,000-2,000-token summaries. | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents |
| deepagents bundles planning (todo), filesystem, sub-agents, summarisation, memory, skills, human-in-the-loop as middleware on top of LangGraph; README says it was inspired by Claude Code. | https://github.com/langchain-ai/deepagents (README, `libs/ARCHITECTURE.md`, read from clone) |

### 2.2 Verification and test loops (the "done" gate)

| Fact | Source |
|---|---|
| Claude Code's loop is gather context -> act -> **verify results**, repeated; verification is typically running tests and re-reading output. | https://code.claude.com/docs/en/how-claude-code-works |
| Claude Code `Stop` hook can **block the stop** (`decision: "block"` or exit code 2 on `Stop`) and force the conversation to continue; hook handlers can be shell commands, HTTP, MCP tool, a prompt (single-turn model check), or an experimental **agent** hook that spawns a verifier subagent with read tools. | https://code.claude.com/docs/en/hooks |
| deepagents `RubricMiddleware`: when the agent would finish (no more tool calls), a **separate grader sub-agent** scores the transcript against a declared rubric; verdicts `satisfied` / `needs_revision` / `failed`; `needs_revision` injects the grader feedback as a message and resumes; terminal statuses include `max_iterations_reached` and `grader_error`. Grader prompt: "Be conservative: every criterion you cannot positively confirm should be marked failed". | `libs/deepagents/deepagents/middleware/rubric.py` in https://github.com/langchain-ai/deepagents (read from clone) |
| OpenHands SDK has a `/goal` driver: send objective, run agent, **judge completion with a second LLM**, re-prompt until done or cap hit; also an iterative-refinement **critic** that retries when a score is below threshold. | `openhands-sdk/openhands/sdk/conversation/goal/`, `critic/base.py` in https://github.com/OpenHands/software-agent-sdk (read from clone) |
| Aider: lints every edited file by default (`--lint-cmd`), runs tests with `--test-cmd` + `--auto-test`; a non-zero exit code triggers an automatic fix attempt. | https://aider.chat/docs/usage/lint-test.html |
| Anthropic "Building effective agents": agents need **ground truth from the environment at each step**; stopping conditions (max iterations) and human pause points; evaluator-optimizer pattern when clear criteria exist. | https://www.anthropic.com/engineering/building-effective-agents |
| Anthropic evals post: three grader types (code, model, human); grade **outcome (final environment state) and transcript**; an agent can claim success in the transcript while the outcome fails; pass@k vs **pass^k** (all k succeed); read transcripts to validate graders. | https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents |

### 2.3 Sub-agent delegation and isolation

| Fact | Source |
|---|---|
| Claude Code subagents run in their **own context window** with their own system prompt, tool allowlist, permission mode, `maxTurns`, optional `memory` scope, optional `isolation: worktree`; non-fork subagents do **not** inherit conversation history; parent receives a summary. Spawning can be restricted (`Agent(worker, researcher)`). | https://code.claude.com/docs/en/sub-agents |
| Anthropic: each delegated task needs **objective, output format, tool/source guidance, clear boundaries**; vague tasks cause duplicated work. Multi-agent used ~15x chat tokens, single agent ~4x; token usage alone explained 80% of research-quality variance. Failure modes seen: too many subagents for simple queries, SEO farms over primary sources. | https://www.anthropic.com/engineering/multi-agent-research-system |
| Cognition (counter-view): "share context, and share full agent traces"; "actions carry implicit decisions, and conflicting decisions carry bad results"; recommends a **single-threaded linear agent**, plus a dedicated compression model for long tasks; avoid parallel agents that cannot see each other's decisions. | https://cognition.com/blog/dont-build-multi-agents |
| deepagents: sub-agents have isolated context windows; custom compiled LangGraph graphs can be sub-agents; async/remote sub-agents exist; middleware state private to a middleware is not leaked to sub-agents. | `libs/ARCHITECTURE.md` (clone) |
| GPT-Researcher multi-agent example: roles Chief Editor, Researcher, Editor, Reviewer, Reviser, Writer, Publisher, Human; stages plan -> collect -> review/revise -> write -> publish. Planner generates research questions, execution agents gather, publisher aggregates. | `multi_agents/README.md` and README in https://github.com/assafelovic/gpt-researcher (clone) |

### 2.4 Context compaction and memory files

| Fact | Source |
|---|---|
| Claude Code: when context nears the limit it **clears older tool outputs first, then summarises**; early detailed instructions can be lost, so persistent rules go in CLAUDE.md; a `Compact Instructions` section steers the summary; it **stops auto-compacting after a few attempts** instead of looping when one output refills the window ("thrashing" guard). Auto memory: first 200 lines / 25KB of `MEMORY.md` load each session. | https://code.claude.com/docs/en/how-claude-code-works |
| OpenHands condenser: when event count exceeds `max_size` (default 120 implied by "view has max_size // 2 events (default: 60)") it keeps the **head**, LLM-summarises the **middle**, keeps the **tail**; also triggers reactively on context-window errors via a `CondensationRequest`. Pipeline condenser exists. | https://docs.openhands.dev/sdk/arch/condenser ; `context/condenser/` in clone of https://github.com/OpenHands/software-agent-sdk |
| deepagents `SummarizationMiddleware`: defaults trigger at 85% of context (fraction) and keep 10%; **offloads the full pre-summary history to a backend file** (`/conversation_history/{session_id}.md`) so the agent can re-read it; also truncates old tool-call args. | `middleware/summarization.py` (clone) |
| Manus: **KV-cache hit rate is the single most important production metric**; keep prompt prefix stable, append-only context, mask tools via logits instead of removing them, **keep failed actions/stack traces in context**, add small structured variation to avoid few-shot ruts. | Manus blog URL above |
| mini-swe-agent: **completely linear history**, no compaction; every step appends messages; trajectory JSON saved after every step. | https://github.com/SWE-agent/mini-swe-agent README and `agents/default.py` (clone) |

### 2.5 Checkpointing, rewind, resume

| Fact | Source |
|---|---|
| Claude Code checkpoints file state **before each user prompt that starts a turn** (last 100 kept); `/rewind` restores code, conversation, or both; **does not track Bash side effects or subagent edits**; "not a replacement for version control". Sessions are JSONL transcripts that can be `--resume`d, `--continue`d, forked. | https://code.claude.com/docs/en/checkpointing ; https://code.claude.com/docs/en/how-claude-code-works |
| Cline: **shadow git repo** commits state after each tool use, separate from the project's git; restore files only, task only, or both; this is what makes auto-approve practical. | https://docs.cline.bot/features/checkpoints |
| Codex `exec`: `--json` JSONL event stream, `--output-schema` validated final message, `exec resume --last`, default sandbox read-only. | https://learn.chatgpt.com/docs/non-interactive-mode (redirect target of developers.openai.com/codex/noninteractive) |
| LangGraph durable execution: checkpointers persist thread state for resume after failure, human-in-the-loop pause, time travel; in-memory savers lose state on restart, use SQLite/Postgres; checkpoints accumulate and need cleanup. | https://docs.langchain.com/oss/python/langgraph/durable-execution |
| Gemini Deep Research: **background execution + polling by interaction id**, streaming resumable with `last_event_id`, `collaborative_planning` returns a plan for the user to refine/approve before the run starts, follow-ups via `previous_interaction_id`. | https://ai.google.dev/gemini-api/docs/deep-research |
| Anthropic multi-agent research: resumes from checkpoint failures rather than restarting; tells the agent when a tool is failing and lets it adapt. | multi-agent research post above |

### 2.6 Error recovery, stuck detection, budgets

| Fact | Source |
|---|---|
| OpenHands `StuckDetector` scans the last 20 events for 5 scenarios: same action + same observation (threshold 4), same action + error (3), agent **monologue** (3), alternating A/B pattern (6), context-window error loop; on by default; `max_iteration_per_run` default 500. Action-error loop also produces a **nudge message** rather than only aborting. | `conversation/stuck_detector.py`, `conversation/types.py`, `conversation/conversation.py` in clone of software-agent-sdk |
| mini-swe-agent `AgentConfig`: `step_limit`, `cost_limit` default 3.0 USD, `wall_time_limit_seconds`, `max_consecutive_format_errors` default 3; every exit is a typed `exit_status` (`LimitsExceeded`, `TimeExceeded`, `RepeatedFormatError`) with trajectory saved in a `finally`. Interactive modes: human / confirm / yolo with a regex whitelist and optional confirm-on-exit. | `agents/default.py`, `agents/interactive.py` (clone) |
| Claude Code headless: `--max-turns`, `--max-budget-usd` (subagent spend counts; spawning fails with `Budget limit reached` once exceeded), `--fallback-model`, `--json-schema` structured final output, `--permission-prompts none` (anything that would prompt is denied and the agent is told not to retry), `--worktree` isolation, typed `api_retry` events, SIGTERM handling that records a killed command. | https://code.claude.com/docs/en/cli-reference ; https://code.claude.com/docs/en/headless |
| Claude Code subagents' `maxTurns` marks result partial; a stuck background subagent is dropped after a 10-minute idle wait ceiling in `-p` mode. | sub-agents and headless pages |
| Codex sandbox modes read-only / workspace-write (default, network off) / danger-full-access; approval policies on-request / never / granular; `.git`, `.agents`, `.codex` stay read-only inside writable roots; Seatbelt on macOS, bwrap+seccomp on Linux, WSL2 or native sandbox on Windows. | https://learn.chatgpt.com/docs/agent-approvals-security (redirect target of developers.openai.com/codex/security was a different page; this URL was the approvals page) |
| OpenHands SDK has a `security/` module with risk levels and a `ConfirmationPolicy.should_confirm(risk)`: confirmation is a **policy over risk**, not a blanket prompt. | `security/confirmation_policy.py` (clone) |
| deepagents: permissions enforce path-level policy on built-in filesystem tools, but "permissions are not a visibility mechanism"; it provides no OS-level isolation (use a sandbox backend); `FilesystemBackend` without `virtual_mode` has no path restriction. | `libs/ARCHITECTURE.md`, `libs/deepagents/THREAT_MODEL.md` (clone) |

### 2.7 Interface design (ACI) and the effect of the harness

| Fact | Source |
|---|---|
| SWE-agent paper: LM agents are a new class of user that needs purpose-built interfaces; custom ACI for editing, navigation, test execution lifted SWE-bench pass@1 to 12.5% and HumanEvalFix to 87.7% in that paper (2024 models). | https://arxiv.org/abs/2405.15793 |
| mini-swe-agent (same team) argues the opposite direction for modern models: ~100-line agent class, bash only, linear history, ">74% on SWE-bench verified" (self-reported; UNVERIFIED independently). | mini-swe-agent README (clone) |

### 2.8 Evaluating long-horizon success

| Fact | Source |
|---|---|
| METR: the **50%-task-completion time horizon** (human time of tasks a model completes half the time); doubling roughly every 7 months since 2019; Claude 3.7 Sonnet about 50 minutes in that paper; gains attributed to reliability and error adaptation. | https://arxiv.org/abs/2503.14499 |
| tau-bench: **pass^k** measures consistency over k trials; GPT-4o under 50% single-try, pass^8 under 25% on retail in that paper. | https://arxiv.org/abs/2406.12045 |
| Anthropic multi-agent research eval: ~20 representative queries to start, LLM-judge rubric (factual accuracy, citation accuracy, completeness, source quality, tool efficiency), humans for edge cases. | multi-agent research post |
| deepagents ships an evals suite with trajectory capture and Harbor / Terminal Bench 2.0 integration. | `libs/evals/README.md` (clone) |
| Round-2 finding already in architecture-v2: shared grader/pack environments get gamed (Berkeley RDI). Applies directly to our Certifier. | architecture-v2 s5.3 (secondary; primary not re-fetched this round) |

### 2.9 Skills and packaging (OpenClaw, Claude Code)

| Fact | Source |
|---|---|
| OpenClaw skills: `SKILL.md` with `name`, `description` frontmatter, optional gating (`requires.bins/env/config`, `os`), 7-level precedence (workspace first), per-agent allowlists, ClawHub install by `@owner/slug` or `git:owner/repo@ref`; docs say **treat third-party skills as untrusted code, they run on the host process, not sandboxed by default**. | https://docs.openclaw.ai/tools/skills |
| Claude Code skills load on demand (only description in context until used); subagents can preload skills; `--bare` skips auto-discovery for reproducible scripted runs. | how-claude-code-works and headless pages |

### 2.10 Not obtained

- OpenAI Deep Research announcement returned HTTP 403: details of its training, planning, citation behaviour are UNVERIFIED this round.
- Codex AGENTS.md semantics page not fetched (repo docs only redirect). UNVERIFIED beyond the fact that Codex reads AGENTS.md.
- Devin internals: no primary technical source found; treat Devin-specific mechanisms as UNVERIFIED. Cognition's public blog (above) is the only primary material used.
- Roo Code and Cline internals beyond checkpoints (Plan/Act mode, memory bank): not in the fetched docs; UNVERIFIED.
- Independent reproduction of any SWE-bench / Deep Research Bench score quoted by a repo README: not done.

---

## 3. Fit for agent-bridge

### 3.1 What this changes in architecture-v2

architecture-v2 s5 defines the harness as "prompts, skills, planner/worker/returner policies, tool config". The owner's feedback is right: that is a **static configuration**, not a workflow. The evidence above says the thing that finishes long tasks is a **control program around the model**: loops with exit conditions, verification gates, durable state, budgets, and recovery. So the pack needs an executable, declarative **workflow** layer that is (a) inspectable, (b) enforceable below the model, (c) certifiable, (d) improvable.

### 3.2 Proposed concept: Harness Spec = workflow graph + policies

A pack's `workflow.yaml` (our own proposal, not sourced) declares:

| Element | Contents | Evidence it comes from |
|---|---|---|
| **Nodes** | `plan` (writes `plan.json`), `act_loop` (bounded ReAct loop with a tool allowlist and per-node step cap), `verify` (gate), `branch` (on verifier result or enum from state), `fan_out`/`fan_in` (sub-agent delegation with objective, output schema, boundaries, budget), `checkpoint`, `compact`, `human_gate`, `finish` | Anthropic harness post, Anthropic multi-agent post, deepagents middleware set |
| **Verify node kinds** | (1) deterministic command (tests, linter, schema validator, row-count reconciliation, citation resolver), (2) rubric grader sub-agent (fresh context, conservative default), (3) both with AND. A verify failure routes back with the failing output as feedback and increments a loop counter | Aider lint/test, deepagents RubricMiddleware, Claude Code Stop hook |
| **State** | A durable **Run State** directory: `plan.json`, `progress.md`, `features.json` (each item `passes:true/false`, model may flip only via a verifier-written field), `notes.md`, `trace.jsonl`; written by the runner, not only by the model | Anthropic harness post, Manus todo.md, Claude `claude-progress.txt` idea |
| **Context policy** | tool-result clearing first, then summarise with full history offloaded to `/state/history/*.md`, head+tail kept, stable system prefix, errors kept in context, thrash guard (stop compacting after N attempts) | Anthropic context post, OpenHands condenser, deepagents summarisation, Claude Code, Manus |
| **Budgets** | per-run and per-node: steps, wall time, USD, tokens, consecutive format errors, verify-loop iterations, fan-out width/depth; sub-agent spend counts toward parent cap | mini-swe-agent config, Claude `--max-budget-usd`, Anthropic effort scaling |
| **Stuck policy** | detector list (same action+obs x4, action+error x3, monologue x3, A/B alternate x6, context-error loop) with response ladder: nudge message -> force `replan` node -> escalate to human gate -> abort with partial result | OpenHands StuckDetector (defaults are theirs; our thresholds need tuning) |
| **Recovery** | retry with backoff on model/transport errors (supervisor-side, not model-visible), fallback model, resume from last checkpoint node, typed `exit_status` for every termination | Claude `api_retry`/`--fallback-model`, mini-swe-agent exit statuses, LangGraph checkpointers |
| **Human gates** | declared per node with a risk class; at runtime effective gate = declared OR policy; in unattended mode a gate becomes "deny and tell the agent no one can approve" or "suspend and park run" (never silently auto-approve) | Claude `--permission-prompts none`, OpenHands confirmation policy, Gemini collaborative planning |
| **Output** | schema-validated result + acceptance checks (the same checks that gate payment capture) | Codex `--output-schema`, Claude `--json-schema` |

### 3.3 Runner architecture

- A small **deterministic workflow runner** (no LLM) walks the graph. Each LLM-bearing node calls the sidecar's model proxy. Node transitions are decided by runner code reading verifier/gate results, not by the model.
- **Adapters**: `builtin` runner, `mini-swe-agent` (as the act_loop node for code-patcher), `deepagents` (as act_loop + summarisation + todo for research), `openhands-sdk` (stuck detector, condenser, confirmation policy as libraries). These are node implementations; the **workflow, budgets, and verification are ours** so ranking compares like with like.
- Everything the runner needs stays inside the Cell (tmpfs T plane) *plus* a requester-side **Run Journal** so that a killed or crashed Cell can be resumed (s3.4 below).

### 3.4 Behavioral-flow problems found in architecture-v2 (owner asked for a careful check)

Each item cites the architecture-v2 section and why it is a problem, using evidence from this research.

| # | Problem | Where | Why it matters / evidence | Suggested fix |
|---|---|---|---|---|
| F1 | **Fixed planner->worker->returner has no verify, retry, or loop.** A wrong answer ends the run; refund only by acceptance checks after the fact. | s5.2 `phases`, s6.2 steps 6-7 | Every surveyed harness loops on environment feedback; "declaring victory early" is the first listed failure mode (Anthropic harness post). | Replace phases with workflow graph; verify gate inside the Cell before returner. |
| F2 | **Plan phase has `memory.read: false`.** The planner cannot see even the lens, so plans are generic. | s5.2 manifest | Plans grounded in the data are the point of planning (Anthropic lead agent plans against retrieved info). | Allow plan to use a **schema/metadata-only** `memory.describe` (names, counts, types) with the same broker accounting; or allow plan to be re-run after first `work` exploration (replan node). |
| F3 | **Task scratch (T) is tmpfs destroyed at task end, and the Cell is killed on a CRITICAL detector. Crash or kill = total loss, no resume.** Long tasks (hours) will hit transient failures (model API, OOM, driver restart). | s4.1 T plane, s6.2 step 9, s7.2 | LangGraph and Claude Code both persist state to resume; Anthropic multi-agent resumes from checkpoints. | Runner writes **Run State** to a Cell-external volume owned by the supervisor (ro to the pack for plan/features files, rw only through the runner), snapshot at each checkpoint node. Resume is only allowed for runs that were not killed by a security detector; killed runs resume only from a new Cell with a fresh run token and re-approval. |
| F4 | **Resume and kill interact with money.** AUTHORIZE hold then capture on acceptance; no defined behavior for a run that pauses for hours, suspends at a human gate, or resumes (authorization expiry; PayPal hold lifetimes). | s6.2 step 3, s6.2 step 9 | Long runs outlive a single authorization. PayPal authorization validity window not re-checked this round: UNVERIFIED. | Define run states (running, suspended, resumable, killed, failed, accepted); price in **milestones** (capture per verified milestone from `features.json`), re-authorize on resume; document the PayPal limits once verified. |
| F5 | **Budget enforcement is only on the model proxy.** Wall time, step count, fan-out, disk, and process counts are not tied to workflow nodes; verify loops can spend the whole budget on one node. | s3.1 sidecar | mini-swe-agent and Claude Code enforce steps, time, USD, and sub-agent spend together; Anthropic notes excess subagents as a real failure. | Budgets are hierarchical (run > node > loop) and held by the supervisor; sub-agent spawn is a broker call that debits the parent. |
| F6 | **Stuck loops are indistinguishable from the "volume/enumeration" detector D4.** A legitimately stuck honest pack repeating `memory.search` will get DENY/PAUSE as a security strike and may be quarantined, harming an honest author. | s7.1 D4, strike budget | OpenHands treats repetition as a *quality* signal with a nudge, not a security signal. | Split: **Progress Guard** (stuck, budgets, loops; authority = nudge/replan/abort, no reputation penalty) vs **Security detectors** (kill/quarantine). Strike mapping is explicit and one-directional. |
| F7 | **Human approval flow is per (digest, mode, lens, budget) once, but long workflows hit mid-run gates** (irreversible actions, out-of-lens requests, budget raise, plan approval). Nothing says what happens when the requester is away; approval fatigue is already flagged. | s6.2 step 2, s4.8 | Gemini offers *collaborative planning* before execution; Claude has `--permission-prompts none` for unattended. | Three gate classes: **plan approval** (optional, before work, like collaborative planning), **escalation gates** (rare, declared), **never-gates** (denied). Unattended policy: deny + tell agent; or suspend with expiry; never auto-approve. |
| F8 | **Compaction and summarisation inside the Cell need model calls and can leak.** A summary of lens data becomes a new artifact in `T`/state; summary calls cost tokens not in the budget model; and Nemotron `min_context: 32000` makes compaction frequent. | s5.2 `model.requires`, s3.1 | deepagents/OpenHands compaction are LLM calls; Claude Code has a thrash guard; Manus stresses cache-prefix stability (cache behavior on Nebius is UNVERIFIED). | Compaction is a first-class node with its own budget and taint propagation (summaries inherit the max sensitivity of inputs); thrash guard; offload full history to state, not to context. |
| F9 | **Sub-agents are not modelled.** A pack that fans out inside a Cell multiplies model calls and memory reads; the Memory Broker's Biscuit and read accounting are per run, not per sub-agent; the detectors cannot attribute actions. | s4.4, s7 | Anthropic: ~15x tokens; Claude Code: subagent spend counts to the cap, subagent edits not covered by checkpoints. | Each sub-agent gets an attenuated child capability (Biscuit attenuation is the natural fit), own budget slice, own trace id; fan-out depth/width caps in the manifest and enforced by the supervisor. |
| F10 | **Rollback story is partial.** "Roll back U to pre-task checkpoint" covers the vault, but the pack's *work product* (files it produced) has no checkpoint; Bash-like side effects are untracked in Claude Code too. | s4.5, s7.2 step 7 | Claude Code checkpoints miss Bash/subagent changes; Cline uses a shadow git repo that does capture everything in the workspace. | The Cell workspace is a git/overlay repo owned by the runner: commit per verified feature (Anthropic) and per tool batch (Cline shadow repo); deliver the final diff, not the live tree. |
| F11 | **Acceptance checks are fixed list names (`schema_valid`, `citations_present`) and trivially satisfiable**; they gate payment but not usefulness. A pack can pass checks with junk. | s5.2 `refund.acceptance_checks`, s6.2 | Anthropic evals post: outcome grading must check the real end state; model graders need calibration. | Acceptance = pack-declared deterministic checks **plus requester-supplied checks** (e.g., reconcile totals, run the requester's tests) executed by the sidecar **outside** the pack. |
| F12 | **Certification measures a final score, not long-horizon behavior.** `pass_k: 3` and a baseline delta say nothing about time-to-complete, resumability, recovery from injected faults, or cost variance. | s5.3 step 4, s5.4 | METR time-horizon and tau-bench pass^k show reliability collapses with length/trials. | Add certification dimensions: success vs task length buckets, pass^k, **fault-injection runs** (tool failure, model 5xx, context overflow, kill-and-resume), cost p50/p95, stuck-rate, human-gate rate. |
| F13 | **Improvement loop (s5.5) optimises prompts/demos only**, but the best levers for long tasks are workflow-level (verify gates, loop caps, plan granularity). GEPA on a multi-phase harness is flagged open. | s5.5 | SWE-agent ACI and Anthropic harness results come from structure and tools, not prompt wording alone. | Allow the optimiser to edit **workflow parameters** (verify strictness, loop caps within manifest ceilings, plan granularity) but never widen permissions; track edits as typed diffs. |
| F14 | **Result Guard is applied once at the end** (s6.2 step 7), but long runs produce intermediate artifacts (checkpoints, partial reports, milestone outputs) that also cross to the requester. | s6.2 | Milestones imply multiple deliveries. | Each milestone delivery passes the same Result Guard; define partial-result semantics. |
| F15 | **Pull runs on a modest requester machine.** A long, token-heavy workflow with many verify loops competes with the user's own work and Nemotron rate limits. | s6.1 | Anthropic: token use dominates cost/quality. Nebius rate limits not re-checked: UNVERIFIED. | Show a pre-run cost/time estimate from certified percentiles; allow suspend/resume schedules. |

---

## 4. Recommendation

1. **Redefine the harness** in the spec as: *Workflow graph + node implementations + policies (budgets, stuck, recovery, gates, context) + declared tools/skills + evals*. The Agent is the model plus the runner executing that graph. Keep `phases` only as a trivial 3-node preset ("simple" workflow) for tier-0 packs.
2. **Build one small deterministic workflow runner** (own code, small, testable). Do not make LangGraph a hard dependency (MIT, heavy); keep a LangGraph/deepagents **adapter** and borrow its concepts (checkpointer interface, interrupts). Reuse OpenHands SDK pieces where cheap (StuckDetector logic is ~300 lines, MIT).
3. **Make verification a first-class node** and make the verifier *outside the pack's authority*: requester-supplied checks run by the sidecar; pack-supplied graders run in a separate sub-cell with no vault access.
4. **Separate Progress Guard from Security detectors** (F6) so honest-but-stuck packs are never treated as thieves.
5. **Add Run State + Run Journal on the requester side** for resume, milestones, and billing (F3, F4, F10). Define the run state machine in an ADR before building the runner.
6. **Certify long-horizon reliability explicitly** (F12): task-length buckets, pass^k, fault-injection, cost percentiles. Use our reference packs as the first suite.
7. **Ship four reference archetypes** (below) as workflows, each with a deterministic acceptance test so certification and refunds are objective.
8. **Don't pick a side in the multi-agent debate in the spec.** Provide `fan_out` as an optional node with caps; default archetypes are single-threaded except research (breadth) where Anthropic's evidence supports it; certify both variants on the same suite.

### 5. Reference archetypes (3-4 to ship)

| # | Archetype | Workflow shape | Machine-checkable acceptance | Upstream to import / learn from |
|---|---|---|---|---|
| A | **Private-folder data analyst** (CSV/XLSX/SQLite/PDF tables in the lens) | plan (profile schema via metadata-only describe) -> feature list of questions -> act_loop with py sandbox -> verify (re-compute with an independent code path, reconcile totals, assumptions listed) -> branch (fail -> loop, max 3) -> compact -> report with provenance of every number -> finish | Numbers in the report match a recomputation by the sidecar; every claim cites a file/cell reference; no value outside the lens | Pattern from Anthropic harness (feature list), deepagents (todo, FS, summarisation); runner: builtin or deepagents (MIT). No data-analyst harness with clear permissive licence was verified: build ours. |
| B | **Code patcher** (repo in lens, produce a patch) | plan -> act_loop (bash/edit in git worktree) -> verify (existing tests + new failing-then-passing test; lint) -> branch -> checkpoint commit per fix -> finish with diff | Tests green; diff applies cleanly; no test files deleted/edited unless declared | mini-swe-agent (MIT) as act_loop; SWE-agent (MIT) for ACI ideas; Aider (Apache-2.0) for lint/test auto-fix loop and git commit pattern; OpenHands SDK (MIT) for stuck/condense |
| C | **Research / report writer** (web allowed only in Hosted or with brokered search; Pull with private data uses only local sources by default) | plan (sub-questions, effort-scaled) -> fan_out researchers (own context, output schema) -> fan_in -> verify (citation resolver + fact-check sub-agent) -> revise loop -> finish | Every claim has a resolvable citation; citation text actually contains the claim (sampled); length/format schema | GPT-Researcher (Apache-2.0: planner / execution / reviewer / reviser / publisher), STORM (MIT), open_deep_research (MIT, archived 2026-08), Anthropic's multi-agent write-up as the design reference |
| D | **Document processor** (batch extract/convert/classify files into structured output, long-running by volume) | plan -> **map** over files with checkpoint every N -> per-item verify (schema + confidence) -> quarantine low-confidence items to human gate -> reduce -> finish | Output rows match schema; coverage = 100% of lens files accounted for (processed or explicitly skipped with reason); sampled accuracy vs gold set | No permissive end-to-end upstream verified; compose from deepagents middleware + our map node. Anthropic's docx/pdf/pptx/xlsx skills are **not redistributable** (architecture-v2 s8): use permissive libs (UNVERIFIED which). |

Archetype A and D are the strongest fit for "agent beside private data" (the product's reason to exist); B and C prove generality and give the Certifier different failure shapes.

### 6. Open-source import candidates (licence from `gh api` SPDX on 2026-10-07)

| Repo | SPDX | Last push | State | Use |
|---|---|---|---|---|
| SWE-agent/mini-swe-agent | MIT | 2026-10-06 | active | Act-loop adapter, exit-status/limits pattern |
| SWE-agent/SWE-agent | MIT | 2026-10-06 | active | ACI reference |
| OpenHands/software-agent-sdk | MIT | active (clone 2026-10-07) | active | StuckDetector, condenser, confirmation policy, `/goal` judge loop, critic |
| OpenHands/OpenHands | MIT (repo LICENSE read) | 2026-10-07 | active; repo is now an "Agent Canvas" control-center app, not the SDK | UI reference only. Whether any subdirectory has a different licence: UNVERIFIED |
| langchain-ai/deepagents | MIT | 2026-10-07 | active | Runner adapter; summarisation, rubric, skills, memory, sub-agent middleware as references or imports |
| langchain-ai/langgraph | MIT | 2026-10-07 | active | Checkpointer/interrupt concepts; optional adapter |
| openai/codex | Apache-2.0 | 2026-10-07 | active | Reference for sandbox/approval/`exec --output-schema` semantics; not a runner we need |
| Aider-AI/aider | Apache-2.0 | 2026-05-22 | not archived, slower | Lint/test loop reference |
| cline/cline | Apache-2.0 | 2026-10-07 | active | Shadow-git checkpoint reference |
| RooCodeInc/Roo-Code | Apache-2.0 | 2026-05-15 | **archived** | Reference only |
| assafelovic/gpt-researcher | Apache-2.0 | 2026-10-01 | active | Research archetype base |
| langchain-ai/open_deep_research | MIT | 2026-08-10 | **archived** | Research archetype reference |
| stanford-oval/storm | MIT | 2025-09-30 | stale | Outline-first research reference |
| openclaw/openclaw | MIT | 2026-10-07 | active | Optional MCP front end; skills format reference. Docs say skills are untrusted and unsandboxed by default |
| Claude Code | Proprietary | n/a | n/a | Dev-time reference only; not redistributable |

Licence caution: SPDX covers the repo root; transitive dependencies and bundled prompts/data were not audited (UNVERIFIED). Run the s5.3 SPDX/SBOM gate per import.

---

## 7. Risks

1. **Over-engineering the workflow DSL.** A graph language invites a long tail of features. Mitigation: start with six node kinds (plan, act_loop, verify, branch, checkpoint, finish) plus fan_out and human_gate; version the spec; keep the runner under a few thousand lines.
2. **Verification theater.** A pack-chosen grader can be gamed or too lenient; LLM judges over-accept. Mitigation: requester-side deterministic checks, certifier-side hidden checks, conservative grader prompts (deepagents wording), calibration against human labels (Anthropic evals post).
3. **Multi-agent evidence conflict.** Anthropic's research gains come from a breadth-first task type and 15x tokens; Cognition's critique targets coding. Adopting fan_out broadly could raise cost and inconsistency. Mitigation: archetype-specific defaults, measured in the Certifier.
4. **Self-reported benchmark numbers** (mini-swe-agent >74%, Deep Research Bench ranks) are UNVERIFIED and model/version-specific; the SWE-agent ACI result is 2024-era. Do not quote them as product claims.
5. **Stuck/limit thresholds are borrowed** (OpenHands 4/3/3/6, deepagents 85%/10%, mini-swe-agent 3 format errors, $3 default). They are tuned for other models; Nemotron on Nebius needs its own tuning. No data yet.
6. **Resume and billing complexity** (F3, F4): the run state machine plus PayPal authorization lifetimes is the riskiest un-designed area; PayPal hold behavior on multi-hour runs is UNVERIFIED.
7. **Context-window fit.** Nemotron min_context 32k in the manifest example means frequent compaction; summaries can leak sensitive content into artifacts; cache behavior (Manus KV-cache advice) on Nebius is UNVERIFIED.
8. **Security interplay.** More autonomy and loops mean more tool calls, more broker reads, more candidates for D4/D6 false positives (F6). Sub-agents widen the capability surface (F9). deepagents itself states it offers no OS-level isolation; OpenClaw skills run unsandboxed by default: both only usable inside our Cell.
9. **Importing active upstreams** couples our certification to upstream churn (OpenHands repo restructured; Roo and open_deep_research archived). Pin SHAs, vendor, and re-certify on bump.
10. **Gaps in this research:** OpenAI Deep Research, Devin, Codex AGENTS.md, Cline Plan/Act and memory bank were not verified from primary sources; there may be mechanisms there we missed.

---

## Source list (primary, fetched 2026-10-07)

- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/multi-agent-research-system
- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- https://cognition.com/blog/dont-build-multi-agents
- https://code.claude.com/docs/en/how-claude-code-works , /sub-agents , /checkpointing , /hooks , /headless , /cli-reference
- https://docs.openhands.dev/sdk/arch/condenser ; source at https://github.com/OpenHands/software-agent-sdk (stuck_detector.py, types.py, goal/, critic/, security/)
- https://github.com/SWE-agent/mini-swe-agent (agents/default.py, agents/interactive.py, README)
- https://arxiv.org/abs/2405.15793 (SWE-agent), https://arxiv.org/abs/2503.14499 (METR time horizons), https://arxiv.org/abs/2406.12045 (tau-bench)
- https://github.com/langchain-ai/deepagents (README, libs/ARCHITECTURE.md, THREAT_MODEL.md, middleware/rubric.py, summarization.py, libs/evals)
- https://docs.langchain.com/oss/python/langgraph/durable-execution
- https://aider.chat/docs/usage/lint-test.html
- https://docs.cline.bot/features/checkpoints
- https://learn.chatgpt.com/docs/non-interactive-mode ; https://learn.chatgpt.com/docs/agent-approvals-security
- https://ai.google.dev/gemini-api/docs/deep-research
- https://github.com/assafelovic/gpt-researcher (README, multi_agents/README.md)
- https://docs.openclaw.ai/tools/skills
- Licence/activity data: `gh api repos/<owner>/<repo>` for each repo in the s6 table.
