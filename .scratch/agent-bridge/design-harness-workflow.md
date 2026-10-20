# Harness as an automated workflow: engine, format, security, authoring (design v3-A)

Date: 2026-10-07. Status: design proposal, nothing here is built or measured. Replaces architecture-v2 section 5.2 `phases:` block and the "folder with prompt + tools" definition of a harness. Companion inputs: `architecture-v2.md`, `../decisions.md`, `research-v3/01..03`, `research-v2/`, and the audit findings (traceability in Appendix B).

Conventions. Everything about agent-bridge (names, thresholds, field names, check names, defaults) is our own PROPOSAL and untuned. External facts are only those already cited in research-v3/01-03 with their URLs (listed in Appendix C); this document introduces no new external claims and no new web research. Things not confirmed from a primary source are marked UNVERIFIED. Example YAML in section 2 is illustrative and has not been run through any analyzer (none exists yet).

TL;DR (tieng Viet). Chu nhan dung: harness khong phai "thu muc prompt + tool" va cung khong phai 3 pha co dinh. Harness la mot CHUONG TRINH workflow viet bang du lieu (do thi co kieu: buoc, nhanh, vong lap co chan, fan-out, gate kiem chung, diem dung cho nguoi, ngan sach, checkpoint), duoc mot ENGINE tin cay do chung ta viet (`flowd`, phia requester, ben canh sidecar) chay. Model chi dien noi dung trong tung buoc; engine so huu thu tu, vong lap, dieu kien dung, retry, ngan sach, luu trang thai ben vung (journal) va resume. Quyen han (tool, memory lens, model, ngan sach) khai bao theo tung buoc va duoc sidecar thi hanh duoi tang model; pack khong the mo rong quyen. Phan 3 la engine, phan 4 la phan tich tinh luc publish, phan 8 la nhung gi khong the bieu dien, phu luc A la ra soat hanh vi (behavioral flow) toan he thong.

---

## 0. Reading guide and the decisions this document takes

Where research-v3 files disagree, this document picks one and says so.

| # | Decision | Alternatives rejected | Why |
|---|---|---|---|
| W1 | A harness is a signed workflow program (data) plus step contents plus policies plus a capability envelope. The three phases become one template. | Phases block; "folder + tools"; harness-as-code | Owner feedback; control flow must be inspectable, enforceable below the model, certifiable (research-v3/01, /02). |
| W2 | The engine is our own small interpreter `flowd`, running in the requester's sidecar process group as its own OS user. It is not inside the Supervisor and not inside the Cell. | Embed LangGraph or Temporal; runner inside the Cell (research-v3/03 s3.3); engine inside Supervisor | Control flow inside the Cell is pack-influenced; embedding runtimes puts pack-authored code in the TCB and brings deserialization advisories (research-v3/02 B). Supervisor must keep a minimal kill path. |
| W3 | `flowd` is a pure function of the run journal (stateless between events). The Supervisor is the only journal writer, signer, lease holder, outbox owner and kill authority. | flowd owns its own store | A tampered or crashed flowd cannot rewrite history; restart equals replay; matches the Temporal/Inngest model of recorded history (research-v3/01 B). |
| W4 | For tier-0 packs, `llm` steps run in flowd's own bounded agent loop (trusted code). Pack-supplied code runs only as leaf `code` steps or `adapter` steps inside a Cell. | Run every agent loop inside the Cell | A tier-0 pack then executes no pack code at all; every model turn and tool call is journaled by trusted code, which makes turn-level replay and Progress Guard possible. Cost: our loop must be good with Nemotron tool calling (UNVERIFIED, smoke test needed). |
| W5 | Graph shape is structured: sequence, branch, bounded `loop` block, bounded `map`, static `parallel`. No arbitrary back-edges, no dynamic graph creation in v1. | General graphs (LangGraph style); dynamic subgraphs | Termination, worst-case cost and label analysis stay decidable. |
| W6 | Only typed, labelled values cross steps. Free text is a typed field with a size cap and a label. | Free-form context hand-off | Fresh-context isolation only works if what crosses is narrow (research-v3/02 F1). |
| W7 | Gates have trust classes. Only platform-implemented (P) and requester-supplied (R) checks can drive milestones, money or acceptance. Pack-supplied graders (K, J) steer loops only. | Pack-declared acceptance checks | Verification theater (research-v3/03 F11; audit TK-F1). |
| W8 | Budgets are hierarchical with an engine-held reserve; the first cap hit moves the run to WINDING_DOWN and a deterministic partial result is assembled with no model call. | Single token pool | Audit PR-F9. |
| W9 | One pause mechanism: the `human` node. Every timeout maps to a no-fault outcome unless deterministic evidence says otherwise. | D6 pause with kill-on-timeout | Audit AD-F3, HI-F5, PR-F7. |
| W10 | Three separated signal families: Progress Guard (stuck, budgets: nudge/replan/abort, never a reputation penalty), infra faults (retry/freeze, no strike), security detectors (kill/quarantine). Each carries an evidence class. | One detector table | Audit AD-F1/F3, research-v3/03 F6. |
| W11 | Run state lives in a requester-side Run Store (plane R), device-local, supervisor-written, never pack-writable, never replicated. Resume = journal replay under a lease epoch. | Pack-writable durable workspace; multi-device resume | Audit LC-F6, PR-F1, TK-F6, TK-F7. |
| W12 | The output contract is platform-owned (closed registry of output kinds). A pack's `result_schema` may only narrow it. | Pack-declared schema and checks | Audit TK-F1. |
| W13 | v1 excludes: pack-to-pack delegation, connectors with credentials, web access in the same scope as lens data, dynamic plan expansion, model-spawned sub-agents. Each has a designed hook (section 8). | Include everything | Keeps the TCB small. |

---

## 1. What a harness is (definition)

### 1.1 The owner's criticism, restated

architecture-v2 s5 defines the harness as prompts, skills, a three-phase policy and a tool list. That is a static configuration. It has no steps with typed results, no loops with exit conditions, no verification step, no durable state, no retries or budgets enforced outside the model, no human checkpoints and no resume. The sources agree that these are what separate a workflow that finishes hard tasks from a long prompt (research-v3/01 Summary; research-v3/03 s1: every serious long-horizon harness is a loop with an environment-grounded verify step, durable state outside the context window, hard budgets, stuck detection, and an exit the model does not decide alone). The criticism is correct and this document replaces the definition.

### 1.2 Definition

> A **harness** is a content-addressed, signed program in a closed workflow language. It consists of four layers:
> 1. **Workflow graph** (`workflow.yaml`): steps, typed state, edges, bounded loops, fan-out, gates, human checkpoints, milestones.
> 2. **Step contents**: prompts, skills, schemas, rubrics, few-shot demos, fixed code leaves, tool-catalog selections. This is the H plane that the improvement loop edits.
> 3. **Policies**: retry, timeout, budget, stuck, context, human-wait, recovery.
> 4. **Capability envelope**: per-step grants of tools, memory lens, model class, mounts, network class. The union is the manifest ceiling shown on the approval card.
>
> An **agent** is a model (pinned id) plus the executors that run its steps. A **pack** is a harness plus manifest, evals, license and provenance. The **engine** (`flowd`) is platform code, not part of the pack, versioned and certified separately.

