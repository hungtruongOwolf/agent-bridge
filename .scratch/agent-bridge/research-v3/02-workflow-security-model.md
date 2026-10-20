# 02 - Security model for a declarative workflow harness run by a trusted engine

Date: 2026-10-07. Scope: security consequences of making the harness a declarative workflow (DAG/state machine with steps, branches, bounded loops, checkpoints, retries, budgets, human gates) interpreted by a TRUSTED engine in the requester sidecar/supervisor, versus arbitrary pack code running in the Cell. Builds on `architecture-v2.md` (sections 3, 5, 7). Primary sources only for external facts; our own proposals are marked PROPOSAL; things not confirmed from primary sources are marked UNVERIFIED.

## Summary

1. Moving the control flow out of pack code and into a declarative document interpreted by a trusted engine is the single biggest security upgrade available to v2. Today the manifest only says "phases: plan/work/return" and the runner (builtin loop, mini-swe-agent, deepagents) decides everything else inside the Cell. With a workflow engine, the sequence of steps, which tools/memory/model/budget each step gets, and what data may flow where become data that the supervisor can parse, analyze at publish time, enforce at run time, log, and replay.
2. The engine does not remove the LLM from the loop and does not make prompt injection impossible. What it gives is the property CaMeL and FIDES exploit: untrusted data cannot change which steps run, with which authority, unless the workflow explicitly branches on it and the engine labels that branch. The honest claim stays "structural control on authority and flow, detect-and-contain on content".
3. Per-step capabilities turn the Rule of Two from a per-session slogan into a per-step static check. Each step declares its three properties (untrusted input, private data, external communication/state change). A workflow that has any single step with all three is rejected at publish time unless it has a human gate. The v2 "fresh context per step" idea only works if what crosses steps is a typed, labelled value, not free text.
4. Code-bearing steps (python sandbox, custom tool) stay contained as leaf nodes: they run in a nested no-network sandbox, take typed inputs, return typed outputs, and their outputs inherit the union of their input labels. They cannot choose the next step.
5. Reusing an open-source runtime as the engine is risky in a different way from reusing it as a library for convenience. LangGraph graphs are Python code, so a pack-supplied graph is arbitrary code in the engine process; Temporal explicitly does not treat workflow code as untrusted and its Python sandbox is for determinism, not security. Both have had or document non-security-boundary properties. Recommendation: write a small own interpreter for a restricted workflow format (JSON/YAML data, CEL-style expressions, no embedded general-purpose code), and borrow design ideas (event-history replay from Temporal, state-machine semantics from Amazon States Language, label tracking from CaMeL/FIDES) rather than embedding a runtime. If a durable runtime is wanted later, run it as the internal substrate for engine-authored code only, never for pack-authored definitions.

## Key facts with sources

### A. Why control/data separation and per-step authority matter

- CaMeL: a protective layer around the LLM that "explicitly extracts the control and data flows from the (trusted) query; therefore, the untrusted data retrieved by the LLM can never impact the program flow." Uses capabilities to "prevent the exfiltration of private data over unauthorized data flows by enforcing security policies when tools are called." AgentDojo: 77% of tasks solved with provable security versus 84% undefended. Source: https://arxiv.org/abs/2503.18813
- CaMeL architecture details (read from the HTML version): the Privileged LLM sees only the user query and emits Python-like code; the Quarantined LLM has no tool access and parses unstructured data into a predefined schema; a custom interpreter keeps a dependency graph. In "strict mode" the conditional test or loop iterable becomes a dependency of every variable assigned in the block. Stated limitations: side channels (exception-based bit leakage via a prompt-injected Q-LLM, timing, external resource fetching), user fatigue with approval prompts, and security "only as strong as the capabilities ... and the policies" a human defines. Source: https://arxiv.org/html/2503.18813
- FIDES: planner that "tracks confidentiality and integrity labels, deterministically enforces security policies, and introduces novel primitives for selectively hiding information"; uses dynamic taint tracking; provides a formal model and a task taxonomy of planner design trade-offs. Source: https://arxiv.org/abs/2505.23643 (abstract level only read).
- Six design patterns paper (Plan-Then-Execute, Dual LLM, Action-Selector, Code-Then-Execute, Context-Minimization, LLM Map-Reduce); states trade-offs between security and utility and that no single pattern is complete. Source: https://arxiv.org/abs/2506.08837 and PDF https://arxiv.org/pdf/2506.08837 (pattern names taken from a summary of the PDF fetch; verify names against the paper text before quoting them in product copy -> UNVERIFIED wording).
- Agents Rule of Two (Meta): within a session an agent must satisfy no more than two of [A] untrustworthy inputs, [B] sensitive systems or private data, [C] ability to change state or communicate externally. If all three are needed "without starting a new session (fresh context window)" it needs human-in-the-loop approval or another reliable validation. Covers prompt injection only; "a supplement and not a substitute" for least privilege. Source: https://ai.meta.com/blog/practical-ai-agent-security/
- Lethal trifecta (Willison): private data + untrusted content + ability to externally communicate; "we still don't know how to 100% reliably prevent this"; guardrails claiming 95% are inadequate; principle: once an agent has ingested untrusted input it must be constrained so it is impossible for that input to trigger consequential actions. Source: https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/

