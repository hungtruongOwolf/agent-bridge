# Audit 10: the TASK model and its I/O (flow audit)

Date: 2026-10-07. Subject: `architecture-v2.md` (v2) plus `research-v3/01` and `02` (workflow engine proposals, not yet merged into v2). No external facts are used here; everything below is derived from reading those files. "v2 s.X" = section of architecture-v2.

## 0. What v2 actually says about a task (the gap)

There is no Task object in v2. The word appears only as: Biscuit caveat "task" (4.4), namespace `task/<id>` (4.1), scratch plane T "destroyed at task end" (4.1), "pre-task Merkle checkpoint" (4.5), and the manifest field `result_schema: schemas/result.json` inside the pack's `return` phase (5.2). Consequences: the task text, input folders, parameters, output kind, acceptance criteria, deadline, budget, mode constraints, and sinks are not specified by anyone. Every field that does exist (result schema, acceptance_checks, memory.proposes schema) is declared by the PACK AUTHOR, i.e. by the adversary.

## 1. Proposed Task spec (what the flow must carry; our proposal)

```
TaskSpec (requester-owned, immutable once approved, content-hashed)
  task_id, epoch(fencing), created_by_device
  instruction: text (+ taint label; may contain private data -> never sent to hub unredacted)
  inputs:  [ {kind: lens | folder | file | artifact_from_task(task_id,out_id) | param,
              selector, snapshot_hash, max_sensitivity, classification_report_hash} ]
  needs:   {web: none|public-only-stage, connectors: [ {id, ops:[...], rw:ro|rw} ], write_targets:[...]}
  outputs: [ {kind: answer|report|patch|file_set|table|proposal,   # CLOSED platform registry
              envelope_schema (platform-owned), max_bytes, sinks: [display|apply_to:<path>|share:<audience>],
              inherited_label}]
  acceptance: {deterministic: [...], human: required|optional}     # requester-owned, pack may only add
  limits: {usd, tokens, wall_s, steps, human_wait_s, question_budget}
  mode_constraints: {must_stay_local: bool, allowed_modes}
  lifecycle: {cancel_policy, resume_policy, revalidate_on_resume: [revocation, digest, input_hash, auth]}
```

## 2. Flow as a state machine (actors and what each holds)

Actors: **Req** (human), **RA** (local requester agent, Nemotron, full vault read), **Vault** (vaultd, U/Q), **DC** (Disclosure Compiler), **Sup** (Supervisor), **Side** (Sidecar: Model Proxy, Memory Broker, Tool Broker, Egress, Result Guard, detectors), **Cell** (untrusted pack), **Hub** (registry, escrow, run tokens, relay), **Auth** (pack author, offline), **Host** (Hosted only), **PP** (PayPal).

Legend: [v2] defined in v2; [v3] only in research-v3 proposals; [NONE] undefined anywhere.

| # | State | Trigger / actor | State held by | Defined |
|---|---|---|---|---|
| S0 | DRAFT | Req or RA writes instruction | RA context only | [NONE] no spec object |
| S1 | MATCHING | RA calls hub `browse_agents` with task text | Hub sees query | [v2 partial] hub-sees-task-text not analysed |
| S2 | QUOTED | Hub card + price; Hosted: host-signed quote | Hub, Req | [v2] |
| S3 | APPROVED | Approval card per (digest, mode, lens, budget) | Req, DC | [v2] binds NOT task text, inputs content hash, outputs, sinks |
| S4 | AUTHORIZED | Hub issues run token, PP AUTHORIZE at cap | Hub, PP | [v2]; validity windows [v3 only] |
| S5 | STAGED | Vault stages ro snapshot of lens slice to /in; canaries; Biscuit | Vault, Sup | [v2] lens only; folders/files/artifacts [NONE] |
| S6 | RUNNING | Cell planner->worker->returner | Cell (T), Side (journal, accounting) | [v2]; workflow nodes [v3] |
| S6a | WAITING_CLARIFICATION | Cell asks Req a question | Sup, Req | [NONE] (v3 `ask` node only) |
| S6b | WAITING_WEB / CONNECTOR | Cell needs web or private API | Side | [NONE] (v2 forbids network tools in private-data runs) |
| S6c | PAUSED | Detector D6/D8, budget, user | Sup | [v2] "freeze, keep state"; resume [v3 only] |
| S7 | RETURNING | Cell emits result via socket | Side | [v2] |
| S8 | GUARDED | Result Guard: schema, size, inert render, overlap/canary | Side | [v2] schema is pack-supplied |
| S9 | DELIVERED_UNTRUSTED | Result to Req/RA; proposals to Q | RA, Vault(Q) | [v2] |
| S10 | ACCEPTED / REJECTED | Acceptance checks, human or RA Accept | Req/RA, Hub | [v2] who may Accept [NONE] |
| S11 | APPLIED | Patch/files written into requester data, or connector write | Req machine / external | [NONE] |
| S12 | CAPTURED | Partial/final PP capture, holdback | Hub, PP | [v2] |
| S13 | SETTLED | Payout, receipt (3.4), Cell destroyed, T wiped | Hub, Auth | [v2] |
| T1 | KILLED / QUARANTINED / REVOKED | Detector ladder | Sup, Hub | [v2] |
| T2 | CANCELLED | Req | ? | [NONE] |
| T3 | EXPIRED / FAILED / BUDGET_STOPPED | timeouts, caps | ? | [NONE] / [v3] |