What the harness controls: what is done, in which order, with which authority, and when it is considered done (gates and milestones, not the model's say-so). What it does not control: what the model says inside a step, and anything below the sidecar (permissions are a request, never a grant, architecture-v2 s5.2).

### 1.3 Assurance classes (computed by the analyzer, shown on the listing, ranked separately)

| Class | Meaning | Contents allowed |
|---|---|---|
| S static | Every step is `tool`, `code` (leaf), `gate`, `human`, or a bounded `llm` step (tool allow-list of at most 6 read-only catalog tools, at most 25 turns, no effects) | Strongest; fully analyzable |
| E enveloped | S plus a plan-expansion step validated against an envelope | Reserved, not in v1 (section 8) |
| O opaque | Contains an `adapter` step (third-party runner loop in a Cell) or an `llm` step above the bounded limits | Allowed; lowest assurance; detectors and sandbox carry the load; Progress Guard is partly blind (section 3.9) |

This extends the tier 0 / tier 1 split (data-only vs code-bearing) and the assurance ordering in research-v3/02 F13. The two axes are independent: tier 1 with only `code` leaves can still be class S.

### 1.4 What changes against architecture-v2

| v2 | Now |
|---|---|
| 5.2 `phases: {plan, work, return}` | `workflow:` graph; `plan-work-return` is a built-in template |
| Memory rights per phase | Per step (section 6.1) |
| Pack decides when it is done (returner phase) | Gates and engine-owned progress list decide; Accept is outside the graph |
| T scratch destroyed at end; kill/crash loses everything | Run Store R plus journal; defined resumable vs terminal outcomes |
| Acceptance checks authored by the pack | Platform check library plus requester checks; pack checks can only add strictness |
| One cap pool in the Model Proxy | Hierarchical budgets, reserve, cap precedence |
| D8 statistical sequence anomaly | Declared graph is the baseline; off-graph is deterministic evidence |
| Pause = freeze, default kill | `human` node, no-fault timeout outcomes |
| `/in` snapshot for the whole lens | Per-step grants; Broker-only data path for tier 0; accounted `materialize` for tier 1 (section 3.4) |

---

## 2. The workflow format (v1)

### 2.1 File format and digest rules

- Authoring format: JSON, or a **strict YAML subset**: mappings, sequences, JSON-compatible scalars only; no anchors, aliases, tags or merge keys; no duplicate keys; strings that YAML 1.1 would coerce (`no`, `on`, `1.10`) must be quoted or the file is rejected. One shared parser library is used by the validator, hub, supervisor and flowd, with a conformance corpus (audit LC-F12).
- Canonical form for validation: LF line endings only, no CR in any pack file; non-canonical input is rejected, not normalized. The pack digest is SHA-256 over the raw bytes of every file (no normalization), so D9 (pack drift) compares raw bytes against the same definition (audit LC-F12, AD-F11 Windows hashing).
- The digest covers workflow, step contents, policies, envelope. It excludes certification facts, price and listing metadata (those are separate signed documents; audit LC-F5). `model.tested_on` is deleted from the manifest.
- A capability-set hash is computed by the analyzer over: union of tools, namespaces, max sensitivity, network classes, output kinds, proposal schema, adapters and runner image digests, model classes, declared max USD and approval budget. Approval binds to it (section 3.3, audit LC-F4).

### 2.2 Types, values and labels

Types: `bool`, `int{min,max}`, `num{min,max}`, `enum[...]`, `str{max_len,pattern}`, `text{max_bytes, flavor: plain|md_subset|code}`, `list<T>{max_len}`, `object{...}`, `ref{artifact|record|source}`, `hash`. JSON Schema subset files (`schemas/*.json`) describe objects; no `$ref` outside the pack, no `additionalProperties: true`.

Every value in flight is `{data, type, label}` with `label = {integrity: trusted|untrusted, conf: set of {ns, sensitivity}, src: set of record ids and step ids}`. The engine computes labels; authors cannot set them. Rules (adapted from CaMeL/FIDES, research-v3/02 s4):

1. Step output label = join of input labels, the step's own source label, and the program-counter label (below).
2. Anything an `llm` step produced after reading an untrusted value is untrusted, regardless of intent.
3. Program-counter label: if a `branch` or `loop` condition depends on an untrusted value, every value produced inside the arms inherits that dependency (CaMeL strict mode). The analyzer additionally flags any such branch whose arms differ in tool set, sink or grants (control-flow channel).
4. Declassification (lowering conf or raising integrity) happens only via: (a) `extract`: a quarantined `llm` step whose output is an `enum`/bounded `int`, charged against a per-run declassification bit budget (`budgets.declassify_bits`, log2 of the enum size per call; CaMeL lists bit leakage through quarantined LLMs as a residual, research-v3/02 s4); (b) a `human` node; (c) a platform deterministic rule (count, bucket, round, hash). LLM judgement ("is this safe to share") is never a declassifier.
5. Label sets are capped (at most 64 src ids per value; overflow coarsens to a namespace-level label) so journals and analysis stay bounded.

### 2.3 Expressions

All conditions and field mappings use CEL with a cost limit (CEL cannot loop forever, is side-effect free, has bounded cost and is designed for untrusted expressions: https://github.com/google/cel-spec/blob/master/doc/langdef.md). Variables: `state.*`, `out.*` (current step output), `item.*`/`q.*` (map item), `gate.<id>.verdict`, `budget.remaining.*`, `run.iteration`, `task.*`. No clock, no randomness, no environment, no network. Regexes use an RE2-class engine (which engine: UNVERIFIED). Engine-provided recorded APIs (`now()`, `rand()`) exist only as journaled events and are unavailable inside expressions.

### 2.4 Top-level document

```
bridge_workflow: 1
id, engine{min,max}, assurance (declared; analyzer recomputes; mismatch = publish error)
task:       output kinds accepted, input slots, limits (ask_budget, quote_budget, max bytes)
budgets:    run{usd,tokens,active_s,waiting_s,steps,model_calls,tool_calls}, reserve{usd}, declassify_bits
policies:   retry, stuck, context, human, on_exit
state:      typed keys with reducers (replace | append{max_len} | merge | max | min | set_union); engine-owned keys marked owner: engine
scopes:     named capability scopes (optional), see 2.8
adapters:   third-party runners (pinned), tier 1 only
steps:      id -> step
milestones: gate-backed payment/progress milestones
```

State keys are declared with schema and reducer; a step may only read keys in `reads` and write keys in `writes`; the engine rejects undeclared writes. `progress` is an engine-owned feature list (the Anthropic initializer pattern: items start `passes:false`, https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents); an item flips to passed only through a committed gate, never by a step output claiming it.

### 2.5 Common step fields

| Field | Meaning |
|---|---|
| `kind` | one of the closed set in 2.6 |
| `reads`, `writes` | state keys and artifact names |
| `run_if` | CEL guard; false means the step is skipped and its `writes` stay unchanged |
| `next` or `edges` | successor; `edges` is an ordered list of `{when, goto}` plus a mandatory `default` |
| `grants` | the per-step capability envelope: `model`, `tools`, `memory`, `mounts`, `network` |
| `retry` | `{max, on[], backoff{initial_s,factor,max_s,jitter}, non_retryable[]}`; defaults from policies |
| `timeout` | `{step_s, idle_s}`; idle = no heartbeat (every model or tool call through a broker is a heartbeat) |
| `budget` | per-execution caps `{usd, tokens, turns, model_calls, tool_calls, active_s}`; totals across the attempts of one execution |
| `output` | `{schema, max_bytes}` (required for `llm`, `code`, `adapter`) |
| `effects` | declared durable effects (`propose_memory`, `emit_artifact`); applied by the engine at commit, never by the step |
| `context` | `fresh` (default) | `summary` (progress summary plus typed inputs); `inherit` is not allowed across steps |
| `on_error` | `{goto|fail|skip|human}` per error class |

### 2.6 Step kinds (closed set)

| Kind | What it does | Notes |
|---|---|---|
| `llm` | Bounded agent loop run by flowd: render prompt, call model via Model Proxy, execute tool calls via Tool Broker, finish by a `submit` call validated against `output.schema` | `role: quarantined` (no tools, no memory beyond inputs) or `privileged` (tools, sees only trusted-integrity inputs unless declassified). Caps: `turns`, tools list, `autonomy: bounded` computed. |
| `tool` | One deterministic tool call from the platform catalog, args built from typed values | Includes `memory.describe`, `memory.search`, `memory.propose`, `repo.materialize`, `workspace.diff`, `verifier.run` |
| `code` | Leaf code run in a nested no-network sandbox, typed JSON in, typed JSON out | Source is either a pack file (pinned in digest) or text from an upstream step (`source_from`); no sidecar socket (section 5) |
| `adapter` | Third-party runner loop (mini-swe-agent, deepagents, OpenHands SDK) run in a Cell with a model handle; yields assurance class O | Hard turn, USD, wall and idle caps |
| `gate` | Ordered checks, verdict `pass | fail | needs_human` | Section 2.7 |
| `branch` | CEL `edges` over typed fields | Label rule 3 |
| `loop` | Block with `body[]`, `until` (CEL or gate verdict), `max_iterations` (required), `stagnation`, `on_exhausted` | No other cycles are legal |
| `map` | Bounded fan-out over a typed list: `max_items`, `max_concurrency`, `item_budget`, `join`, `reducer`, `on_item_fail` | Each item gets a fresh context; Cell reuse follows 3.4 |
| `parallel` | Static fan-out of at most 4 named branches with `join: all | any | quorum(k)` | For voting and independent recomputation |
| `human` | Durable suspension: `mode: approve | ask | review`, typed `prompt_schema`, `show` fields, `timeout`, `on_timeout` | Section 3.10 |
| `return` | Produces the result: output kind, source state key; passes the Result Guard (section 2.9) | Ends the graph in RESULT_READY |
| `subflow` | Reserved (section 8) | |

Structural rules the validator enforces: every step reachable from `entry`; every path ends in `return` or an explicit `fail`; the only cycles are `loop` blocks; every `loop`, `map`, `parallel` is bounded; no step references grants beyond the manifest envelope.

### 2.7 Gates and the trust classes of checks

A gate runs its checks in order (deterministic first). Each check names a class:

| Class | Who implements and runs it | May drive milestones, money, acceptance | May steer loops |
|---|---|---|---|
| P platform | Platform check library, implemented inside flowd (trusted) | yes | yes |
| R requester | Requester-supplied in the TaskSpec; run by flowd or a throwaway no-network verifier cell with no vault access | yes | yes |
| K pack_code | Pack code run in a verifier sub-cell: artifact in, verdict out, no vault, no sidecar | no | yes |
| J llm_judge | Judge model in a fresh context with only the frozen artifact and a rubric; model must differ from the producing model id for certification | no (unless ANDed with P/R, and then only the P/R part counts) | yes |

Platform check library v1 (PROPOSAL): `schema_valid`, `size_within`, `regex_match`, `artifact_present`, `citations_resolve` (every cited id exists in the supplied source set), `numbers_reconcile` (every number in a text field is traceable to a typed value within tolerance), `row_count_reconcile`, `coverage_complete`, `numeric_agree`, `enum_in`, `quote_budget`, `no_outbound_refs`, `patch_applies_clean`, `patch_paths_policy`, `tests_not_modified`, `tests_pass` (R-class, delegated to a verifier cell), `failing_set_fixed`.

Anti-gaming rules: the artifact under test is frozen (content hash) before the gate runs and the gate result is bound to that hash; only the hash-matching artifact may flow to `return`; gate specs and rubrics live in the engine's read-only area, not in state a step can write; a step cannot write an artifact version after its gate (a new version is a new hash and must pass again); a gate failure routes via `on_fail` with the failing output as typed feedback and records a `fail_signature` (check id plus normalized message hash) for stagnation detection.

### 2.8 Scopes (web and private data never share a scope)

`scopes:` names capability scopes. A scope declares `data: none | lens` and `network_class: none | brokered_search`. The analyzer rejects any scope with both `data: lens` and a network class other than `none`, and rejects flows of values with non-empty `conf` into inputs of a scope with `brokered_search`. The legal pattern for tasks needing both is a PUBLIC scope (empty lens; inputs only from the requester's TaskSpec text; search goes through a Search/Fetch Broker with query logging, allow-lists, rate limits) producing untrusted-integrity typed outputs, followed by a PRIVATE scope with `network: none` that consumes them. Data moves from private back to public only through the Disclosure Compiler with a requester preview (audit TK-F8). The listing states which search provider sees public-scope queries. Fabricated sources are rejected by `citations_resolve` against the fetch log.

### 2.9 Task contract and the Result Guard (what the pack cannot define)

TaskSpec (set by the requester at hire, frozen and hashed into the approval): `output_kind`, `max_bytes`, `inputs` (lens, artifacts, `artifact_from_task(task_id, out_id)`), `instructions` (requester-authored text, label trusted), `limits` (`ask_budget`, `quote_budget`, caps), `checks` (R-class), `needs` (`web`, `write_targets`; connectors are not supported in v1), `audience` (UX default, not a boundary), `plan_approval` (bool).

Output kind registry (closed, platform-owned): `answer`, `report`, `table`, `patch`, `file_set`, `proposal`, `needs_input`. Each kind has a platform envelope schema, a size default and a guard:
- `report`: Markdown subset with no raw HTML, no images, no auto-links; URLs are stripped unless they appear verbatim in the task inputs or the requester allow-list; "result contains an outbound reference" is a deterministic strike detector (D15), not an automatic kill; the renderer is a static view with CSP `default-src 'none'`; links display their domain and need an explicit click.
- `patch`: diff parser with path allowlist; paths touching `.git/*`, hooks, CI config, package scripts, lockfiles, dotfiles, build scripts, symlinks or binaries are hard-flagged and need per-file approval; added URLs/hosts are flagged. A patch is never applied to the live tree by the pack or by Accept. Applying is the requester agent's act under its own policy, onto a throwaway worktree with a recorded `base_hash` (reject on drift), with install scripts and hooks disabled, followed by human diff review and an undo journal. Apply machinery is out of v1 scope; the contract above is what v1 guarantees (audit TK-F5, HI-F6).
- `needs_input`: a typed request `{question_id, kind: choose|confirm|short_text<=200, options[]}`; counts against `ask_budget`.

The pack's `result_schema` may only narrow the platform envelope. This is verified as a subschema relation at publish and certification; a wider schema is ignored at runtime. Effective acceptance checks = platform checks for the kind + TaskSpec checks + extra strictness the pack declares; a pack check can add strictness but can never remove or replace one. Accept is not a workflow node and not an agent tool: it is a human click or the deterministic rule "P+R checks passed and the accept window expired" (section 3.3).

### 2.10 Milestones

```
milestones:
  - {id, after: <gate id or block id>, require: {classes: [platform, requester], pass_fraction: 1.0}, weight_bp: 0..10000}
```
A milestone is reached only when committed gates of the listed classes passed on frozen artifacts. The engine journals `milestone_verified{evidence_hash}`; the Supervisor turns that into a capture request through its outbox. Weights sum to 10000. The author's price is fixed per accepted milestone, not per attempt or per token (audit LC-F6, PR-F9).

### 2.11 Reference harness 1: private-data analyst

Illustrative. Quarantined `llm` steps have no tools; the one place data meets code is a `code` leaf. Per-step grants are the point of the example.

```yaml
bridge_workflow: 1
id: acme/finance-analyst
engine: {min: "1.0", max: "1.x"}
assurance: static
task:
  kinds: [report, table]
  limits: {ask_budget: 2, quote_budget_bytes: 600}
budgets:
  run: {usd: 3.00, tokens: 1500000, active_s: 5400, waiting_s: 86400, steps: 220, model_calls: 420, tool_calls: 700}
  reserve: {usd: 0.06}
  declassify_bits: 24
policies:
  retry: {max: 2, on: [transient, invalid_output], backoff: {initial_s: 2, factor: 2.0, max_s: 60, jitter: full}, non_retryable: [policy_denied, fatal_security, budget_exceeded]}
  stuck: {same_action_obs: 4, action_error: 3, monologue: 3, alternating: 6, no_progress_turns: 12, ladder: [nudge, replan, human, abort]}
  context: {compact_at: 0.70, keep_tail: 0.15, max_compactions: 3, offload_history: true, reserve_out_tokens: 2000}
  human: {default_timeout_s: 86400, on_timeout: abort_clean}
state:
  profile:           {schema: schemas/profile.json,   reducer: replace}
  pending_questions: {schema: schemas/ask.json,       reducer: replace, max_len: 2}
  clarifications:    {schema: schemas/answer.json,    reducer: append,  max_len: 2}
  questions:         {schema: schemas/question.json,  reducer: replace, max_len: 12}
  findings:          {schema: schemas/finding.json,   reducer: append,  max_len: 12}
  report:            {schema: schemas/report.json,    reducer: replace}
  progress:          {owner: engine}
entry: describe
steps:
  describe:
    kind: tool
    tool: memory.describe                       # metadata only: names, types, counts; accounted by the Broker
    grants: {memory: {describe: {ns: [projects/atlas], tags: [finance], max_sensitivity: medium}}}
    writes: [profile]
    next: scope
  scope:
    kind: loop
    max_iterations: 2
    budget: {usd: 0.25}
    body: [plan, maybe_ask]
    until: "size(state.pending_questions) == 0"
    on_exhausted: {goto: confirm_plan}          # proceed; assumptions recorded in the receipt
    next: confirm_plan
  plan:
    kind: llm
    role: quarantined
    prompt: prompts/plan.md
    reads: [profile, clarifications]
    grants: {model: {class: reasoning, max_out: 2500, stream: false}}
    output: {schema: schemas/plan.json}         # {questions[<=12], needs_input[<=2]}
    budget: {usd: 0.12, turns: 1}
    writes: [questions, pending_questions, progress.init]
  maybe_ask:
    kind: human
    mode: ask
    run_if: "size(state.pending_questions) > 0"
    prompt_schema: schemas/ask.json             # question text is rendered inert and labelled "from pack, untrusted"
    timeout: {s: 7200, on_timeout: abort_clean}
    writes: [clarifications]
  confirm_plan:
    kind: human
    mode: approve
    run_if: "task.plan_approval"
    show: [questions]
    next: analyze
  analyze:
    kind: map
    over: state.questions
    item: q
    max_items: 12
    max_concurrency: 2
    item_budget: {usd: 0.18, model_calls: 30, active_s: 600}
    join: {mode: quorum, min_fraction: 0.75}
    on_item_fail: mark_unanswered
    reducer: {into: findings}
    body: [retrieve, solve, explain]
    next: draft
  retrieve:
    kind: tool
    tool: memory.search
    grants: {memory: {search: {ns: [projects/atlas], tags: [finance], max_sensitivity: medium, k: 8, bytes: 24000, min_tier: 1}}}
    args: {terms: "q.search_terms"}
    writes: [item.slices]
  solve:
    kind: loop
    max_iterations: 3
    stagnation: {same_fail_signature: 2}
    body: [dual_calc, cross_check]
    until: "gate.cross_check.verdict == 'pass'"
    on_exhausted: {mark_item: unanswered}
  dual_calc:
    kind: parallel
    join: all
    branches:
      a: [author_code_a, run_code_a]
      b: [author_code_b, run_code_b]            # different prompt and model class: independent path
  author_code_a:
    kind: llm
    role: quarantined
    prompt: prompts/calc_a.md
    reads: [item.slices, q]
    grants: {model: {class: reasoning, max_out: 1500}}
    output: {schema: schemas/code.json}         # {code: text<=4096 flavor code, unit: enum}
    budget: {usd: 0.015, turns: 1}
  run_code_a:
    kind: code
    runtime: python3-sandbox@sha256:<pinned>
    source_from: author_code_a.out.code
    mounts: [{from: item.slices, mode: ro}]
    limits: {cpu_s: 20, mem_mb: 512, pids: 32, out_bytes: 16384}
    output: {schema: schemas/calc_out.json}     # {value: num, unit: enum, rows_used: int}
  author_code_b: {kind: llm, role: quarantined, prompt: prompts/calc_b.md, reads: [item.slices, q], grants: {model: {class: judge, max_out: 1500}}, output: {schema: schemas/code.json}, budget: {usd: 0.015, turns: 1}}
  run_code_b:    {kind: code, runtime: "python3-sandbox@sha256:<pinned>", source_from: author_code_b.out.code, mounts: [{from: item.slices, mode: ro}], limits: {cpu_s: 20, mem_mb: 512, pids: 32, out_bytes: 16384}, output: {schema: schemas/calc_out.json}}
  cross_check:
    kind: gate
    checks:
      - {class: platform, check: schema_valid, of: run_code_a.out}
      - {class: platform, check: row_count_reconcile, args: {claimed: run_code_a.out.rows_used, observed: item.slices.row_count}}
      - {class: platform, check: numeric_agree, args: {a: run_code_a.out.value, b: run_code_b.out.value, rel_tol: 0.001}}
    on_fail: {feedback: true}
  explain:
    kind: llm
    role: quarantined
    prompt: prompts/explain.md
    reads: [q, run_code_a.out]
    grants: {model: {class: reasoning, max_out: 600}}
    output: {schema: schemas/finding.json}      # {claim: text<=400 plain, value_ref, refs[]}
    writes: [item.finding]
    budget: {usd: 0.02, turns: 1}
  draft:
    kind: loop
    max_iterations: 3
    budget: {usd: 0.40}
    stagnation: {same_fail_signature: 2}
    body: [write_report, check_report]
    until: "gate.check_report.verdict == 'pass'"
    on_exhausted: {goto: review_partial}
    next: propose
  write_report:
    kind: llm
    role: quarantined
    prompt: prompts/write.md
    reads: [findings, gate.check_report.feedback]
    grants: {model: {class: reasoning, max_out: 4000}}
    output: {schema: schemas/report.json}
    writes: [report]
    budget: {usd: 0.10, turns: 1}
  check_report:
    kind: gate
    checks:
      - {class: platform, check: schema_valid, of: state.report}
      - {class: platform, check: citations_resolve, args: {cites: state.report.cites, universe: state.findings.refs}}
      - {class: platform, check: numbers_reconcile, args: {text: state.report.body, values: state.findings.values, rel_tol: 0.001}}
      - {class: platform, check: quote_budget, args: {max_bytes: "task.limits.quote_budget_bytes"}}
      - {class: platform, check: no_outbound_refs}
      - {class: llm_judge, rubric: rubrics/report.md, model_class: judge, context: fresh}   # advisory
  review_partial:
    kind: human
    mode: review
    show: [report, gate.check_report.failures]
    timeout: {s: 86400, on_timeout: abort_clean}
    next: propose
  propose:
    kind: tool
    tool: memory.propose
    grants: {memory: {propose: {schema: schemas/proposal.json, max_items: 3}}}
    effects: [propose_memory]                   # run-wide cap of 3, idempotent by content hash
    next: finish
  finish:
    kind: return
    output_kind: report
    from: state.report
milestones:
  - {id: findings_verified, after: analyze, require: {classes: [platform], pass_fraction: 0.75}, weight_bp: 4000}
  - {id: report_verified,   after: check_report, require: {classes: [platform, requester]}, weight_bp: 6000}
```

Analyzer summary this file should produce (computed by hand from the declared caps: map 12 x 0.18 = 2.16, scope 0.25, draft 0.40, reserve 0.06): worst-case USD 2.87, declared 3.00, accepted. Human cards at most 2 (ask) + 1 (plan) + 1 (review) = 4, plus Accept. Assurance S. Steps that send private text to the model provider: plan, author_code_a/b, explain, write_report (shown on the card; the model call is a sanctioned sink, not an attacker-directed one, see 4.5). Rule of Two: no step has external communication or state change except `propose` (schema-bound, run cap 3) and `return` (Result Guard), so the A+B+C trifecta does not occur.

### 2.12 Reference harness 2: code patcher

Tier 1 (code-bearing adapter), assurance O. Illustrative.

```yaml
bridge_workflow: 1
id: acme/patch-smith
engine: {min: "1.0", max: "1.x"}
assurance: opaque                               # contains an adapter step
task:
  kinds: [patch]
  inputs: {repo: {kind: git_snapshot, required: true}, issue: {kind: text, max_bytes: 8000}}
  limits: {max_patch_bytes: 262144, ask_budget: 1}
budgets:
  run: {usd: 4.00, tokens: 2500000, active_s: 7200, waiting_s: 86400, steps: 120, model_calls: 300, tool_calls: 900}
  reserve: {usd: 0.05}
adapters:
  swe: {runner: mini-swe-agent, source: {repo: SWE-agent/mini-swe-agent, sha: "<pinned>", license: MIT}, image: "sha256:<pinned>"}
policies:
  stuck: {same_action_obs: 4, action_error: 3, monologue: 3, no_progress_turns: 10, ladder: [nudge, replan, human, abort]}
  human: {default_timeout_s: 86400, on_timeout: abort_clean}
state:
  base:     {owner: engine}                      # {artifact: repo@base_hash}
  baseline: {schema: schemas/baseline.json, reducer: replace}   # {failing[], passing_count}
  suspects: {schema: schemas/suspects.json, reducer: replace}
  attempts: {schema: schemas/attempt.json,  reducer: append, max_len: 4}
  flags:    {schema: schemas/flags.json,    reducer: replace}
entry: materialize
steps:
  materialize:
    kind: tool
    tool: repo.materialize                      # accounted broker op; snapshot hashed; base_hash recorded
    grants: {memory: {materialize: {ns: [repos/current], max_sensitivity: high, bytes: 200000000}}}
    writes: [base]
    next: baseline
  baseline:
    kind: tool
    tool: verifier.run                          # requester's test command, throwaway no-network cell, pristine snapshot
    reads: [base]
    writes: [baseline]
    next: locate
  locate:
    kind: llm
    role: privileged
    prompt: prompts/locate.md
    reads: [base, baseline, task.issue]
    grants: {model: {class: reasoning, max_out: 1500}, tools: [fs.read, fs.grep]}     # read-only catalog tools
    output: {schema: schemas/suspects.json}     # {suspects: list<path>(<=10), hypothesis: text<=800}
    budget: {usd: 0.30, turns: 15}
    writes: [suspects]
    next: fix
  fix:
    kind: loop
    max_iterations: 4
    budget: {usd: 3.00}
    stagnation: {same_fail_signature: 2}
    body: [attempt, diff, verify]
    until: "gate.verify.verdict == 'pass'"
    on_exhausted: {select: min_failing, mark: partial, goto: review}
    next: review
  attempt:
    kind: adapter
    adapter: swe
    reads: [base, suspects, gate.verify.feedback, task.issue]
    workspace: {from: base, mode: rw_overlay}   # writable overlay; base is never modified
    grants: {model: {class: reasoning, max_out: 3000}, network: none}
    limits: {turns: 30, usd: 0.60, active_s: 900, idle_s: 120}
    output: {schema: schemas/attempt.json}      # {summary: text<=1200}
    writes: [attempts]
  diff:
    kind: tool
    tool: workspace.diff                        # engine-run, deterministic; freezes the patch artifact by hash
    writes: [patch]
  verify:
    kind: gate
    checks:
      - {class: platform,  check: patch_applies_clean, args: {base: state.base}}
      - {class: platform,  check: patch_paths_policy,  args: {allow: task.write_allowlist}}
      - {class: platform,  check: tests_not_modified}
      - {class: requester, check: tests_pass}                    # requester-supplied command, verifier cell
      - {class: platform,  check: failing_set_fixed, args: {baseline: state.baseline}}
    on_fail: {feedback: true}
  review:
    kind: human
    mode: review
    run_if: "size(state.flags.hard) > 0 or task.human_review or state.attempts.partial"
    show: [patch.summary_by_class, state.flags]                 # per-file approval only for hard-flagged paths
    timeout: {s: 86400, on_timeout: abort_clean}
    next: finish
  finish:
    kind: return
    output_kind: patch
    from: state.patch
milestones:
  - {id: patch_verified, after: verify, require: {classes: [platform, requester]}, weight_bp: 10000}
```

Notes. The `attempt` adapter runs in a Cell with the worktree overlay writable and a model handle bound to the step token; it has no network and no sidecar socket other than the model proxy. flowd sees its model calls, wall time and result, not its internal bash calls, so Progress Guard on adapters uses model-call-level signals only (section 3.9). `verify`'s test execution happens in a fresh verifier cell that holds neither vault data nor a sidecar socket, because test runs execute pack-influenced code (audit PR-F4). Because tests are requester-supplied and run on the requester machine, the milestone is requester-attested; that is the Pull limit, not something the workflow can fix (section 6.2).

### 2.13 Templates and archetypes shipped with the platform

Templates (authors start from one, never from a blank graph; from research-v3/01 and /03):
1. `plan-work-return`: `plan` (quarantined llm) -> `work` (bounded llm with the lens) -> `check` gate -> `return`. The old v2 three-phase pack compiles to this.
2. `plan-map-reduce`: orchestrator-workers with a gate per item.
3. `generate-verify-refine`: evaluator-optimizer loop with stagnation exit.
4. `long-task`: initializer plus incremental units: engine-owned feature list, one item per iteration, per-item gate, milestone per verified item, progress file, journal-backed resume (the Anthropic long-running shape).
5. `route-then-specialist`: enum-extracting quarantined router, `branch`, specialist sub-blocks.

Archetypes (reference packs with deterministic acceptance tests, research-v3/03 s5): A private-folder data analyst (section 2.11), B code patcher (section 2.12), C research/report writer (public scope then private scope, `map` researchers, `citations_resolve`), D document processor (`map` over files with checkpoint every N, per-item gate, low-confidence items to `human`, `coverage_complete` check).

---

## 3. The trusted engine (`flowd`)

### 3.1 Where it runs and what is trusted

```
REQUESTER MACHINE
+-------------------------------------------------------------------------------+
| Supervisor (OS user A; minimal code)                                          |
|   Run Store writer (hash-chained signed journal, blob store), lease holder,   |
|   outbox (hub + payment calls), reconcile-on-start, kill/ladder authority     |
|        ^ events (append, acked after fsync)         | commands: pause/cancel/  |
|        |                                            v resume/kill               |
| flowd (OS user B; own seccomp profile; no NIC; unix sockets only)             |
|   scheduler, CEL evaluator, label engine, schema validator, gate runner       |
|   (P/R), llm executor (bounded agent loop), Progress Guard, budget ledger,    |
|   context manager, effect planner                                             |
|        | step token sockets                                                     |
| Sidecar services: Model Proxy | Memory Broker | Tool Broker | Egress Proxy |  |
|   Result Guard | Sensor Hub + detectors  (all step-token aware)               |
|        |                                                                        |
| Cells (untrusted): step executors only for `code` and `adapter`, plus         |
|   throwaway verifier cells. Never decide control flow.                        |
+-------------------------------------------------------------------------------+
```

- flowd is in the sidecar process group but a separate OS user from the Supervisor and from the Cell driver; the audit/journal signing key lives with the Supervisor (audit ID-F11: the key must not sit on the host user the Cell can reach). The journal head is periodically anchored outside the Cell host user's reach (coarse hash to the hub, optional paired device) to detect tail truncation (audit PR-F12).
- flowd has no network. Its only I/O is unix sockets to the Supervisor, the brokers and the Cell executor channel. It therefore cannot itself become an exfiltration path.
- On Windows 11 Home the process placement (flowd in the WSL2 VM next to the sidecar, Supervisor on the host or in a separate VM user) is tied to the driver ADR (architecture-v2 phase 3); not decided here.
- TCB supply chain: flowd and the analyzer are released under the offline TCB signing key with the other TCB parts; updates are opt-in and downgrade-refusing (audit ID-F2). Engine bugs (expression evaluation, template rendering, label join, schema validation) are the new exploit surface (research-v3/02 F7); mitigations: memory-safe language (Rust or Go; UNVERIFIED which, section 9), a few thousand lines, fuzzing of parser and template renderer, differential tests of the label join and CEL evaluation, a conformance suite (3.15).
- Hosted: the engine runs under the host's root, so the engine's static guarantees do not protect the packet from the host and verdicts are host-attested (section 3.13).

### 3.2 The run record, journal and Run Store (plane R)

The Supervisor keeps one write-ahead row per run: `run_id, state, workflow digest, capability-set hash, approval hash, model id, engine version, hub token id, authorization id, lease epoch, cell labels, stage path, journal head hash`, fsynced on every state transition before the side effect it announces. On start it reconciles (audit PR-F1): list cells with the bridge label and kill those whose run is not RUNNING; wipe stage dirs with no live run; for runs in STAGED or RUNNING with no valid lease, mark SUSPENDED and offer resume (section 3.6) or void; for SETTLING, resume the outbox.

Journal: append-only, typed JSON lines, never deserialized into objects (LangGraph's checkpoint-loading advisories show the risk of loading state as objects: https://github.com/langchain-ai/langgraph/security/advisories). Each line: `{run_id, seq, epoch, mono_ms, wall, type, step_path, attempt, payload, prev_hash, sig}`. Framing is length-plus-CRC with fsync; on open, an incomplete final frame is truncated and a `recovery_marker` event recorded; only a mid-chain hash mismatch is tamper (audit AD-F8). Event types: `run_created, admitted{approval_hash}, authorized, lease_acquired{epoch}, step_scheduled, step_started, turn_model{req_hash,resp_blob,usage}, turn_tool{...}, step_staged{out_hash}, gate_result{class,evidence_hash}, step_committed{out_hash,state_delta_hash,labels,budget_used}, effect_intent{key}, effect_done{key}, human_requested, human_resolved, pause, resume, stuck_signal, detector_event{id,class}, suspend_gap{mono_gap_ms}, infra_fault, milestone_verified{evidence_hash}, run_outcome{outcome,reason}`.

Blobs (model responses, tool results, artifacts) are content-addressed in the Run Store, encrypted under a per-run key, and each records `derived_from_key_ids` (the vault record keys of the data they were derived from). Plane R is device-local: it is not replicated with the vault and never read by a pack (audit TK-F6 asks for exactly this plane). Retention: R of a COMPLETE or ABORTED run is wiped at the end of the settlement window; R of a KILLED run is quarantined (hashes plus a metadata diff by default; plaintext only on user opt-in, encrypted under a shreddable key); a TTL applies to everything. Journal events pass the same secret scanner as vault capture before blob storage (audit MM-F8).

### 3.3 The Run object, state machine and lease

Run states (supervisor-owned; flowd sees them as commands and events):

```
CREATED -> ADMITTED -> AUTHORIZED -> RUNNING <-> {PAUSED_HUMAN, STALLED, SUSPENDED}
RUNNING/PAUSED/STALLED/SUSPENDED -> WINDING_DOWN -> RESULT_READY -> ACCEPT_PENDING -> SETTLED | VOIDED
terminal outcome (written once, absorbing): COMPLETE | PARTIAL(reason) | FAILED_PACK | FAILED_INFRA | ABORTED_CLEAN | KILLED(evidence_class)
```

Hire order (fixes audit PR-F3, LC-F6, ID-F8, TK-F7): (1) requester mints `run_id` (ULID) and freezes the TaskSpec; every hub and payment call carries idempotency key `run_id+op`, sent as the PayPal-Request-Id header, and the hub stores `(run_id, op) -> response`. (2) Local preflight (3.11): analyzer re-run, model pinned and reachable, driver conformance subset, disk/RAM/concurrency admission, revocation list fresh enough for the lens sensitivity, input snapshot staged and hashed. (3) Approval card computed from the workflow and signed: `approval_hash` over `{workflow digest, capability-set hash, mode, lens definition, snapshot manifest hash (record id, version, content hash), TaskSpec hash, budgets and price cap with quote id, model id, engine version, driver tier and conformance run id, run_id, expiry}`. Staging precedes the card, so the card shows bytes that are already fixed; a different hash at launch re-prompts (audit HI-F2, PR-F5). (4) Hub AUTHORIZE at the cap; returns a hub-signed run token bound to `{run_id, digest, mode, cap, canary seed commitment, expiry}`. (5) Supervisor writes the run row, starts flowd, takes `epoch=1`; the first `step_started` produces the STARTED ack. Until then the token may be re-bound to the same `run_id` and the same hold, and a hub reaper voids holds with no STARTED within N minutes (audit PR-F3).

Lease (audit LC-F6, TK-F7, ID-F8): the one-time token only starts the run. The Supervisor holds a run-lease `(run_id, digest, last checkpoint hash, epoch)`; the hub allows one live lease per run id; resume increments `epoch`; hub, relay and payment calls with a stale epoch are rejected. In v1, resume from a replicated journal on another device is forbidden (a second device may view or cancel only). Terminal states absorb: a late Accept, capture, cancel or receipt after a terminal state is a logged no-op. Accept and kill are mutually exclusive through a compare-and-set on the single run row (money ledger is the payments design's, this row is its anchor).

Outcome table (the engine emits outcome plus the verified-milestone list; settlement amounts belong to the payments design, the right column is the proposed interface):

| Outcome | Trigger | Cell | R plane | Memory/Q | Fault assigned | Proposed settlement input |
|---|---|---|---|---|---|---|
| COMPLETE | `return` committed, Result Guard ok | destroyed | wiped after window | proposals to Q | none | all milestones |
| PARTIAL(budget) | a cap hit; partial assembled | destroyed | kept to window | committed proposals only | none | verified milestones only; unverified items listed separately |
| PARTIAL(cancel) | user cancel; grace then WINDING_DOWN | destroyed | kept to window | Q of the run discarded unless kept | none | verified milestones only |
| PARTIAL(human_timeout) | human wait exceeded | destroyed | kept to window | as above | none | verified milestones only |
| PARTIAL(revoked_drain) | pack deprecated or yanked, drain current step | destroyed | kept | as above | none | verified milestones only |
| FAILED_PACK | unrecoverable: gates exhausted with no human path, repeated invalid output | destroyed | kept | Q discarded | pack (no reputation effect unless Progress Guard repeats across requesters, which is a ranking input, not a strike) | none |
| FAILED_INFRA | Cell/driver/model/disk faults after recovery cap | destroyed | kept for resume | untouched | none | void, no strike |
| ABORTED_CLEAN | pause timeout or user "abort clean" | destroyed | wiped | Q discarded | none | void minus requester-side non-refundable floor (payments design) |
| KILLED(e) | deterministic evidence (tamper, egress, drift) | destroyed after snapshot | quarantined | Q discarded; run-scoped revert list (6.1) | pack only if evidence is hub-checkable (6.2) | hold, not void, until adjudication |

### 3.4 State, blackboard and the step execution protocol

State lives with flowd as a projection of the journal: typed keys with reducers; each step receives a projection of its declared `reads` only. A step never sees the blackboard.

One step execution:
1. flowd emits `step_scheduled`; the Supervisor appends it. flowd asks the Broker, Tool Broker and Model Proxy to mint step-scoped handles: a Biscuit attenuated to `{run_id, step_path, attempt, epoch, namespaces, field mask, quota, expiry in seconds}` (attenuation only: no step can exceed the run capability; the Biscuit is never persisted, it is re-minted on resume).
2. `step_started` appended (fsync) before any work.
3. Execution by kind: `llm` in flowd's loop; `tool` via Tool Broker; `code`/`adapter` via the Cell executor channel with only typed inputs and handles.
4. Output arrives as a staged value; flowd validates against `output.schema`, applies size caps and label join, runs canary scan on typed values (6.2). Invalid output is `invalid_output` (one repair attempt carrying the validator error, then retry per policy).
5. `step_staged{out_hash}`; gates and effect planning; then `step_committed` (fsync) carrying the state delta and effect intents. Only after commit does state change and only after commit are effects applied (3.7).

Cell reuse: a Cell session may serve consecutive `code`/`adapter` steps only if the data capability class (lens, mounts, network class) is identical; any change starts a fresh Cell (or re-mount plus fresh sidecar capability). Tier-0 steps need no Cell. The old `/in` whole-slice mount no longer exists: for tier 0 all data comes through `memory.search`/`memory.describe`; for tier 1 files appear only through an accounted `materialize(selector)` op writing into the step's own tmpfs. A `cat /in/*` in a non-data step fails because nothing is mounted there (audit PR-F6, CO-F2, MM-F2).

### 3.5 The llm executor (flowd's agent loop)

Per turn: render (3.12), reserve budget, call the Model Proxy with the step token, parse the response (native tool calling if the model supports it reliably, else a JSON-schema-constrained response; which holds for Nemotron on Nebius is UNVERIFIED and gets a smoke test), execute allowed tool calls through the Tool Broker (not in `grants.tools` is a D3 deny), journal the turn, loop until a `submit(output)` call validates, or a cap hits. `max_consecutive_format_errors` defaults to 3 (mini-swe-agent default, research-v3/03 s2.6), after which the step fails `invalid_output`. Identical repeated `memory.search` within one step returns the memoized result and is not charged again to D4 volume counters, which removes the main source of Progress-versus-security false positives (research-v3/03 F6).

### 3.6 Checkpoint and resume

Every `step_committed` is a checkpoint (memoized result, as in Inngest's step memoization, https://www.inngest.com/docs/learn/how-functions-are-executed). Resume algorithm (flowd restart, Supervisor restart, device wake, explicit resume):
1. Supervisor verifies the journal chain and signature; flowd rebuilds state by folding `step_committed` events.
2. Resume checklist before any step runs (audit TK-F6, LC-F1): pack not revoked or yanked by a reason that blocks (3.14); workflow digest and engine major equal (otherwise refuse, never patch); model id still available (else INFRA_FAULT, section 3.9); input snapshot hash equal or the user approves a re-snapshot (a re-snapshot is a new approval); revocation freshness; hold status and honor window (3.10); run token re-validated; Biscuits re-minted; quarantine and strike state re-read.
3. The first step without `step_committed` is re-executed with `attempt+1`. For an `llm` step the executor replays recorded turns from the journal (model responses and tool results come from blobs, tools are not re-run) and continues live from the first unrecorded turn; this works because the loop is our deterministic code. `code` steps restart from the start; `adapter` steps restart from the start (their internals are opaque).
4. Terminal-by-security outcomes (KILLED) are never resumed or replayed (audit F7 of research-v3/01: policy_denied and fatal must not re-fire strikes). Strike and detector events carry unique ids and are not regenerated by replay.
5. Resumable outcomes: crash, flowd restart, device sleep, budget soft-stop, human wait, STALLED. A resumed run takes a new epoch.
6. Shred and invalidate events during a run: the engine subscribes to vaultd events. A shredded key marks dependent blobs (`derived_from_key_ids`) deleted and invalidates the steps that consumed them; the run re-executes those steps against a refreshed snapshot (needs re-approval) or is discarded. Per-record `base_versions` ride on proposals so stale proposals are flagged on promotion. For records of sensitivity high or secret in the active lens, invalidation or reclassification pauses the run at the next step boundary and raises a card; default on timeout is abort-clean (audit PR-F5, MM-F2).
7. Chaos resume is a Certifier test (kill flowd at a random event index; outcome and state must equal an uninterrupted run modulo model nondeterminism, which is eliminated by replaying recorded turns).

Journal growth is bounded: blob size caps per turn, tool-result clearing in context (3.12), retention TTL, and a migration rule: journal lines carry `schema_version`; flowd upcasts at read time; journals are not migrated in place and a run whose journal is older than the engine's supported window is refused for resume (audit MM-F11, MM-F12).

### 3.7 Idempotency and effects

Steps produce typed outputs plus declared effect intents; they never perform durable effects themselves. At commit, flowd emits `effect_intent{key}` with `key = H(run_id, step_path, iteration_path, input_hash)`; the Supervisor applies the effect (Q write, artifact emit) idempotently by key, then appends `effect_done`. On restart, intents without `effect_done` are reconciled against the target by key and then applied. Consequences: an abandoned or killed step has no effects; a retried step cannot duplicate a proposal; memory proposals are idempotent by content hash and counted per run across all iterations and map items (audit research-v3/01 F8). Tools with external effects are not present in v1 private runs; when they appear they must be idempotent under a key and are forbidden in retried steps unless declared so (research-v3/02 F2).

### 3.8 Retries, error classes and strikes

| Class | Examples | Retried by | Counts to budget | Strike or fault | Unrecovered outcome |
|---|---|---|---|---|---|
| `transient` | model 5xx/timeouts after the proxy gave up, executor channel loss | step policy, backoff with jitter (Temporal-style defaults for reference: 1s initial, factor 2.0, https://docs.temporal.io/encyclopedia/retry-policies; ours are `retry.backoff`) | yes, except infra-attributed retries (charged to `infra_overhead`, not to the requester or author) | none | STALLED then FAILED_INFRA |
| `invalid_output` | schema failure, oversized output | one repair, then step policy | yes | none (Progress signal) | FAILED_PACK if loop exhausted |
| `gate_fail` | any failed check | loop semantics | yes | none | per `on_exhausted` |
| `budget_exceeded` | step/scope/run cap | not retried | n/a | none | PARTIAL(budget) |
| `step_timeout`, `idle_timeout` | no heartbeat or wall cap | once if policy allows | yes | Progress signal | per policy |
| `policy_denied` | broker or tool deny (D3, D1) | never | no | detector accounting only; never re-fired by replay | step `on_error` |
| `resource_exhausted` | OOM, ENOSPC, disk quota | never auto | no | no strike, no author penalty | FAILED_INFRA |
| `fatal_security` | supervisor kill | never, never replayed | n/a | by evidence class (6.2) | KILLED |
| `human_timeout` | wait exceeded | n/a | n/a | none | per policy, default abort-clean |

Retry loops cannot be used to burn requester budget at no cost to the author (audit LC-F6): all retries sit inside per-step and block budgets, the analyzer proves worst-case cost is at or below the declared maximum, the engine enforces it, and the author's price is fixed per accepted milestone.

### 3.9 Progress Guard (stuck detection)

Input: the engine's own journal (never broker security accounting). Signals (thresholds are borrowed from OpenHands' StuckDetector and are untuned for Nemotron: same action and observation x4, action and error x3, monologue x3, alternating A/B x6, context-error loop; plus ours: `no_progress_turns` (no new committed state, no new progress item in N turns), loop stagnation (same `fail_signature` twice, or no improvement score), map item failure rate, idle heartbeat). Source of borrowed values: https://github.com/OpenHands/software-agent-sdk (stuck_detector.py), read in research-v3/03 s2.6.

Ladder: nudge (an engine-authored, trusted message appended to the context), force `replan` (jump to the declared `on_stuck` node), escalate to `human`, abort with partial result. No reputation penalty and no detector strike. Honest limits: for `adapter` steps flowd sees only model calls, wall time and the final result, so only repeated identical request hashes, monologue-like model output, idle and wall caps apply; the step's own loop detection (for example mini-swe-agent's limits) is configured but not trusted.

### 3.10 Human nodes, waits and the PAUSED_HUMAN family

A `human` node durably suspends the run (Inngest-style wait: no compute while waiting, `null`-like timeout result, https://www.inngest.com/docs/learn/how-functions-are-executed). Kinds and defaults (all numbers PROPOSAL):

| Kind | Channel | Default deadline | Default on timeout | Budget clock | Hold clock | Cell / Nebius |
|---|---|---|---|---|---|---|
| `approve` (plan or irreversible step) | card (desktop, phone via relay) | 24h | abort-clean | paused | runs; must be shorter than authorization expiry or the hub re-authorizes | Cell frozen or destroyed (steps that need no Cell have none) |
| `ask` (typed clarify) | card | 2h | partial result if `ask_budget` partly used, else abort-clean | paused | runs | as above |
| `review` (deliverable or partial) | card | 24h | abort-clean | paused | runs | as above |
| `pause_review` (injected by the engine when a detector raises a pause) | card | 15 min | abort-clean (never kill) | paused | runs | proxy stopped, egress blocked, keys idle |

Rules: (1) Pause never consumes `active_s`; a separate `waiting_s` cap bounds total waiting. (2) The maximum wait must be shorter than the payment authorization window (PayPal's 3-day honor period per research/09 digest cited in the audit; exact values UNVERIFIED against primary docs), else the Supervisor asks the hub to re-authorize before the wait. (3) Cards bind `{card_hash, run_id, epoch, decision, nonce, expires_at}`; the first valid decision wins; any later or conflicting decision, or one arriving after a terminal state, is dropped and logged; phone approvals are signed by the phone key (relay design is separate, audit HI-F3). (4) Question text, pause evidence and prompts are pack-authored or detector-derived text: rendered inert, escaped, truncated, labelled "from pack, untrusted"; evidence cards render only supervisor-generated fields (audit AD-F12). (5) A `pause_review` has three outcomes: resume, abort-clean, kill-incident; a timeout or an unreachable requester always maps to abort-clean: discard the result, no quarantine, denylist, revocation or reputation effect; rate-limited per requester to stop abort-clean being used for free runs (audit AD-F3). (6) The requester's answer to `ask` is typed data. It never goes to an LLM holding vault read access and never re-opens the lens. (7) A `human` node inside a `loop` or `map` has a max count and counts against the approval budget (section 4).

### 3.11 Liveness, leases, clocks, sleep and preflight

- INFRA_FAULT is distinct from tamper (audit PR-F2, AD-F12). Tamper requires positive evidence: bad signature, unexpected socket peer, hash mismatch, unauthorized write. Missing heartbeats or a dead process are INFRA_FAULT: freeze, grace, kill, no strike, no author penalty, release or void the hold, re-queue.
- Lease chain: the Supervisor grants flowd and the sidecar services a short lease (10-15 s, renewed over a local socket); flowd serves steps and the Cell reaches services only while the lease is valid; on lapse the Cell is frozen, then killed after a grace period and keys are dropped. flowd, sidecar and Cell die with the Supervisor (parent-death signal or cgroup; the exact WSL2 behavior is UNVERIFIED); the Supervisor reaps orphans at restart.
- Clocks: run budgets use a monotonic clock minus suspended time; wall-clock TTLs are enforced hub-side; after a gap above a threshold the Supervisor writes `suspend_gap`, then re-validates token, hold, revocation, snapshot and hub reachability before RESUMING. Dead TLS or Nebius sockets are retryable faults. Hosted ordering uses per-task sequence numbers and the event hash chain, not timestamps.
- Sleep: at run start the Supervisor warns about or inhibits sleep (Windows power request or a keepalive; WSL2 idle behavior UNVERIFIED, vmIdleTimeout 60 s noted in research-v2/07) and records a suspension counter in the receipt.
- Preflight (before AUTHORIZE, and a fast subset before each private-data run and each resume): driver conformance subset (no-NIC, no automount of host paths, socket connect on ro mount; target under 10 s), a 3-probe self-test at every Cell start (audit CO-F12), disk and RAM admission (the 6 GB WSL cap), concurrent-run limit, RPM share (3.15), model reachable and pinned, analyzer re-run on the downloaded digest (the requester never trusts the hub's analysis; analysis is deterministic over content-addressed input). Any failure refuses private-data Pull with a plain-language reason and what the user can still do (audit HI-F8).

### 3.12 Context management

Per `llm` step the context is: engine preamble (stable first, for cache friendliness; whether Nebius gives KV-cache benefits is UNVERIFIED), then the pack's step prompt (trusted: it is pack content the requester approved), then tool definitions, then typed inputs inside labelled delimiters (untrusted fields can never appear in system-role text; delimiters support labelling and do not stop injection), then an engine-written progress summary and objective recitation (the todo.md idea, https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus). Policy `context`: tool-result clearing first, then summarization at `compact_at` (default 0.70 of the declared context; the 85% in deepagents and the thresholds in other harnesses were tuned for other models, research-v3/03), full pre-summary history offloaded to an R artifact the step can page through, `max_compactions` as a thrash guard (Claude Code stops auto-compacting after a few attempts, research-v3/03 s2.4), failed actions kept in context. Compaction is a metered model call with its own budget line; summaries inherit the max sensitivity and the union labels of what they summarize. The analyzer rejects steps whose declared input max plus prompt plus output reserve exceeds 60% of the model's declared context (Nemotron `min_context` 32k forces frequent compaction otherwise). `inherit` context across steps does not exist; hand-offs are typed and size-capped (Anthropic's sub-agent summaries of 1,000-2,000 tokens are the reference, https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).

### 3.13 Hosted mode

The host runs the same flowd, sidecar and Cell stack under its own root. The workflow's union of grants yields the packet manifest for the Disclosure Compiler (items beyond it are denied; Pull-only items excluded). `memory.search`/`describe` are served from the read-only packet snapshot behind the same interface (audit HO-F12); (digest, model, mode) is certified separately and the Pull LCB is not shown on a Hosted listing without a Hosted-mode certification. Model calls go through the hub model gateway with a short-lived task token; no Nebius credential reaches a host (audit HO-F1, ID-F12; the gateway itself belongs to the hub design). Failover to another host is off; an explicit opt-in re-discloses and needs a new approval. flowd emits signed monotonic heartbeats via the relay and signed per-milestone journal heads encrypted for the requester, so rollback or suppression by the host is detectable but not preventable. All verdicts and journals are host-attested and labelled so; a host-signed incident can void that run and downgrade the (host, pack) pair only (audit HO-F9).

### 3.14 Revocation and version-state handling during a run

The Supervisor, not the Cell, checks the signed, versioned, expiring revocation list (full download, monotonic sequence, `valid_until`). Start: private-data runs require a list fresher than the policy window shown on the card; stale means refuse (fail closed for high sensitivity) or warn-and-confirm for low. Mid-run: on list expiry the run pauses at the next step boundary (state kept) rather than dies; on a new revocation the in-flight action depends on the reason: malicious-confirmed, key-compromise or runtime-CRITICAL kill and quarantine; vulnerability, deprecated, licence, author-request drain the current step, checkpoint, stop with PARTIAL(revoked_drain) and report which milestones were verified (audit LC-F1, LC-F8, ID-F3). Local denylist always wins; an unreachable hub never unblocks. Quarantine applies to all runs of that digest on the machine and their Q proposals (audit LC-F11).

### 3.15 Concurrency, fan-out safety, model failure and admission

- `max_concurrency` for `map` defaults to 2 and is capped by the Supervisor; total spawn and depth caps are ours (Claude Code's depth 3 and 20 concurrent are references only, research-v3/01 D).
- Model failure semantics belong to the Model Proxy but shape the engine: the proxy owns call-level retries (bounded, jittered exponential backoff, honors Retry-After, idempotent per call id) and returns only typed errors `UPSTREAM_UNAVAILABLE`, `RATE_LIMITED`, `MODEL_GONE` to flowd, never raw provider errors (audit PR-F8). On those, the run enters STALLED: budget and active clocks pause under a separate stall cap; after N minutes the requester gets wait, suspend-and-checkpoint, or abort. `MODEL_GONE` or a response `model` field different from the pinned id is INFRA_FAULT, the run is marked uncertified if continued, and nothing falls back to another model silently.
- Rate limit: the key's RPM is split into per-run token buckets with a reserved slice for the local agent and the extractor; admission warns when concurrent runs exceed the key's limit; `map` fan-out waits on the bucket instead of failing.
- Budget accounting: reserve max tokens before each call, reconcile from the usage field, count timed-out calls conservatively, never charge retries caused by infra.

### 3.16 Budgets, caps and winding down

Hierarchy: run > block (loop, map, scope) > step. Outer bound = min(escrow authorization cap, requester token/USD cap, wall caps). A step budget is per execution; a block budget caps the whole block; carry-over only if declared; sub-budgets never exceed their parent, and `map` items debit their block. Units: `usd, tokens, active_s, waiting_s, steps, model_calls, tool_calls, iterations, compactions`. Precedence: whichever cap is hit first moves the run to WINDING_DOWN; soft thresholds (80%) warn and may switch model class to a cheaper one if the step declares `degrade`. The engine holds `reserve.usd`: no step can spend it. WINDING_DOWN performs, with no model call, a deterministic assembly of a schema-valid partial result from committed outputs: items are flagged `verified` (passed P/R gates) or `unverified`, and only verified items back milestones (audit PR-F9, research-v3/03). If the reserve allows, one optional model-written summary step runs against that slice, enforced by the proxy. The approval card shows token and USD caps next to the price cap; the author fee does not depend on token spend.

### 3.17 Build order and the conformance suite

Engine phases (each depends on architecture-v2 phases in parentheses):
- E0 spec and parser: format, types, labels, CEL integration, shared parser corpus, validator (v2 phase 1).
- E1 journal and Run Store: Supervisor writer, framing, recovery, blob store, reconcile (phase 4).
- E2 scheduler and state: kinds `tool`, `branch`, `gate` (P class), `return`; chaos-resume and replay tests (E1).
- E3 llm executor and context manager; Nemotron tool-calling smoke test first (phase 4).
- E4 loops, map, parallel, budgets, reserve, WINDING_DOWN, Progress Guard (E2, E3).
- E5 code and verifier cells, adapters (phase 3 driver, E4).
- E6 human nodes, leases, sleep handling, hire order and run state machine with the hub (E2; hub stub acceptable).
- E7 static analyzer complete (E0, list in section 4), then Pack Studio tooling (section 7).
- E8 Certifier structural suite (phase 10 base).
Conformance suite (also run by the Certifier against any engine version): replay equivalence, chaos-resume, effect idempotency, budget enforcement (infinite-loop pack stops at cap), gate bypass (write after gate is caught), off-graph step token use (denied), expression cost limit, label join property tests, parser fuzz corpus, journal torn-tail recovery, stale-epoch rejection, pause timeout mapping.

---

## 4. Static analysis at publish time (and again on the requester)

`bridge flow analyze` runs in Pack Studio, in the hub validator and in the requester's supervisor (the requester re-runs it on download; the hub's verdict is not trusted). It is sound and conservative: it may reject safe workflows; authors fix them. Output is a deterministic JSON report whose hash goes into the attestation.

| # | Check | Detail |
|---|---|---|
| 1 | Schema and limits | Closed step kinds, no unknown keys, max steps/edges/template length, strict parser rules from 2.1 |
| 2 | Reachability and structure | All steps reachable; every path ends in `return` or `fail`; only `loop` blocks form cycles; no dead gates |
| 3 | Termination and worst-case cost | `loop`/`map`/`parallel` bounded; worst_case(node) = min(own_budget x executions_bound, enclosing block budget, run budget); sum with reserve must be at or below `budgets.run.usd` and the declared maximum price; retries sit inside budgets |
| 4 | Permission union and capability-set hash | Per-step grants within the manifest envelope; union equals the declared envelope; hash bound into approval and attestation; any widening vs parent requires a MAJOR bump (hub computes the diff and rejects a non-MAJOR widening, audit LC-F4) |
| 5 | Rule of Two per step | A = untrusted-integrity input or untrusted tool output; B = lens data; C = external communication or state change. In v1 private runs C is: external tools (absent), proposals with free strings, and the result channel. The model call is treated as a sanctioned, labelled sink (listed on the card) rather than a C property, because the attacker cannot choose the recipient; this is our PROPOSAL and differs from research-v3/02 s4 which suggested treating it as C. Any step with A+B+C and no dominating gate of class `human` or a deterministic declassifier is rejected |
| 6 | Label flow | May-reach analysis from sources to sinks (model prompt, tool arg, proposal, return field); reports private-to-sink paths without a declassifier; checks the per-run declassification bit budget |
| 7 | Untrusted-branch check | Branch or loop conditions that depend on untrusted values and whose arms differ in authority are errors |
| 8 | Role rules | `privileged` steps accept only trusted-integrity inputs unless declassified; `quarantined` steps have no tools and no memory beyond inputs |
| 9 | Expression and template safety | CEL cost limits; placeholders only for typed fields with known labels; untrusted fields never in system-role text |
| 10 | Gate integrity | Every gate's artifact is frozen by hash; no later writer to a gated artifact; at least one P or R check on every milestone gate; judge model differs from the producing model for certified claims |
| 11 | Result contract | `result_schema` is a subschema of the platform kind envelope; output fits author-bound channel rules where fields leave the machine (receipts only) |
| 12 | Human gates | Each `human` node has timeout, default, and a max count inside loops; `approval_budget` (worst-case number of cards) computed; publish refuses above the ceiling (PROPOSAL: 6 per run); the listing shows gate count and expected cards (audit HI-F10) |
| 13 | Proposals | `max_items` per run across iterations; schema is the platform meta-schema (enums, numbers, hashes, references; free strings allowed only if shown to the user as a diff and never passed to the Scribe or auto-promoted) |
| 14 | Context fit | Input max plus prompt plus output reserve at most 60% of declared context |
| 15 | Scope rule | No scope with `data: lens` and any network class (2.8) |
| 16 | Assurance class and approvals strip | Computes S/O, the "where your data goes" strip (4 lines: stays local; goes to the model provider in N listed steps; author receives nothing during the run; isolation tier), steps that send private text to Nebius |
| 17 | Similarity | Near-duplicate workflow/prompt check against the registry at publish (not trusting declared `parent`; audit CR-F9) |
| 18 | Tool metadata | Catalog tools carry declared reads/writes/network metadata and pinned digests; pack-supplied tools must pass conformance tests; the analyzer is only as sound as this metadata (research-v3/02 risk) |

Dynamic complements run by the Certifier: path and edge coverage over the suite (steps never exercised are flagged), measured worst-case versus declared, and a check that no step ever exceeded its capability in any history.

---

## 5. Containing code-bearing steps

### 5.1 Leaf `code` steps

- Nested sandbox inside or next to the Cell: no network namespace, read-only mount of exactly the typed inputs, writable tmpfs sized separately from the memory cgroup (so OOM versus ENOSPC are distinguishable and classified `resource_exhausted`, audit PR-F12), caps on CPU, memory, pids, wall time and output bytes, no access to the sidecar socket (it cannot call the model or memory), no environment secrets.
- I/O is stdin/stdout typed JSON only. Output is validated against `output.schema` before entering the engine; oversize or non-conforming output is an error, never truncated silently. Output label = join of input labels; the code cannot lower labels.
- Source for a `code` step is either a pinned pack file or text from an upstream step. Generated code is permitted precisely because the sandbox has no network and no brokers (research-v3/02 s9.4); it is not permitted to run with network.
- Pack-provided custom tools are the same: leaves, typed, no brokers. A tool that needs the model must be expressed as an `llm` step.

### 5.2 `adapter` steps (third-party runner loops)

Runs inside a Cell with: no NIC, ro rootfs, caps dropped, a writable overlay of exactly the declared workspace, a model handle bound to the step token and the step's caps (turns, USD, wall, idle), and no memory capability unless the step grants one. Adapters are pinned by SHA and image digest and re-certified on every bump (research-v3/03 risk 9). deepagents provides no OS isolation and OpenClaw skills run unsandboxed by default (research-v3/03 s2.6 and s2.9), so both are usable only inside the Cell. Adapters make the pack assurance class O.

False-positive control for adapter code: the Certifier records a benign-behavior baseline per (digest, model): failed connects, DNS on import, parameters, file touches. Kill-grade evidence needs deviation from the baseline combined with lens data involved; otherwise deny and log. D10 is scoped to after Cell init, and retries are excluded from D4 (audit AD-F11).

### 5.3 Verifier cells and result handling

Anything that executes pack-influenced code for verification (tests, linters, build) runs in a throwaway cell with no network, no vault data and no sidecar socket, started per check. Rendering or reviewing results never fetches URLs (Result Guard CSP, 2.9); patches are never applied outside a throwaway worktree; the conformance fixture is a malicious pack putting a Markdown image, a postinstall script and a link with chunked encoded data into its result, passing only if zero outbound requests occur at render and review time and D15 fires (audit TK-F2).

### 5.4 Residuals

Nested sandbox escape (driver tiers and conformance apply, one fixture per step kind). Covert channels in typed outputs (bounded by narrow schemas, size caps, Result Guard, non-streaming calls). Code can compute on what it was handed and return a typed value; the leak routes remain the result channel and encodings in typed fields.

---

## 6. Integration with memory, detectors, certification and ranking

### 6.1 Memory lens

- Grants per step: `memory.search{ns, tags, max_sensitivity, k, bytes, min_tier}`, `memory.describe` (metadata only: names, types, counts; accounted by the same Broker; fixes the "planner cannot see anything" problem, research-v3/03 F2), `memory.materialize` (tier 1 only), `memory.propose{schema, max_items}`. Each step's grants attenuate the approved run lens; the card shows the union and per-step detail (research-v3/02 F9).
- Data path: tier 0 only through the Broker; tier 1 files only through accounted `materialize`; no `/in` of the whole slice (audit PR-F6, CO-F2, MM-F2). `memory.search` runs over the staged snapshot (a closed set whose record ids and content hashes are on the card) for Pull private runs, not over the live vault; if live search is ever offered the card must say "live search within lens, up to N items, M bytes" and not claim byte-exact (audit HI-F2, TK-F11). The snapshot manifest is `(record_id, version, content_hash)` plus the vault seq; vaultd recomputes hashes at stage time and re-prompts on mismatch.
- Labels to provenance: the label `src` of a proposal (the record ids and step ids it derives from) becomes `derived_from` and `origin {pack_digest, run_id, proposal_id}` on the Q item; acceptance never erases `origin`, accepted pack-derived records stay below user-authored tier, and the endorsement is "pack-claimed" not "user-authored" (audit MM-F4, MM-F9, HI-F1, CO-F5). The engine supplies the taint ancestry that vaultd needs to propagate `derived_from` transitively. Accepted-record sensitivity is at least the max sensitivity in the producing run's read accounting.
- Proposals: schema from the platform meta-schema, `max_items` per run across loops and maps, content-hash idempotency, Q caps per pack and globally with TTL (vault design owns the numbers). The local agent and Scribe never read Q raw (audit MM-F7).
- Run-scoped revert instead of whole-U rollback: the journal lists every `effect_done` of the run, so "which records trace to this run" is a query; revoke or kill produces a revert candidate set (set `invalid_at` plus compensating events, per record, CAS on the tainted version, conflicts to the user, never overwrite concurrent user edits). The pre-task Merkle checkpoint is an audit anchor only; checkpoints are scoped per run id so overlapping runs are unambiguous (audit MM-F1, PR-F5, AD-F9, HI-F4, CO-F11, MM-F9, LC-F10). A regression test: a user write during a run, then a CRITICAL kill, leaves the write intact on every device; a sleeper pack with ten accepted runs and then a CRITICAL leaves none of its items or derivatives retrievable until re-accepted.
- Clarification answers, partial results and chained artifacts (`artifact_from_task`) enter as trust-tier-0 typed inputs with their source sensitivity label; the agent may not paste raw output into instructions; outputs of quarantined or killed runs are never valid handoff inputs; TaskSpec is pack-independent so a revoked pack can be replaced (audit TK-F12).

### 6.2 Detectors, evidence classes and the ladder (step-scoped)

Evidence classes (new; every detector event carries one):

| Class | Meaning | Examples | Default consequence |
|---|---|---|---|
| T tamper | positive evidence of tampering | bad journal/step-token signature, unexpected socket peer, pack hash drift (D9, D12), off-graph step token use | KILL, snapshot first |
| E egress-deterministic | confirmed attempt to reach outside | D5 egress/DNS from the Cell, canary value in a proxy request or tool arg to an external sink | KILL |
| B boundary | denied access | D1, D3 out-of-grant call | deny and continue, strikes accumulate |
| P progress | quality signals | Progress Guard (3.9) | nudge, replan, abort; never a strike |
| I infra | environment fault | lease lapse, model gone, ENOSPC | freeze, retry, no strike |
| C claim | requester-attested or host-attested | any requester-signed CRITICAL in Pull | local kill and quarantine; money HOLD, not VOID; no author reputation effect until hub-checkable |
| X data-induced | trigger text found in a foreign lens or Q record that was in context | injected document makes an honest pack touch a canary | contain (kill or pause, discard Q), no strike, no revocation, requester hygiene warning |

Step-scoping:
- D1/D3 evaluate against the current step's grants, not the run union. D4 volume uses per-step quotas and counts distinct records, not repeated identical queries.
- D8 now means "off-graph": since flowd alone sequences steps, a step request that does not match a legal edge, or a step token used outside its step and attempt, can only come from engine tamper or Cell misbehavior; it is class T and kill-grade, not a statistical anomaly. Everything below the engine that is merely unusual stays B or P.
- D6 overlap gets a sink taxonomy (audit AD-F2, TK-F4): expected-overlap sinks are the result free-text fields (bounded by `quote_budget`, with a "what from your data is in this output" panel) and the model path to the provider (a labelled sink, not overlap-checked); strict sinks are tool args, search queries, URLs, proposals, non-free-text typed fields. The metric is longest verbatim overlap and overlap fraction against the per-step quote budget. The old "return step overlap is high-confidence" rule is removed; replaced by a taint check (return labels must be a subset of input labels). Response ladder: over budget means redact or flag; encoded or canary hits on non-free-text fields mean pause; kill only with a second independent detector or an egress hit. D6 ships log-only until its false-positive rate is measured on honest report fixtures.
- Canaries (audit AD-F1, CO-F1, PR-F10): the hub issues a per-run canary seed committed in the run token; values and placement are bound in the signed manifest before the run; the engine's scan runs at every typed-output boundary and at the Result Guard. Canaries are served only on off-lens or enumerative queries and as out-of-mount decoys, never inside in-lens search results; denied D1 reads never return a canary value; a staged slice that contains any canary value (normalized and encoded) rejects the run at staging. A verbatim canary in a free-text result field is Result Guard reject and redact plus a strike plus pause, not a kill. Kill needs a transformed canary, a canary in a non-free-text field, tool arg or proxy request to an external sink, or corroboration by D5/D6/D7. A D2 hit alone ends at kill-or-pause and quarantine of the run, money HOLD, reputation untouched. Bait tools are not placed in the model-visible tool list.
- Attribution step (audit AD-F10): each journaled model turn records a context manifest (which record ids and labels were in context). On a trigger, flowd checks whether the instruction text or a near paraphrase appears in a foreign lens or Q record that was in context; if so the incident is class X. Any author-affecting action (strike, revocation proposal, payout freeze, public attribution) additionally requires reproduction on a clean synthetic lens by the Certifier; the Certifier suite includes an injected-lens test, and failure there labels the pack "injection-susceptible" instead of malicious.
- Requester and host attestation (audit LC-F2, PY-F1, AD-F4, CR-F1, ID-F4, HO-F9, CO-F3, TK-F10): in Pull the supervisor is requester-controlled, so every verdict, receipt field and acceptance result is requester-attested and labelled as such; a deterministic CRITICAL still kills and quarantines locally but moves money to HOLD/DISPUTE; hub-wide revocation, payout freeze beyond hold, safety-incident counts and ranking penalties require Certifier reproduction (same digest, same canary seed commitment, same fixture) or corroboration from N independent aged requesters. This document supplies the evidence bundle the replay needs: the journal (redacted), the canary placement commitment, the egress trace. It cannot make Pull fair-exchange; it states so plainly.
- Slow exfiltration and public rules (audit AD-F7): the engine caps per-run free-text output bits via narrow typed schemas and records a cumulative per-(requester, pack lineage) ledger on the requester side; the guarantee text says "the pack sees only the lens and the output channel is bounded", not "detectors prevent theft".
- Sensor integrity: signed sensor heartbeats with sequence numbers verified by the Supervisor; loss is class I (audit AD-F12). The guard model (D13) never sees private text in steps that hold lens data, or is local.
- Ladder atomicity (audit AD-F8, PR-F12): on any CRITICAL, append an fsynced `incident_intent`; order is freeze, snapshot (diff, logs, metadata), then kill; remaining rungs are idempotent steps keyed by `(run_id, rung)` with done markers and a boot-time reconciler; concurrent detectors resolve by max severity with one incident per run; Accept is not final until detectors have drained and a short settlement window passed.

### 6.3 Certification

What the Certifier measures per (workflow digest, model id plus provider revision, mode, suite version, engine conformance hash):

1. Task success on private rotating suites, bucketed by task length; pass^k as well as pass@k (https://arxiv.org/abs/2406.12045 for the pass^k idea; https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); clustered over tasks (task is the resampling unit) for the lower confidence bound.
2. Gate-backed success (success verified by P/R checks) reported separately from judge-based success.
3. Cost p50/p95, wall time, retries per node, gate-fail rate per node, loop-iteration distribution, budget-exhaustion rate, stuck rate, human-gate rate, resume success rate.
4. Structural tests (the 3.17 conformance suite applied to the pack): chaos-resume, replay determinism, idempotency after forced restart, budget enforcement against a looping fixture, gate bypass attempts, off-graph step token use, label-flow violations, worst-case-versus-declared cost.
5. Fault injection: tool failure, model 429/5xx/timeout/model-not-found at the proxy, context overflow, kill-and-resume, sleep/wake gap, ENOSPC.
6. Security fixtures: exfiltration and memory-theft fixtures, injected-lens test, the sleeper and time-bomb variants (date trigger, trigger phrase, result-channel exfiltration), fingerprint resistance: the Certifier uses the same supervisor, sidecar, run-token, receipt and engine path as production, production-shaped canaries and vault-shaped synthetic data, randomized and future-dated clocks, and a cheater pack that conditions on cert signals must be caught (audit CR-F4).
7. Coarse outcomes only to authors: pass/fail plus a fixed reason-code class, no case ids, per-publisher rate limit and exponential cooldown, an explicit REJECTED state with one appeal; optimizer iterations use only a freely iterable public-dev suite (audit LC-F12, CR-F5).

Attestation (in-toto-shaped, hub-signed, separate from the pack digest) binds: workflow digest, capability-set hash, analyzer report hash, model id and revision, mode, suite version and scoring version, engine version and conformance hash, adapter image digests, driver tier, Result Guard version, Certifier build, `score_lcb`, per-task outcome hash vector, run-log digest, `valid_until` (about 90 days). A change to any stack component marks it STALE; private-data Pull needs a CURRENT attestation or an explicit requester override banner (audit LC-F5, LC-F9, CR-F8). A requester whose sidecar runs a different model than the attestation shows "uncertified on your model" and no LCB. One counted certification per (digest, model, suite epoch); retries are pre-registered recertifications only.

### 6.4 Ranking and the author-bound channel

- Rank per (workflow digest, model, mode); assurance class and gate-backed success are separate columns; stuck rate and cost percentiles are columns; Progress signals are never safety incidents. Paid signals can only demote or tie-break relative to the Certifier LCB (audit CR-F7).
- Receipts (supervisor-generated, fixed enum and integer fields): run id, workflow digest, mode, outcome enum, milestone ids verified, buckets for duration, tokens and step count (step counts are bucketed because branching and loop counts can encode data; node-level timing is never exposed to authors), detector verdict as a coarse incident/no-incident bit, acceptance enum, attestor label (requester or host). Exact cost is not reported; price tier or bucket is (audit PY-F11, AD-F6). Per-run rows go to the hub only; authors get batched aggregates released with at least k distinct requesters and a delay (the hub design owns k; 20 is a PROPOSAL).
- Optimizer: edits only H-plane step contents and typed parameters within manifest ceilings; topology edits (adding a gate, splitting a node) need human review; budget caps, `max_iterations` and permissions never increase automatically. Topology changes without permission change are MINOR; permission or budget-cap widening is MAJOR (section 2.1 capability-set hash enforces it). Optimizer edits are typed diffs against `workflow.yaml` and step files.

---

## 7. Authoring and testing experience

### 7.1 Pack Studio commands (`bridge flow ...`)

| Command | Does |
|---|---|
| `init --template <t>` | Scaffolds from a template (2.13) with schemas, rubrics, sample fixtures |
| `lint` | Fast structural checks with fix hints in plain language |
| `analyze` | Full static analysis (section 4); prints worst-case cost, assurance class, permission union, label-flow report, Rule-of-Two result, approval budget, the "where your data goes" strip |
| `graph` | Renders the graph (Mermaid or SVG) with grants, budgets and labels on nodes; diff view between two versions |
| `dry-run --mock <fixtures>` | Runs the real engine with scripted model responses and fake tools: deterministic, free, fast; asserts transitions and outputs |
| `run --synthetic` | Real model on synthetic data through the production path (same supervisor, sidecar, brokers) producing a journal |
| `replay <journal>` | Re-runs the engine over a recorded journal; asserts identical transitions (engine drift detector); produces a bug reproduction an author can share (synthetic runs only) |
| `chaos` | Kill flowd at random indices, inject 429/5xx/timeouts/model-gone/ENOSPC/sleep gap, fill the context window, then assert resume correctness and budget enforcement |
| `test` | Unit tests per step (recorded model output in, typed output and verdict out), per gate (frozen artifacts, expected verdicts), golden journals |
| `coverage` | Edge, step and gate coverage across a run set; flags never-exercised steps |
| `cost` | Cost and time estimate from certified percentiles (when attested) or from synthetic runs |
| `explain <denial>` | Maps a broker deny or analyzer error to the grant or edge responsible |
| `optimize` | Runs the improvement loop on the public-dev suite; shows the typed diff, score delta and permission delta for owner approval (never auto-publish) |

### 7.2 Trace viewer

A web view (reuse parts of the munder-difflin node graph and tool waterfall, MIT, architecture-v2 s8) over a journal: step timeline and graph with state transitions; per-turn model calls with token and cost; tool and broker calls with the grant that allowed each; labels on values and where they changed; gate results with class, evidence and frozen artifact hash; budget ledger with reserve; Progress Guard signals; detector events with evidence class; human waits with deadlines; the resume points and epochs; diff of two runs. Authors can only load synthetic or explicitly consented traces; on the requester side the viewer shows the requester's own full data. Redaction mode shows labels and sizes without content.

### 7.3 Requester-side surfaces

- Approval card derived from the workflow (not from author prose): the four-line "where your data goes" strip (audit HI-F9), per-step permission list collapsed behind the summary, lens summary by sensitivity class and item count (bytes second, collapsed), worst-case and p50/p95 cost and time, gate count and expected cards, assurance class, driver status ("isolation verified N/N, 2 min ago"), attestation status (CURRENT/STALE/uncertified on your model). `card.json` carries only typed fields (enums, numbers, hashes); author free text lives in a separate pane labelled "author says, unverified" and is never placed in the local agent's context (audit HI-F7, CR-F10).
- Run status contract (audit HI-F12): current step, elapsed active and waiting time, cost versus cap per level, next human gate and its deadline, last detector event and evidence class, a Cancel control within two taps, content-free notifications for gate waiting, pause, incident, completion. Gate timeouts are configurable and extendable. Every card has a structured text view (headings, lists, no color-only meaning, keyboard operable) next to raw bytes; canonical guarantee strings per language are reviewed once.
- Cancel (audit TK-F10, HI-F5): idempotent hub-side event with epoch and sequence number, short grace, then WINDING_DOWN and PARTIAL(cancel); first terminal event wins.

### 7.4 What the demo can show with this

The 3:00 cut can show the trace viewer for one run, a `kill flowd mid-map, resume, same result` clip replayed from a recorded journal, the Progress Guard nudge, and a gate failing then looping to a pass. Label scenes "replayed from certified run" where they are not live (audit CO-F9). Whether live resume fits the time is UNVERIFIED until E6 exists.

---

## 8. What cannot be expressed, and why

| Not expressible | Why | What to do instead |
|---|---|---|
| A step with untrusted input, private data and external communication, no gate | Rule of Two / lethal trifecta (https://ai.meta.com/blog/practical-ai-agent-security/ , https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) | Add a human gate or a deterministic declassifier; split into steps |
| Control flow chosen by untrusted free text | Untrusted data must not change which steps run (CaMeL, https://arxiv.org/abs/2503.18813) | Extract an enum via a quarantined `llm` step, charged to the bit budget |
| Arbitrary cycles, `goto` back-edges, recursion, dynamic step creation | Termination and worst-case cost undecidable; label analysis breaks | `loop` block with `max_iterations`; `map` over a bounded list |
| Model-spawned sub-agents (`spawn` tool) | Capability surface and cost multiply (about 15x tokens in Anthropic's multi-agent system, https://www.anthropic.com/engineering/built-multi-agent-research-system); detectors cannot attribute | `map` or `parallel` with declared caps; each item gets an attenuated child capability |
| Plan expansion (model writes new graph) | Needs an envelope validator; deferred | Reserved `expand` step: privileged planner from trusted inputs only, emits the engine dialect, validated against a pack-declared envelope, class E |
| Open-ended agent loops with large tool sets on private data | Cannot be bounded statically | Allowed as class O (`adapter` or unbounded `llm`), flagged, ranked separately, only within the lens and Cell |
| Web access in a scope that holds lens data; search queries built from lens values | Exfiltration channel | Public scope then private scope (2.8) |
| Connectors with credentials (private APIs, git hosts, databases) | Arguments are an attacker-chosen exfil/write sink; token scope and revocation on kill undefined | Not in v1. Design hook: typed ops with destination templates, credentials only in the sidecar as handles, writes only through propose/apply with human approval, public destinations denied |
| Pack-to-pack delegation or `subflow` of another pack | Each hop needs its own approval, labels and revocation | Reserved; chaining only through `artifact_from_task` between separate runs |
| Pack-side persistent memory across runs | No pack-writable durable store (architecture-v2 4.7) | Proposals to Q only |
| Declassification by LLM judgement | Not a safe primitive | Schema extraction, human gate, deterministic rule |
| Live clock, randomness, network or env in expressions | Breaks replay and containment | Journaled `now()`/`rand()` events, engine-side only |
| Gate-by-pack for money (K and J classes) | Verification theater | Only P and R drive milestones |
| Mid-run free-form conversation with the requester | Confused-deputy read of the vault via the local agent; free text can carry pasted untrusted content | Typed `ask` nodes with an `ask_budget`; or end with `needs_input` |
| Applying a patch to the live tree | Executes attacker-chosen config or hooks on a networked machine | Result only; requester-side apply contract (2.9) |
| Closing timing, size and steganographic channels | Not preventable by the language | Quantized, narrow, non-streaming outputs; Result Guard; state "detect, not prevent" (the guarantee text in architecture-v2 3.3 stays) |

---

## 9. Open questions

1. Engine language: Rust or Go for flowd and the analyzer (memory safety, sandbox story, the rest of the sidecar stack). Default proposal: whichever the sidecar uses, if memory-safe.
2. CEL library choice and maturity (cel-go, cel-rust, cel-python), RE2-class regex engine, cost-limit configuration: UNVERIFIED, needs a spike.
3. Does Nemotron on Nebius support reliable native tool calling for the `llm` executor, and how often do format errors occur? Smoke test before E3 (research/10 rec 2 is cited by the audit; result unknown).
4. Over-tainting: how many human gates does the label rule force on real tasks (utility cost UNVERIFIED; CaMeL's 77% versus 84% is AgentDojo only)? Spike on two workflows (a research workflow and a code-review workflow), then set the declassification bit budget.
5. Tuning of Progress Guard thresholds, compaction trigger and max compactions for Nemotron; borrowed values untuned.
6. Process placement of flowd and the Supervisor on Windows 11 Home (WSL2 VM versus host), and WSL2 parent-death and idle behavior (ties to the driver ADR).
7. Journal privacy: per-run key escrow, shred propagation granularity, retention values, quarantine copy policy for KILLED runs (vault design must agree).
8. PayPal authorization window and reauthorization behavior (primary docs not re-read here): determines `waiting_s` ceilings and the re-authorization point.
9. How many milestones can a workflow realistically verify with P/R checks only, and how does the payments design capture per milestone without breaking the honor window (UNVERIFIED).
10. Single-thread versus fan-out: Anthropic's multi-agent evidence versus Cognition's single-thread argument (https://cognition.com/blog/dont-build-multi-agents) is contested; the Certifier must measure both variants of the same archetype instead of the platform choosing.
11. Sealed/Hosted: how the engine proves its measurement in an enclave (out of scope here).
12. Whether a `K`-class pack verifier is worth shipping in v1 given it never drives money.
13. A requester-side output-bit ledger per pack lineage: schema, privacy, interplay with the P plane.
14. Adapter observability: can mini-swe-agent or deepagents emit per-step events to flowd (hooks) so Progress Guard is not blind? Needs a read of their code at pinned SHAs.
15. Multi-device: confirmed rule that resume is single-device in v1; what does a "paused on laptop, continued on desktop" user story cost to support later (journal sync plus epoch)?
16. Approval budget ceiling (6 cards per run is a guess) and measurement of approval-rate telemetry for reflexive approving.
17. License and security review of imported adapters' transitive dependencies (SPDX data covers repo roots only, research-v3/03).

---

## Appendix A. Behavioral-flow review

The owner asked for a careful check of how everything behaves. Part 1 walks twelve scenarios through the design to check each step has a defined outcome. Part 2 lists problems found in this design itself, and part 3 the problems that remain open.

### A.1 Scenario walk-throughs

| # | Scenario | Event sequence under this design | Verdict |
|---|---|---|---|
| 1 | Happy path, analyst, 3 hours | run_id minted; preflight; snapshot staged and hashed; card with approval_hash; AUTHORIZE (idempotent); STARTED on first `step_started`; describe, scope loop (ask once), plan approval, map of 12 items at concurrency 2 with per-item gates, milestone 1 verified, draft loop passes, propose effect, return, Result Guard, RESULT_READY, accept window (deterministic rule or click), milestone 2 verified, capture requests via outbox, R wiped after window | Defined. Depends on payments design for capture mechanics |
| 2 | Crash of flowd at hour 2 mid-map | Supervisor sees socket drop; I-class fault; flowd restarts and folds journal; resume checklist; items with `step_committed` are memoized; in-flight items re-run from last committed turn (llm) or from start (code/adapter); epoch+1 | Defined; replay of an `llm` step relies on recorded blobs; if a blob is missing the step restarts from its beginning |
| 3 | Laptop sleeps 40 minutes | Lease lapses; Cell frozen then killed after grace; on wake `suspend_gap`; monotonic budget excludes the gap; token, hold, revocation, snapshot re-validated; resume or void | Defined; PayPal honor window and WSL2 behavior UNVERIFIED |
| 4 | Budget exhausted mid-draft loop | Block cap hit; WINDING_DOWN; deterministic partial assembled from committed verified findings; reserve slice runs the optional summary; PARTIAL(budget); settle verified milestones only | Defined |
| 5 | D2 canary appears in a free-text result field | Result Guard redacts, strike, pause_review card; timeout maps to abort-clean; no kill, no money void | Defined; differs from architecture-v2 7.2 on purpose |
| 6 | Same, but canary base64-encoded in a tool arg to an external sink | Class E: KILL; incident_intent fsynced, freeze, snapshot, kill, idempotent rungs; money HOLD; hub adjudicates by replay | Defined; Pull still requester-attested |
| 7 | Pack yanked for a vulnerability during a run | List refresh; reason class drain; current step finishes; checkpoint; PARTIAL(revoked_drain); verified milestones settled | Defined |
| 8 | Requester away at a plan-approval gate | Waiting clock runs; 24h deadline; timeout abort-clean; hold released or re-authorized earlier if the window is shorter | Defined |
| 9 | User cancels at 90% | Cancel event with epoch; grace; WINDING_DOWN; partial from committed outputs; PARTIAL(cancel); first terminal event wins versus a racing Accept | Defined |
| 10 | User shreds a record during the run | vaultd event; dependent blobs deleted; consuming steps invalidated; high/secret in lens pauses with card; re-snapshot needs re-approval | Defined; interacts with approval design |
| 11 | Nebius 429 storm | Proxy retries with jitter; typed RATE_LIMITED; STALLED with clocks paused; stall cap then requester choice; map waits on RPM bucket | Defined |
| 12 | Malicious pack tries to bypass its gate by rewriting the artifact | Artifact frozen by hash before gate; rewrite creates a new hash; `return` accepts only the hash that passed; attempt appears as gate_result mismatch (class T if via step token misuse) | Defined; certifier fixture |

### A.2 Problems found in this design while checking (and the handling written above)

| # | Problem | Handling |
|---|---|---|
| N1 | Engine-owned agent loop concentrates risk in flowd (tool-call parsing, prompt rendering); a bug there is TCB | Small module, fuzzing, own process boundary option (llmd) considered; open question 1 |
| N2 | Adapters make Progress Guard partly blind and replay impossible mid-step | Step restart semantics; model-call-level signals; hard caps; assurance class O |
| N3 | Review of a "verified" partial: unverified items could be mistaken for verified | Partial assembly flags items; only verified items back milestones |
| N4 | `accept_best` selection could pick a tainted attempt | Selection is deterministic over committed gate metrics; result marked partial; human review default |
| N5 | Gate time-of-check/time-of-use | Hash-frozen artifact, hash-bound verdict, only matching hash flows on |
| N6 | Over-tainting makes everything private-and-untrusted and drives approval fatigue | Quarantined extraction with bit budget; role rules; approval budget ceiling; spike (open question 4) |
| N7 | Fan-out shares a 60 RPM key with the local agent and extractor | Per-run buckets, reserved slice, admission warning |
| N8 | Sum of per-item budgets could exceed the run budget | Block budgets and reservations; analyzer worst-case |
| N9 | Strikes re-fired by replay | Unique detector event ids; replay never regenerates security events |
| N10 | Human cards multiply inside maps | Max count, approval budget, ceiling at publish |
| N11 | Journal contains lens data and model outputs (privacy surface) | Encryption under per-run key, `derived_from_key_ids`, secret scanner, retention, quarantined copy rules |
| N12 | Resume under a changed environment (engine version, model id, snapshot, revocation) | Resume checklist; refuse not patch |
| N13 | Two requester devices resuming the same run | Single-device in v1, epoch rejects stale events |
| N14 | `memory.describe` leaks column names or filenames that are themselves sensitive | Labelled as lens data (B), same accounting as search |
| N15 | Per-step fresh Cells cost latency | Cell reuse only within identical data capability class; tier 0 needs no Cell; warm pool optional |
| N16 | Engine and analyzer drift between certification and use | Conformance hash in attestation; STALE state; requester analyzer re-run |
| N17 | Pack prompts are trusted by the engine (system role) | They are part of the approved, visible pack; authority envelope bounds what they can cause; prompt-only changes show a "behavior changed, score x to y" line, never silent |
| N18 | Hosted engine is host-controlled | Labels, signed per-milestone heads, no failover; unchanged residual |
| N19 | Platform check library is itself an attack surface (regex, parsers) | In flowd, fuzzed, bounded cost; `tests_pass` delegated to a verifier cell |
| N20 | A pack could game `numbers_reconcile`/`citations_resolve` with junk that satisfies them | Checks are necessary, not sufficient: Accept, requester R checks and hidden certifier checks sit on top; documented as Pull limit |

### A.3 Still open (not solved by this design)

Pull has no fair exchange: the requester can always keep the output and the supervisor is theirs; this design caps the loss and labels attestation but cannot remove it. Covert timing and steganography remain. Replay audits engine decisions, not model behavior. Static analysis is only as sound as tool metadata. Several parameters are untuned. The payments, hub, revocation-governance, phone-approval protocol, memory shred and multi-device designs are separate documents and this one only defines the interfaces it needs from them.

---

## Appendix B. Audit traceability

Prefixes by audit flow: LC pack lifecycle, PR Pull run, PY payment, HO hosted, MM memory, AD active defense, HI human-in-the-loop, CR certification and ranking, ID identity and keys, TK task and I/O, CO consistency. Disposition: A = addressed here (section); I = interface specified here, owning design elsewhere; N = outside the harness/task I/O boundary, owned elsewhere (no action here).

| ID | Topic | Disp | Where |
|---|---|---|---|
| LC-F1 | revocation freshness, in-flight rule | A | 3.14, 3.6 |
| LC-F2 | requester fabricates CRITICAL | A/I | 6.2 classes C/X, outcome table |
| LC-F3 | author key takeover | N | hub; capability hash and attestation fields help (2.1, 6.3) |
| LC-F4 | semver, capability hash, parent | A | 2.1, section 4 #4, #17 |
| LC-F5 | digest circularity, attestation fields | A | 2.1, 6.3 |
| LC-F6 | long runs, token, lease, retries burn | A | 3.3, 3.8, 3.16, 2.10 |
| LC-F7 | registry freshness, split view | N | hub |
| LC-F8 | version states and in-flight | A/I | 3.14 |
| LC-F9 | upstream, runner, engine, model outside digest | A | 5.2, 6.3 |
| LC-F10 | revocation vs promoted memory | A/I | 6.1 |
| LC-F11 | races, quarantine scope, approval concurrency | A | 3.3, 3.14, 3.15 |
| LC-F12 | certifier oracle, canonicalization | A | 2.1, 6.3 |
| PR-F1 | no durable run record | A | 3.2 |
| PR-F2 | liveness, sleep, clocks | A | 3.11 |
| PR-F3 | hire not idempotent | A | 3.3 |
| PR-F4 | accept window, checks | A/I | 2.7, 2.9, 3.3 (settlement in payments design) |
| PR-F5 | snapshot lifecycle, shred, residue | A/I | 3.3, 3.6, 6.1 |
| PR-F6 | /in vs Broker, phase rights | A | 3.4, 6.1 |
| PR-F7 | waiting on human | A | 3.10 |
| PR-F8 | model API failure | A | 3.15 |
| PR-F9 | budget exhaustion | A | 3.16 |
| PR-F10 | D2 canary kill + void | A | 6.2 |
| PR-F11 | approval scope, agent hires | I | 3.3 approval hash; agent tool separation is the local-agent design |
| PR-F12 | ladder crash safety, audit tail, ENOSPC | A | 3.2, 5.1, 6.2 |
| PY-F1 | requester decides VOID | A/I | 6.2, 3.3 |
| PY-F2 | accept/reject undefined | A/I | 3.3 |
| PY-F3 | honor period | I | 3.10 rule 2, open question 8 |
| PY-F4 | accept/capture/void races | I | 3.3 single run row, terminal absorption |
| PY-F5 | hub crash capture/payout | N | payments |
| PY-F6 | holdback vs dispute | N | payments |
| PY-F7 | clawback, retraction | N | payments/ranking |
| PY-F8 | payee binding | N | payments |
| PY-F9 | merchant of record | N | legal/payments |
| PY-F10 | wash trading | N | ranking (6.4 note) |
| PY-F11 | receipt signer, cost field | A | 6.4 |
| PY-F12 | token not a meter | I | 6.2 honesty, no-fair-exchange statement |
| HO-F1 | host holds model key | I | 3.13 (hub gateway) |
| HO-F2 | approval not bound to packet | I | 3.13, 3.3 |
| HO-F3 | key directory | N | hub/relay |
| HO-F4 | host as sole meter | I | 3.13, 6.4 |
| HO-F5 | quote not bound | N | hub |
| HO-F6 | settlement races | I | 3.3 |
| HO-F7 | host vanishes | A/I | 3.13 |
| HO-F8 | canary spot checks | N | hub/hosts |
| HO-F9 | host-attested verdicts | A | 6.2, 3.13 |
| HO-F10 | packet safety, tags | I | 4 #16, packet manifest from union grants |
| HO-F11 | clock, ordering, replay | A | 3.11 |
| HO-F12 | distribution, hosted memory, certification per mode | A | 3.13, 6.3 |
| MM-F1 | rollback destroys work | A | 6.1 |
| MM-F2 | staged /in dump | A | 3.4, 6.1 |
| MM-F3 | extractor laundering | I | labels supply taint (2.2, 6.1); capture-time taint is vault design |
| MM-F4 | cross-pack laundering | A | 6.1 origin |
| MM-F5 | crypto-shred residue | I | 3.2 R blobs, 3.6; vault owns the rest |
| MM-F6 | multi-device | N | 3.2 states R is device-local |
| MM-F7 | extractor failure, Q flood, Q read | A/I | 6.1 |
| MM-F8 | secrets in journal | A | 3.2 scanner |
| MM-F9 | revocation vs promoted | A | 6.1 |
| MM-F10 | P plane | N | memory design |
| MM-F11 | schema migration | A | 3.6 journal versioning |
| MM-F12 | growth, decay | A | 3.6 retention; vault owns the rest |
| AD-F1 | canaries served to honest packs | A | 6.2 |
| AD-F2 | D6 overlap | A | 6.2 |
| AD-F3 | pause timeout defaults to kill | A | 3.10, 6.2 |
| AD-F4 | requester-attested incidents | A | 6.2 |
| AD-F5 | revocation governance | N | hub governance |
| AD-F6 | receipts covert channel | A | 6.4 |
| AD-F7 | public rules, slow exfil | A | 6.2 |
| AD-F8 | ladder non-atomic | A | 6.2, 3.2 |
| AD-F9 | U rollback weaponizable | A | 6.1 |
| AD-F10 | honest author framed | A | 6.2 |
| AD-F11 | FP on honest runner code | A | 5.2 |
| AD-F12 | supervisor fooled or flooded | A | 3.10 rule 4, 6.2 |
| HI-F1 | approval launders foreign text | A/I | 6.1 |
| HI-F2 | approval not bound to what runs | A | 3.3, 6.1 |
| HI-F3 | phone approval protocol | I | 3.10 rule 3 (relay design owns the rest) |
| HI-F4 | rollback and approved items | A | 6.1 |
| HI-F5 | terminal-state table | A | 3.3 |
| HI-F6 | large outputs, apply, Accept | A | 2.9, 5.3 |
| HI-F7 | author text reaches agent | A | 7.3 |
| HI-F8 | driver downgrade UX | A | 3.11 preflight |
| HI-F9 | guarantee text | A | 4 #16, 7.3 |
| HI-F10 | approval volume | A | section 4 #12 |
| HI-F11 | hosted host consent | N | role matrix elsewhere |
| HI-F12 | visibility, accessibility | A | 7.3 |
| CR-F1 | requester incident evidence | A | 6.2 |
| CR-F2 | certifier beside signing key | N | hub; engine part: Certifier workers hold no secrets (6.3 fixtures) |
| CR-F3 | recompute overclaim | I | 6.3 attestation fields |
| CR-F4 | sleeper, fingerprinting | A | 6.3 |
| CR-F5 | certification cost, oracle | A/I | 6.3 |
| CR-F6 | LCB gameable | A | 6.3 |
| CR-F7 | wash trading | N | ranking; 6.4 note |
| CR-F8 | tested_on, model gating | A | 2.1, 6.3 |
| CR-F9 | version laundering | A/I | section 4 #17 |
| CR-F10 | author labels, taxonomy | A | 7.3 |
| CR-F11 | platform conflicts | N | governance |
| CR-F12 | legal | N | legal |
| ID-F1 | root of trust | N | hub |
| ID-F2 | TCB supply chain | A | 3.1 |
| ID-F3 | revocation, fail mode | A | 3.14 |
| ID-F4 | requester-held supervisor evidence | A | 6.2 |
| ID-F5 | log witnesses | N | hub |
| ID-F6 | key directories | N | hub/relay |
| ID-F7 | author key lifecycle | N | hub |
| ID-F8 | run token, lease, clocks | A | 3.3, 3.11 |
| ID-F9 | sybil, namespaces | N | hub |
| ID-F10 | hub metadata | I | 6.4 receipts |
| ID-F11 | erasure, key hierarchy, audit key | A/I | 3.1, 3.2 |
| ID-F12 | host spends hub model key | I | 3.13 |
| TK-F1 | Result Guard defined by adversary | A | 2.9 |
| TK-F2 | render and apply exfil | A | 2.9, 5.3 |
| TK-F3 | clarification confused deputy | A | 2.6 human, 3.10 |
| TK-F4 | result labels, D6 policy | A | 2.9, 6.2 |
| TK-F5 | write access, apply | A | 2.9 (contract only; machinery out of v1) |
| TK-F6 | long task resume | A | 3.2, 3.6 |
| TK-F7 | epoch and idempotency | A | 3.3 |
| TK-F8 | web research | A | 2.8 |
| TK-F9 | credentials, connectors | A | section 8 (excluded from v1, hook designed) |
| TK-F10 | cancellation | A | 3.3, 7.3 |
| TK-F11 | approval binds task | A | 3.3, 6.1 |
| TK-F12 | chaining, Accept injection | A/I | 2.9, 6.1; agent tool separation is the local-agent design |
| CO-F1 | canary classes | A | 6.2 |
| CO-F2 | /in dump | A | 3.4 |
| CO-F3 | requester as economic adversary | A | 6.2 |
| CO-F4 | Nebius key, ZDR, rate limits | A/I | 3.15, 3.13, 4 #16 |
| CO-F5 | memory auto-promote contradiction | A | 6.1 |
| CO-F6 | digest circularity | A | 2.1, 6.3 |
| CO-F7 | revenue per run | N | product/payments |
| CO-F8 | build phases | A | 3.17 for the engine; the rest of section 10 is architecture-level |
| CO-F9 | demo realism | A | 7.4 |
| CO-F10 | hiring agent | I | local-agent design |
| CO-F11 | rollback incoherent | A | 6.1 |
| CO-F12 | guarantee sentences, workflow requirement | A | the whole document; per-mode certification 6.3; self-test 3.11 |

---

## Appendix C. External sources used (all from research-v3 digests; nothing new fetched) and UNVERIFIED items

Sources: https://www.anthropic.com/engineering/building-effective-agents ; https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents ; https://www.anthropic.com/engineering/built-multi-agent-research-system ; https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents ; https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents ; https://cognition.com/blog/dont-build-multi-agents ; https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus ; https://docs.temporal.io/workflow-execution ; https://docs.temporal.io/encyclopedia/retry-policies ; https://www.inngest.com/docs/learn/how-functions-are-executed ; https://docs.langchain.com/oss/python/langgraph/persistence ; https://github.com/langchain-ai/langgraph/security/advisories ; https://github.com/OpenHands/software-agent-sdk (stuck_detector.py, condenser) ; https://github.com/SWE-agent/mini-swe-agent ; https://github.com/langchain-ai/deepagents ; https://arxiv.org/abs/2503.18813 (CaMeL) ; https://arxiv.org/abs/2505.23643 (FIDES, abstract only) ; https://ai.meta.com/blog/practical-ai-agent-security/ ; https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ ; https://github.com/google/cel-spec/blob/master/doc/langdef.md ; https://arxiv.org/abs/2406.12045 (tau-bench) ; https://arxiv.org/abs/2503.14499 (METR time horizon).

UNVERIFIED (carried over or introduced): n8n, Dagster severity, Mastra control flow, Agent SDK budget options, Anthropic dynamic-workflows post; Nemotron tool-calling reliability on Nebius and KV-cache behavior there; PayPal authorization validity and reauthorization; WSL2 sleep/idle and parent-death behavior; CEL and RE2-class library choice; Cedar and CaMeL README details; Temporal untrusted-code statement is from 2020; all thresholds, ceilings, defaults and field names in this document are untuned proposals; effect of label-driven gating on real task utility; whether a P/R-only milestone set is rich enough for fair partial capture.