### B. Engine candidates and their attack surface

- Temporal: workflow code must be deterministic ("any time your Workflow code is executed it makes the same Workflow API calls in the same sequence, given the same input"); recovery is by replaying against event history; mismatched commands cause non-determinism errors; time and randomness must go through SDK APIs whose results are stored in history. Source: https://docs.temporal.io/workflow-definition
- Temporal Python sandbox: "not completely isolated, and some libraries can internally mutate state, which can result in breaking determinism"; it exists to catch non-determinism, not malicious code; `sandbox_unrestricted()` can disable it. Source: https://docs.temporal.io/develop/python/python-sdk-sandbox (confirmed by the fetch of that page).
- Temporal on untrusted workflow code: a staff answer (6 Sep 2020, therefore possibly dated, UNVERIFIED that it still holds) says untrusted workflow execution is not directly supported, all workflow and activity code runs on worker processes not the server, and suggests isolating workers and launching a sandbox from an Activity for user code. Source: https://community.temporal.io/t/untrusted-workflow-execution/580
- LangGraph: graphs are built in code (`builder.compile(checkpointer=..., store=...)`), so a pack-authored graph is pack-authored code. Persistence layer has checkpointers and stores. Source: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph security advisories (10 listed on the repo as of the fetch) include unsafe JSON deserialization in checkpoint loading (22 May 2026, Moderate), unsafe msgpack deserialization in checkpoint loading (5 Mar 2026), BaseCache deserialization RCE (ZDI-CAN-28385, 23 Feb 2026), RCE in "json" mode of JsonPlusSerializer (5 Nov 2025, High), SQLite checkpointer SQL injection (9 Dec 2025, High), custom-auth and Store cross-user issues (Aug-Sep 2026). Source: https://github.com/langchain-ai/langgraph/security/advisories . A secondary summary says an attacker with write access to the checkpoint backing store can craft a payload that executes code in the worker on resume (CVE-2026-48775; CVE-2026-28277; CVE-2025-64439): https://www.sentinelone.com/vulnerability-database/cve-2026-48775/ , https://advisories.gitlab.com/pypi/langgraph-checkpoint/CVE-2025-64439/ (secondary, not read in full).
- Lesson from LangGraph advisories: persisted workflow state is an attack surface. Anything that can write the checkpoint store gets code execution if state is deserialized into objects. This directly applies to our "checkpoints" requirement.
- Orcheo (third-party project) uses a restricted purely declarative `workflow.py` grammar that rejects non-Orcheo imports including langgraph: shows the restricted-grammar approach exists in practice. Source: https://orcheo.readthedocs.io/en/latest/sandboxed_custom_workflows/ (appeared in search results; page not read, UNVERIFIED details).
- Amazon States Language: workflows as JSON data with state types (Task, Choice, Fail, plus others), conditions in JSONata or JSONPath, validated by Statelint. Shows a data-only workflow format is mainstream. Source: https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html (only the first states and the Choice example were seen in the fetch; Map/Parallel/Retry/Catch/Wait behaviour is UNVERIFIED in this run, from memory only).

### C. Safe expression and policy languages

- CEL: programs "cannot loop forever", have no observable side effects, cannot access unrelated memory, evaluation cost is bounded in terms of input sizes, and "one of the main applications for CEL is for execution of untrusted expressions with reliable containment." Source: https://github.com/google/cel-spec/blob/master/doc/langdef.md
- Starlark: design goals of deterministic evaluation, hermetic execution (no filesystem, network, clock), parallel evaluation via frozen immutable data, simplicity; repo mentions no recursion/while loops and freezing. Source: https://github.com/bazelbuild/starlark . (Spec page truncated; whether a given implementation enforces limits on CPU/memory is UNVERIFIED.)
- Cedar: permit/forbid policies with scope and conditions, schemas for validation. Source: https://docs.cedarpolicy.com/overview/terminology.html . Claims about default-deny, forbid-overrides-permit and formal analysis are not confirmed from the pages read in this run: UNVERIFIED.