Edges not defined in v2: S6->S6a->S6, S6->S6b->S6, S6c->S6 (resume), any->T2, S10->S11->S12 ordering, task output -> next task input (multi-pack), S6 -> re-dispatch to another pack after T1/T3.

## 3. Step-by-step interrogation (fail / repeat / reorder / concurrent / timeout / malicious / offline / state changed)

**S1 matching.** Malicious/curious hub: task text in `browse_agents` queries is content, but B2 only promises "hub never gets vault content". RA is an LLM that may paste private details into a query. Fix needed: query is built from a task *category + redacted summary* by DC, not raw text. Hub offline: cannot browse; no cached-card path defined. Out of order: card changes between browse and approve (price/digest swap) - digest pinning in S3 covers digest, not price/terms.

**S3 approval.** Approved tuple is (digest, mode, lens, budget). Same tuple, different task = no new approval ("once per" tuple, 6.2 step 2). State changed in between: lens tags resolve at stage time, so records added after approval (new sensitive items tagged `finance`) enter the snapshot unseen. Byte-exact preview is impossible for a folder or a large lens: user rubber-stamps (approval fatigue already listed 4.8). Repeated tap on phone/desktop: two approvals, two run tokens, two AUTHORIZEs (no idempotency key defined).

**S4 authorize.** Sandbox tokens expire in 3-8 hours (v2 s.9); a long task or a human wait outlives the hold; capture of expired authorization fails after the work is done. Hub offline at start: refuse (fail closed) - fine, but free/open packs are also blocked, undefined. Duplicate run token reuse: "one-time" but no consume-atomically rule stated for retries after a Sidecar crash.