### D. Gaps in the sources

- No primary source in this run establishes the exploit rate of "workflow-structured" agents against adaptive prompt injection beyond the CaMeL and FIDES abstracts. Any claim like "the engine blocks injection" is not supported; only "restricts consequences" is.
- No primary source read for Wasm/Firecracker-based nested code sandboxes in this round; refer to research-v2/05, 07 for isolation facts.

## Fit for agent-bridge

### 1. Where the engine sits

The Workflow Engine is a module of the Supervisor/Sidecar (requester-owned, trusted, B1 side), NOT inside the Cell. The pack contributes `workflow.yaml` (data) plus prompts/skills/demos (data) plus optional leaf code. The Cell becomes a pool of step executors: the engine asks it (over the existing unix socket) to run one step with one typed input and gets back one typed output. This keeps the existing boundaries: Cell has no NIC, the sidecar is the only exit.

Consequence for v2 text: "phases planner -> worker -> returner" becomes a special case of a workflow, and manifest `phases:` is replaced by `steps:` and `edges:`. Permissions are per step, and the effective permission rule from architecture 5.2 (declared AND requester policy AND mode ceiling) is evaluated per step.

### 2. Step model (PROPOSAL)

Step kinds, a closed set:

| Kind | What it does | Who decides control flow |
|---|---|---|
| `llm` | One model call (or bounded ReAct sub-loop) with a prompt template, allowed tools list, output schema | Engine; the model only fills the typed output |
| `tool` | Deterministic tool call with args built from typed inputs | Engine |
| `code` | Leaf sandboxed code (python, custom tool) with typed in/out, no network | Engine; code returns data only |
| `branch` | Chooses next step by a CEL expression over typed fields | Engine, with label rule (below) |
| `map` | Bounded fan-out over a typed list (LLM Map-Reduce pattern) with max N | Engine |
| `loop` | Repeat a sub-graph until a CEL condition or max iterations | Engine, max iterations mandatory |
| `gate` | Human approval or deterministic check (schema, acceptance test) | Engine / user |
| `checkpoint` | Snapshot engine state (typed values only) | Engine |
| `return` | Produce the result through Result Guard | Engine |

There is no step that executes pack-supplied control-flow code. No `eval`, no `import`, no dynamic step creation (the "dynamic subgraph" feature that frameworks offer is excluded or restricted to expansion from a pre-declared template with bounded count).

Each step declares: `tools`, `memory lens` (namespaces, max sensitivity, k and byte budget), `model` (class and params), `budget` (tokens, USD, wall time, tool calls), `inputs` (typed), `outputs` (schema), `labels_in`/`labels_out` (derived, see 4), `on_error` (retry count with backoff, fallback step, or fail), `human` (none | before | after).

### 3. Per-step capabilities and step-scoped detectors

- Capability minting: before each step the engine asks the Memory Broker to mint a narrower Biscuit (or macaroon) for that step: step id, namespaces, field mask, quota, expiry in seconds, run id. Attenuation only; a step cannot obtain more than the run capability. A step that reads memory but has no tools has no way to use what it read except through its typed output.
- Tool broker: allowed tool set is per step, enforced by the sidecar (policy engine OPA/Cedar as already planned), not by the model. A tool call from a step outside its list is a D3 scope violation.
- Model proxy: per step model class and token cap; the proxy refuses requests whose step id token does not match. This also removes the "pack picks a pricier model" abuse class.
- Step-scoped detectors: change D1-D14 from run-global to step-parameterised. Concrete changes:
  - D4 volume: budgets are per step, so a worker step that suddenly enumerates is caught against its own small quota, not against a whole-run quota.
  - D6 overlap: the egress content comparison corpus is "the lens of the current step", not the union lens. A `return` step with no memory should never emit lens-overlapping content, so any overlap is high-confidence.
  - D8 sequence: the state machine is the baseline. Actual step sequence not matching an edge of the declared graph is a deterministic violation (promote from policy/pause to deny or kill) rather than a statistical anomaly.
  - D14 behaviour baseline: becomes profile per step, from certified runs.
  - New D15 (PROPOSAL): "engine state tamper": checkpoint hash mismatch, or any step output that fails its schema repeatedly.
- Per-step kill granularity: the ladder gets a step-level rung before run-level: deny the tool call, abort the step with `on_error`, then fail the run. Kill authority stays only in the Supervisor.

### 4. Rule of Two / lethal trifecta per step, and data-flow labels

Mapping to our system:

- [A] untrusted input: pack/web/doc/tool-result content, anything from Q, foreign pack output, outputs of any LLM that has seen such content.
- [B] private data: any memory.search result, staged `/in` files, derived values.
- [C] external communication or state change: tools with network or write effect, writes into Q or artifacts, the result channel itself (the Result Guard output goes to the requester, and the model proxy goes to Nebius which is an external recipient).

Publish-time check (PROPOSAL): for every step compute A, B, C from its declared tools, memory lens and input labels (the label analysis in the next list). Reject a workflow when any step has all three and no `gate`. In Pull private-data runs C is already near zero for tools (`no network tools in private-data runs`), so the realistic trifecta risks are (a) the return step with B-labelled input and A-labelled influence, and (b) the Nebius model call which carries prompts to a third party. Treat (b) explicitly as a C property for any step whose prompt contains B-labelled values, and show it in the listing ("this step sends private text to Nebius").

Taint labels (CaMeL/FIDES-style, PROPOSAL):

- Every typed value carries `{integrity: trusted|untrusted, confidentiality: set of namespaces/sensitivity, source: set of step ids / record ids}`.
- Step output label = join of its input labels and the step's own source label. An `llm` step that reads any untrusted value yields an untrusted output regardless of what the model "means".
- Branch rule, from CaMeL strict mode: if a `branch`/`loop` condition depends on an untrusted value, then every value produced inside the branch is also labelled as depending on that condition. Additionally, publish-time analysis flags any branch whose condition is untrusted and whose arms differ in their tool set or sink (a control-flow channel).
- Sink policy: each sink (tool arg, return field, Q proposal, model prompt to Nebius) declares max confidentiality it accepts and min integrity it requires. Violation is D7 (already in the detector table). Deterministic enforcement is only possible on labelled structured values; free text produced by an LLM is labelled with the join of everything it saw and is therefore usually "private + untrusted", which is why free text must not cross steps unless the next step is allowed that label.
- Declassification: only three ways to lower a label: (a) a deterministic schema/enum extraction by the engine (e.g. a Q-LLM-style step that outputs an enum), (b) human gate, (c) a Disclosure Compiler rule (PII tokenization). Each is logged. Note that (a) is not leak-free: CaMeL itself lists exception/bit-leak through a quarantined LLM, so enum outputs from a prompt-injected step still carry log2(|enum|) bits per call; the per-run count of declassifications is capped (PROPOSAL).
- Dual LLM mapping: an `llm` step marked `quarantined` has no tools and no memory beyond its inputs, and outputs only schema-typed values. A `privileged` step sees only trusted values (user task, plan template, labels) and has the tools. This is the Plan-Then-Execute / Dual LLM pattern expressed as step attributes. The planner step in the current v2 manifest (`plan: memory.read false, tools []`) is already this shape.

What the label system cannot do: labels attach to values the engine can see. Anything the Cell does inside a `code` step or a multi-turn ReAct step is opaque; therefore the output is labelled as the join of the step's inputs and nothing finer, which is sound but coarse, and the in-step behaviour is covered only by sandbox + detectors.

### 5. Plan-then-execute inside the engine

Two usage styles:

1. Static workflows (default): the author fixed the graph. Strongest and most auditable; certifiable per digest.
2. Plan-then-execute workflows (opt-in `planner` step): a privileged planner step produces a plan in the engine's own workflow dialect (not Python) from the trusted task only; the engine validates the plan against a pack-declared envelope (allowed step kinds, tools, max steps, max depth, budget) and the requester policy, then executes it as an ephemeral workflow. This is CaMeL's control-flow extraction with our dialect instead of a Python interpreter. Plans cannot be re-planned using untrusted data, except via a `replan` gate that either needs a human or uses only trusted-labelled information. Fits long/hard tasks where a static graph is too rigid; the envelope is what the static analyzer checks.

The CaMeL cost trade-off (77% vs 84% on AgentDojo) is the measured price for provable security in that benchmark; for us the price shows up as tasks that need the planner to see the data (research on unseen documents) and therefore must be gated or run in the "hosted/low sensitivity" regime. UNVERIFIED how large it is on our task mix.

### 6. Code-bearing steps stay contained

- A `code` step runs in a nested sandbox inside or next to the Cell: no network, read-only input mount of exactly its typed inputs, writable tmpfs, CPU/memory/pids/time caps, no access to the sidecar socket (it cannot call model or memory itself). Its only I/O is stdin/stdout typed JSON. This separates "code that computes" from "code that talks to the broker" and removes the case where pack code gets a memory capability.
- Custom tools (pack-provided tool implementations) are the same: leaf, typed, no brokers. If a tool needs the model, it is expressed as an `llm` step in the workflow instead.
- Outputs are validated against the output schema before they enter the engine; oversized or non-conforming outputs are an error, not truncated silently. Output label = join of inputs; the code step cannot lower labels.
- A tier-1 pack (with code) is therefore still bounded: code can compute on the data it was handed and return a typed value; the leak routes remain the result channel and covert encodings in typed fields, mitigated by schema narrowness (enums, bounded ints, bounded strings), Result Guard overlap checks, and size caps.
- Residual: nested sandbox escape. Driver tiers and the conformance suite from v2 apply; add a fixture per step kind.