**S5 stage.** Folder inputs: symlinks/hardlinks, `.git` history, `.env`, SSH keys inside the folder; lens "sensitivity" exists per vault record but folders have no tags. Snapshot vs live drift (TOCTOU) between approval and copy. Size: copy of GB data into WSL2 VM on DrvFs (UNVERIFIED perf). Malicious file content (prompt injection in the user's own data) is not in scope of the lens model.

**S6 running.** Cell crash: T wiped, Side journal exists only as audit log, no resumable state. Model context overflow: v2 has no context policy (min_context 32000 only in manifest). Heartbeat/stuck: none. Concurrent runs of two packs on one vault: both read via Broker, both propose to Q; no per-task dedupe.

**S6a clarification.** See finding F3.

**S6b network/connectors.** See F8, F9.

**S6c pause/resume.** Pause keeps state in the Cell; resume after hours: capability (Biscuit) expiry, revocation list freshness, run token, PP auth all stale; /in snapshot stale; vault changed (records invalidated or crypto-shredded). Resume on a different device (journal replication, 4.6): split brain.

**S7/S8 result.** See F1, F2, F4.

**S9 delivery.** RA reads untrusted output. Reader/Scribe split covers vault writes only, not RA's *other* tools (web, hub, payments, shell).

**S10 accept.** See F12.

**S11 apply.** See F5.

**S12-S13 settle.** Capture after acceptance, but acceptance can precede application/testing; dispute window 180 days; cancellation mid-run unspecified (F10).

## 4. Consistency checks against the rest of v2

1. 4.7 "Pull packs get no writable persistent store" vs any resumable long task (needs persisted workspace) vs 4.1 `T destroyed at task end` vs namespace `task/<id>` in the vault list. Three statements, no reconciliation.
2. 4.1 Q "Never readable by packs" vs 4.6 demo "pack B already knows the project goal pack A produced". Works only after acceptance into U; but profile/procedural writes are daily-digest batched (4.3) and foreign-derived semantic never auto-promotes. So chaining is blocked by human latency, or someone will weaken Q.
3. 3.3/6.2 "no network interface" vs decisions.md Tavily web tool vs 7.1 D7 "sink is external" vs 4.4 "no network tools in private-data runs". Web research on private data is neither supported nor explicitly forbidden in the listing.
4. 7.2 ladder step 7 "roll back U" does not cover files already applied (S11) or external connector effects.
5. 3.4 receipts/ratings are the only author-bound channels, but the *result itself*, once rendered or applied, can fetch URLs and run code (F2, F5): contradicts "author receives nothing during the run" unless renderer/apply path is locked down.
6. 5.2 `refund.acceptance_checks` and `result_schema` are in the author-controlled manifest; principle "manifest is a request, never a grant" is not applied to them.
7. 7.1 D6 (egress overlap with lens, kill on confirmation) vs the purpose of the task: an honest report legitimately contains lens data. D6 is defined on egress; for results the overlap policy is undefined, so either every honest long report is flagged or the threshold is so loose it detects nothing.
8. v3 `workflow:` (bounded loops, `ask`, `human`, journal on Sup side) is not in v2; items F3/F6/F7 are only solvable if v3's requester-side journal is adopted AND constrained by the findings below.

## 5. Ranked findings

See the structured output returned with this audit; IDs F1..F12 map to the list there. Short index:

F1 pack-owned result schema and acceptance checks make the Result Guard adversary-defined.
F2 render-time and apply-time fetches reopen an author-bound exfil channel despite "inert render".
F3 clarification questions are a confused-deputy read of the full vault by the local agent.
F4 results lack inherited sensitivity labels; D6 overlap policy undefined; over-disclosure to third parties.
F5 write access/patch application path undefined (code-in-patch, hooks, CI, partial apply, rollback).
F6 resume across Cell restarts contradicts 4.7, ignores stale inputs/vault shred/revalidation.
F7 split brain and duplicate submissions: no run epoch/fencing/idempotency.
F8 web research in a no-NIC cell: no mixed-task design; search queries as exfil.
F9 credentials/private APIs: handle-only is unspecified; connector args are an exfil/write sink.
F10 cancellation undefined; races with kill, capture, void; free-riding and forged-incident abuse by the requester.
F11 approval binds to (digest, mode, lens, budget), not to the task, inputs, outputs; folder inputs unclassified; byte-exact preview does not scale.
F12 multi-pack chaining conflicts with Q rules; Accept authority exposed to injection by pack output.

## 6. Minimum additions to v2 (summary of fixes)

- Add TaskSpec (s.1) as a first-class, requester-owned, hashed object; approval binds its hash.
- Closed registry of output kinds with platform-owned envelope schemas; pack schemas may only narrow.
- Results carry labels (max sensitivity read, trust tier 0); sinks declared in the TaskSpec; DC re-runs on any flow from result to another pack, hub, web, share or apply.
- Task states T2/T3, a single transition table with terminal-state absorption and idempotent events keyed by (task_id, epoch, event_id).
- Requester-side journal and artifact store (as v3) with typed JSON only; workspace snapshot is supervisor-owned, re-mounted ro or as fresh copy, never trusted across packs.
- Two-stage tasks (public stage with network and empty lens; private stage with lens and no network), joined only via the DC.
- Connector broker: declared ops, ro default, args schema, sidecar-held credentials, writes only through the apply path.