### 7. Static analysis at publish time

`bridge pack validate` and the Certifier run an analyzer on `workflow.yaml` (PROPOSAL; all checks are our design):

1. Schema validity, closed step-kind set, no unknown keys, size limits (steps, edges, template length).
2. Reachability: every step reachable from start; every path reaches `return` or `fail`; no dead steps; no unreachable `gate`.
3. Termination bounds: every `loop` and `map` has max iterations/items; the product of nested bounds times max cost per step gives a worst-case cost; compare to the declared budget and refuse if the worst case exceeds the hub price cap. `retry` counts are included in this bound.
4. Permission union: computed set of tools, namespaces, max sensitivity, models across steps. This must equal or be a subset of what the manifest declares and what the approval card shows; any widening vs parent is a MAJOR bump (existing rule). The approval card shows per-step permissions and the union.
5. A/B/C classification per step and the Rule-of-Two check; label flow analysis from sources to sinks over the graph (a may-reach analysis; conservative); report paths private->sink with no declassifier.
6. Untrusted-branch check: branch conditions tainted untrusted whose arms differ in authority.
7. Expression safety: all expressions in a CEL-class language with cost limits (CEL spec states bounded cost and termination); no regex with catastrophic backtracking (use an RE2-class engine, UNVERIFIED which engine we pick).
8. Template safety: prompt templates may only interpolate typed fields via explicit placeholders; every placeholder's label is known; untrusted fields are wrapped in labelled delimiters and cannot appear in system-role text (PROPOSAL; delimiting does not stop injection, it only supports labelling).
9. Human gates: gate steps have timeout and default (default deny for irreversible, default stop for others); no gate sits in a loop without a max count (approval fatigue).
10. Resource closure: declared output schemas fit the author-bound channel rules (enum/int/bounded) when the return fields leave the requester machine (receipts only); result schema may carry free text to the requester only.
11. Dynamic checks that complement: run the certification suites and measure actual path coverage; steps never exercised are flagged.

The analyzer is advisory in the sense of "sound and conservative": it may reject safe workflows; false rejections are the cost, and authors fix them. The requester's supervisor re-runs the analyzer on download, never trusting the hub's verdict, because the digest is content-addressed and analysis is deterministic.

### 8. Determinism, replay and certification

- What is deterministic: the graph walk, tool arguments built from typed values, expression evaluation, label computation, budget accounting. What is not: LLM outputs, wall-clock, tool results from the world.
- Event history (PROPOSAL, borrowed from Temporal's model of replaying against recorded history, source above): the engine appends to the hash-chained audit log, per step, `{step id, input hash, labels, capability id, model request hash, model response (or hash + stored blob), tool results, output hash, decision}`. Replay = re-run the engine against recorded model/tool responses and check that it takes the same transitions and produces the same outputs. This audits the engine and workflow logic without re-calling the model. It does not prove the model would answer the same way.
- Replay use cases: (a) incident forensics: show exactly why a kill fired; (b) certification evidence: attestation binds (workflow digest, model id, suite version, event history hash); (c) regression: replay old histories against a new engine version to detect engine behavioural drift; (d) dispute resolution on payments.
- Privacy of history: event histories contain private data when run in Pull. They stay on the requester machine (vault side), encrypted, with the same crypto-shred rules. Histories that go to the Certifier come from synthetic tasks only. Hub receives only the content-free receipt (existing rule).
- Versioning: Temporal documents that changing commands in a running workflow breaks replay and must be versioned/patched. Our analogue: engine version and workflow digest are pinned in the run; resuming a checkpoint under a different digest or engine major version is refused (PROPOSAL), not patched.
- Certification gains: certify per (workflow digest, model) can include structural coverage (all edges exercised), worst-case cost verified, and a "no step ever exceeded its capability" property checked from histories.

### 9. What a workflow cannot express safely (and what v2 should refuse or gate)

1. Any step with A+B+C simultaneously and no gate (publish-time reject).
2. Control flow chosen by untrusted LLM free text (e.g. "let the model decide the next tool freely over arbitrary tools after reading documents" is just the unconstrained ReAct loop; allowed only as a bounded `llm` step with a fixed tool allow-list and A/B/C within two).
3. Open-ended agent loops with large tool sets and private data: expressible, but they collapse the step to "opaque", so detectors and sandbox carry the load; treat as lower assurance tier and say so on the listing.
4. Dynamic code generation and execution as a step (the model writes code, engine runs it): allowed only as `code` step with typed in/out and no network; anything that needs network is not expressible in Pull private-data runs.
5. Multi-turn conversations with the requester mid-run that carry free text back into private-data steps: the requester's reply is trusted input but may contain pasted untrusted text; treat as a gate with typed answer unless explicitly labelled.
6. Delegation to sub-agents of another pack (pack calling pack): not expressible in v1 of the engine; if added, each hop is a separate run with its own approval and the data-flow label survives.
7. Timing/size covert channels and slow exfiltration through allowed typed outputs: not preventable by the language; mitigated by quantizing, size caps, fixed-shape outputs, non-streaming model calls (open decision 10 in architecture-v2).
8. Declassification by LLM judgement ("is this safe to share?") is not a safe primitive; only schema extraction, human gate, or deterministic rules count.
9. Persistence of state across runs inside the pack (pack-side memory): not expressible; durable effects go only to Q.
10. Anything requiring non-deterministic engine behaviour that cannot be recorded (live wall clock, random choice): must use engine-provided recorded APIs.

### 10. Behavioural-flow problems found in the workflow design and in architecture-v2 (owner asked for a careful check)

Problems that a workflow harness introduces or exposes, with proposed handling:

| # | Problem | Why it matters | Handling (PROPOSAL) |
|---|---|---|---|
| F1 | Free text crossing steps defeats fresh-context isolation | Rule of Two "new session" only helps if state crossing sessions is labelled and narrow | Only typed values cross steps; free text is a typed field with labels and a size cap |
| F2 | Retries replay side effects and re-emit side channels | A retried step repeats tool calls, token spend and any covert emission | Retries counted in budget and in strike accounting; non-idempotent tools forbidden in retried steps; retry reuses recorded outputs where possible |
| F3 | Checkpoint/resume is an injection and deserialization surface | LangGraph advisories show code execution from loaded checkpoints; also the pack could try to write checkpoint contents via step outputs | Checkpoints are engine-written JSON of typed values only, hash-chained and signed by the supervisor, never deserialized into objects, stored on the vault side; resume verifies signature, digest and engine version |
| F4 | Budget semantics: step budget vs run budget vs price cap | A cheap loop can drain the escrow cap; unspent step budgets could be reallocated by pack | Run budget is the hard cap, step budgets are sub-limits; no carry-over unless declared; worst-case from analyzer must be <= price cap |
| F5 | Human gate timeouts and fatigue | CaMeL paper and architecture-v2 both flag approval fatigue (93% approval figure in Claude Code is cited in v2 from earlier research, not rechecked here) | Gates only at irreversible/high-sensitivity transitions; typed, diff-style cards; default on timeout is deny/stop; gate count shown in the listing |
| F6 | Kill/abort mid-step leaves partial state | A killed step may have written to T, proposals, or escrow authorisation | All durable effects happen at engine commit points after step success; step outputs are staged and discarded on abort; escrow VOID triggered by the supervisor, not the engine |
| F7 | Engine bug is now the trusted computing base | Pack no longer controls flow but the interpreter bugs (expression eval, template, label join) are now the exploit target | Small engine, fuzzing, differential tests, memory-safe language, expression language with cost limits, run the engine under its own seccomp/AppArmor profile separate from the Supervisor kill authority |
| F8 | Engine and Supervisor coupling | v2 says Supervisor must be separate from the Sidecar so sensors tampering cannot disable kill | Put the engine in the Sidecar side process, not in the Supervisor process; Supervisor only receives engine events and can kill |
| F9 | Pack lens vs step lens | architecture-v2 manifest has a run-level lens approved by the user; per-step lenses must be subsets | Approval card shows union and per-step; step lens is attenuation of the approved lens |
| F10 | Hosted mode | The host runs the engine under host root, so the engine is not trusted by the requester in Hosted | Say so: in Hosted the engine's static guarantees still hold for the packet content but verdicts/histories are owner-attested; requester re-validates workflow and results on arrival; packet is built from the workflow's union lens only |
| F11 | Nebius as a hidden sink | Every `llm` step with B-labelled prompt sends private text to a third party | Treat as a labelled sink "third-party model"; approval card lists which steps send private text; ZDR caveats from v2 apply |
| F12 | Result channel carries free text and is the main exfil channel | Typed enums cannot cover all deliverables (reports, patches) | `return` schema distinguishes "free text field" (to requester only) from enum fields; Result Guard overlap and canary checks plus inert render remain; claim stays detect-and-contain |
| F13 | Workflow expressiveness vs certification | More dynamic workflows reduce certifiability | Assurance tiers: static workflow > envelope-bounded plan > opaque agent loop; tier shown in listing and ranked separately (extends existing tier 0/1) |
| F14 | Nondeterminism in graders | Certification of LLM steps is statistical | Keep v2 rule: LCB over pass^k on private suites, per (digest, model) |
| F15 | The `phases` block in architecture-v2 sets `memory.read` for work only, but the manifest says tools list includes `py_sandbox` in the same step that reads memory | In the current design the work phase mixes A, B and code execution | In the workflow model split into `retrieve` (B only, no tools) then `compute` (code, typed in/out) then `synthesize` (llm, quarantined) |

## Open question: reuse an open-source runtime as the engine?

| Option | What it gives | Attack surface of embedding | Verdict |
|---|---|---|---|
| LangGraph (as engine) | Graph/state machine, checkpointers, human-in-the-loop, widely used with LLM agents | Graph is Python code: pack-authored graph = arbitrary code in engine process. Persistence layer has a record of deserialization RCE advisories (Nov 2025 - May 2026) and SQL injection in SQLite checkpointer; large dependency tree (LangChain). Can be used only if the graph is generated by our own compiler from the declarative file and checkpoints are replaced with our own typed JSON saver | Do not embed as the trusted engine. Possible as a runner adapter inside the Cell for tier-1 packs |
| Temporal | Production-grade durable execution, event-history replay, retries, timers, signals (human gates) | Requires a server and database; workflow code is code; Python sandbox "not completely isolated" and not a security boundary; staff position (2020, possibly dated) is no direct support for untrusted workflow code; huge operational footprint for a requester laptop | Do not embed. Copy concepts (event history, determinism rules, versioning) |
| Amazon Step Functions / Argo-style / ASL | Declarative JSON state machine as the data model | ASL is a spec; AWS runtime is a managed service, not embeddable locally; Task states reference cloud resources | Use ASL as a design reference for the data format (state types, Choice, Retry/Catch); do not depend on it; Map/Parallel/Retry details UNVERIFIED in this run |
| CaMeL reference implementation | Custom Python interpreter with capabilities and dependency graph | Research artifact from Google repo (README not read: the fetch of the GitHub URL returned 404, so its licence, status and API are UNVERIFIED); Python interpreting Python = large language surface | Read for design; do not embed. Our dialect is data, not Python |
| Starlark interpreters (Go/Rust) | Deterministic, hermetic, no recursion/while loops design goals | Still a general-purpose-ish language; CPU/memory limits per implementation UNVERIFIED; implementation bugs possible | Optional for author-supplied transforms if expressions in CEL prove too limited; not needed in v1 |
| CEL (cel-go, cel-rust, cel-python) | Expression language built for untrusted expressions: no loops forever, no side effects, bounded cost | Implementation bugs; need cost limits configured; which library we use is UNVERIFIED (library maturity not checked) | Use for conditions and field mappings only |
| Own minimal interpreter | Exactly the step kinds we need, typed values with labels, checkpoint format, event history hooks, small TCB | We own all bugs; need fuzzing and tests | Recommended |

Engine implementation guidance (PROPOSAL): language is memory-safe and has good sandboxing story for the sidecar (Rust or Go; JS only if the rest of the sidecar is JS and the engine runs in its own isolated process); workflow format is YAML/JSON canonicalized and signed like the manifest; the interpreter is ~a few thousand lines; property-based and differential tests of the label join and expression evaluation; fuzz the parser and the template renderer; the engine process has no network except the unix sockets to broker and model proxy (so the engine itself cannot become the exfil path); the engine has no access to vault files except through the Memory Broker.

## Recommendation

1. Adopt "workflow-first harness": `workflow.yaml` (closed step set, typed values, labels, per-step permissions and budgets, bounded loops, gates, checkpoints, retries) interpreted by a trusted Workflow Engine in the requester sidecar process group. The Cell executes steps, never decides flow.
2. Build the engine ourselves (small interpreter + CEL for expressions). Take design ideas from Temporal (event history, determinism and versioning rules), ASL (declarative state machine), CaMeL/FIDES (labels, strict-mode dependency, capability checks at tool calls), Rule of Two (per-step classification). Do not embed LangGraph or Temporal as the trusted engine; LangGraph/other runners remain allowed only as runner adapters inside the Cell for tier-1 packs.
3. Make the publish-time analyzer part of the Certifier and also of the requester's supervisor (re-verify locally). Gate publication on: reachability, termination bounds and worst-case cost, permission union equal to manifest, Rule-of-Two per step, untrusted-branch check, label flow report.
4. Replace "phases" in the manifest with `steps/edges`; keep a template workflow equal to plan -> retrieve -> compute -> synthesize -> return so simple packs stay simple.
5. Enforce per-step capabilities at three places: Biscuit per step for memory, tool broker per step, model proxy per step; make detectors step-parameterised, and treat "step sequence off-graph" as a deterministic kill-grade signal (it can only come from engine tamper or Cell misbehaviour).
6. Checkpoints and event histories: typed JSON only, signed hash chain, vault-side encryption, never deserialized to objects; resume refused if digest or engine version differs.
7. Introduce assurance tiers: static workflow (highest), envelope-bounded plan-then-execute, opaque agent loop (lowest, still allowed for non-private-data or low-sensitivity runs). Show on the listing; rank separately.
8. Add to the research/design backlog: a spike for the label system on two real workflows (a research workflow and a code-review workflow) to measure how often the strict-mode rule forces human gates; a fuzzing plan for the engine; a decision on declassification budget.
9. Product copy stays honest: "the engine guarantees which steps may run and which authority each step has; it does not guarantee that a model reading untrusted text will not be steered within its authority; content leakage through allowed outputs is detected, not prevented."

## Risks

- The engine becomes the trusted computing base: a bug in expression evaluation, template rendering, label propagation or schema validation can silently break all guarantees. Needs fuzzing, differential tests, small code.
- Over-tainting: with strict-mode style dependency tracking, most real tasks end with "private + untrusted" labelled outputs, leading to many gates and approval fatigue (CaMeL itself lists user fatigue). Measured utility cost for our tasks is UNVERIFIED (CaMeL's 77% vs 84% is AgentDojo only).
- Expressiveness ceiling: authors of hard, long tasks (the owner's target) may need agent loops that cannot be statically bounded; the tiering handles it, but the top rank tier may stay thin, hurting cold start.
- False sense of security: marketing "workflow = safe" would contradict the honesty rules. Side channels (timing, enum bit leakage, steganography in free text) remain.
- Static analysis is conservative and may be unsound in corners (templates, tool outputs with hidden structure, tools with side effects not captured in their declared metadata); declared tool metadata (reads/writes/network) becomes a trust input that we must audit for our own tools and require conformance tests for pack-supplied tools.
- Replay gives audit of engine decisions, not of model behaviour; claims about "reproducible runs" must be limited accordingly. Histories hold private data in Pull and need the same protection as the vault.
- Hosted mode: engine runs under host root, so none of the engine guarantees protect the packet from the host; verdicts remain owner-attested.
- Reuse temptation: embedding LangGraph/Temporal later for convenience would reintroduce pack-authored code in the engine process and a large dependency/advisory surface; record this as an ADR so it is not undone casually.
- Several sources were read at abstract or summary level only (FIDES, Six patterns, Cedar, ASL beyond the first example, Starlark spec); the CaMeL GitHub README fetch returned 404. Any quote in product copy must be re-verified from the full paper first.
- The Temporal staff statement on untrusted workflows is from 2020 and may be outdated.

## Sources

- CaMeL abstract: https://arxiv.org/abs/2503.18813 ; HTML: https://arxiv.org/html/2503.18813
- FIDES: https://arxiv.org/abs/2505.23643
- Design patterns: https://arxiv.org/abs/2506.08837 ; https://arxiv.org/pdf/2506.08837
- Agents Rule of Two: https://ai.meta.com/blog/practical-ai-agent-security/
- Lethal trifecta: https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- Temporal workflow definition: https://docs.temporal.io/workflow-definition
- Temporal Python sandbox: https://docs.temporal.io/develop/python/python-sdk-sandbox
- Temporal community on untrusted workflows (2020): https://community.temporal.io/t/untrusted-workflow-execution/580
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph advisories: https://github.com/langchain-ai/langgraph/security/advisories
- Secondary on CVE-2026-48775 / CVE-2025-64439: https://www.sentinelone.com/vulnerability-database/cve-2026-48775/ ; https://advisories.gitlab.com/pypi/langgraph-checkpoint/CVE-2025-64439/
- CEL spec: https://github.com/google/cel-spec/blob/master/doc/langdef.md
- Starlark: https://github.com/bazelbuild/starlark
- Cedar terminology: https://docs.cedarpolicy.com/overview/terminology.html
- Amazon States Language: https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html
- Orcheo restricted workflows (search result only): https://orcheo.readthedocs.io/en/latest/sandboxed_custom_workflows/
