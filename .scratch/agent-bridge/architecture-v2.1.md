# agent-bridge: architecture v2.1 (round 3 integration)

Date: 2026-10-07. This file does not replace `architecture-v2.md`; it is the **delta and verdict** on it. Read it together with:

- `architecture-v2.md` (the base design; sections cited as "v2 s5.2" etc.)
- `design-harness-workflow.md` (cited "WF s3.3"): the harness as an automated workflow, the engine `flowd`, the static analyzer. Link: [design-harness-workflow.md](design-harness-workflow.md)
- `design-state-machines.md` (cited "SM s3.3"): six behavioral flows as explicit state machines. Link: [design-state-machines.md](design-state-machines.md)
- `audit/01..11` (the 132 audit findings; ids written `PL-F2` = pack lifecycle finding 2; prefixes PL, PR, PAY, HO, MEM, DEF, HUM, CERT, ID, TASK, CON as in SM s0)
- `../decisions.md`

Paths: `.scratch/agent-bridge/{architecture-v2.md, design-harness-workflow.md, design-state-machines.md, audit/}`.

Conventions. No new external research was done for this file. External facts are only those already cited in the two design files or in `research*/`; anything not confirmed from a primary source is marked UNVERIFIED. Every threshold, fee, TTL, percentage, field name and default is our own untuned PROPOSAL unless a source is cited. The one PayPal fact set that SM says it verified (29-day hold, 3-day honor period, capture "subject to risk and money availability", reauthorization gives a new id, void exists) comes from https://developer.paypal.com/docs/checkout/standard/customize/authorization/ ; I did not re-fetch it for this file.

TL;DR. The behavioural flow of v2 was **not ready** to build: the audit found 132 problems (25 high, 105 medium, 2 low, none refuted). The two new designs (the `flowd` workflow engine and the state machines) handle most of them, but combining the two documents showed 11 contradictions between them and 6 new gaps (the worst: if the requester finishes a run and then goes silent, the hold is voided and the author gets nothing). The harness is now a signed workflow program run by a trusted engine with a journal, checkpoints, resume, a budget and gates; it is no longer a folder of prompts and tools, and no longer three fixed phases. Section 7 lists the decisions still open for the project owner.

---

## 0. Is the behavioral flow OK? (plain answer)

**No, not as written in v2. With the two new designs it is mostly closed on paper, but nothing is built or measured, and a few holes remain.**

### 0.1 Counts

132 behavioral findings were audited across 11 flows (12 per flow). Severity scale used by the audit: critical, high, medium, low.

| Severity | Count |
|---|---|
| critical | 0 |
| high | 25 |
| medium | 105 |
| low | 2 |
| **total** | **132** |

Verification status: 105 confirmed by the auditor, 27 marked `not-checked` (the auditor did not independently verify them; both design files adopted them conservatively). Refuted: **0**.

| Flow | high | medium | low | not-checked |
|---|---|---|---|---|
| 1 Pack lifecycle | 3 | 8 | 1 | 2 |
| 2 Pull run end to end | 1 | 11 | 0 | 1 |
| 3 Payment and escrow | 1 | 10 | 1 | 3 |
| 4 Hosted mode | 2 | 10 | 0 | 4 |
| 5 Memory flows | 3 | 9 | 0 | 3 |
| 6 Active defense | 4 | 8 | 0 | 2 |
| 7 Human-in-the-loop | 2 | 10 | 0 | 4 |
| 8 Certification and ranking | 2 | 10 | 0 | 4 |
| 9 Identity, keys, trust roots | 3 | 9 | 0 | 1 |
| 10 Task model and I/O | 2 | 10 | 0 | 0 |
| 11 Consistency of v2 vs research | 2 | 10 | 0 | 3 |

Found during this integration (not by the audit; my own ratings, unaudited): 11 contradictions between the two new design files (section 3.1) and 6 new gaps (section 3.2: 1 high, 3 medium, 2 low).

Disposition of the 132 after the two designs: about 119 have a designed mechanism in WF/SM. 8 carry an explicitly accepted residual (PL-F7 full TUF, PR-F4, PAY-F1, PAY-F7, HO-F8, DEF-F7, TASK-F4, CERT-F4 partly). 13 pointed to a design document that did not exist; this file closes 6 of those (CON-F8 build order, CON-F9 demo, CON-F12 guarantee rewrite, HUM-F9 data-flow strip, TASK-F8 and TASK-F9 via WF s2.8 and s8). **7 still have no owning design**: CERT-F2 (hub trust-domain and key management), CERT-F4 (Certifier fingerprint resistance spec, partly in WF s6.3), CERT-F11 (platform-as-referee governance), CERT-F12 (legal), ID-F10 (hub metadata privacy), PAY-F10 (anti-wash weighting) and HUM-F8 (non-WSL fallback driver). They are listed in section 3.3.

### 0.2 Top problems found (grouped; the number is how many findings share the root cause)

1. **In Pull the requester controls the supervisor that signs every verdict (9 findings: PL-F2, PAY-F1, DEF-F4, CERT-F1, ID-F4, CON-F3, PR-F10, TASK-F10, HO-F9).** The requester has the result on disk, then fabricates or provokes a "canary hit" and gets the hold voided, the author's payout frozen and a revocation proposed. v2 7.3 said a canary alone never hurts an author while v2 7.2 did exactly that. Fix: every Pull verdict is labelled requester-attested; money moves to HOLD/DISPUTE, never final VOID of delivered work; author penalties need Certifier reproduction or N independent corroborations; non-refundable floor fee; hub-issued canary seed committed before the run (SM s1.5, s3.4, s5.4, s5.5; WF s6.2). The underlying fact stays: **Pull has no fair exchange**; the loss is capped, not removed.
2. **The harness could not do long, hard tasks and the run had no durable state (8 findings: PL-F6, PR-F1, PR-F3, PR-F2, ID-F8, TASK-F6, TASK-F7, CON-F12).** Fixed plan/work/return phases, a one-time run token, no run record, no resume, no idempotency, undefined sleep/crash behavior, a PayPal hold that expires after 3 days. Fix: workflow program plus engine plus journal and lease (WF s1-s3), hub and supervisor run state machines with idempotency keys and an outbox (SM s1-s3).
3. **Rolling back U on incident destroys legitimate work, and foreign text laundered through one-click accept or through the local agent's own episodic summaries becomes "trusted" memory (9 findings: MEM-F1, MEM-F3, MEM-F4, MEM-F9, HUM-F1, HUM-F4, DEF-F9, CON-F5, CON-F11).** Fix: immutable `origin`/`derived_from`, endorsed-foreign trust tier 1, taint set at capture, run-scoped compensating revert instead of rollback (SM s7.4-s7.6).
4. **The staged `/in` snapshot defeated the Broker (3 findings: PR-F6, CON-F2, MEM-F2) and canaries were either unreachable or served to honest packs (DEF-F1, CON-F1).** A malicious pack could `cat /in/*` with no accounting; an honest pack that listed files tripped a KILL. Fix: no whole-slice mount, closed staged set served only through the Broker, per-step grants, three canary classes with D2-soft/D2-hard (WF s3.4, s6.1, s6.2; SM s2.6, s5.1).
5. **Trust roots and freshness (8 findings: PL-F1, PL-F5, PL-F7, ID-F1, ID-F3, ID-F5, CERT-F3, CON-F6).** The digest contained the certification that depends on the digest; "anyone can recompute ranking" and "transparency log" were overclaims for a single-writer hub log; revocation had no freshness or fail mode; Certifier ran attacker code beside signing keys. Fix: certification and listing become separate signed documents, whole-list signed revocation with `seq` and `valid_until`, Merkle log with signed heads and pinned heads, signer separated from Certifier (SM s6.3-s6.5), with a full malicious-hub model deferred.
6. Also high: Hosted gave a hub-issued Nebius key to a hostile host (HO-F1, ID-F12); Hosted approval not bound to packet bytes or host (HO-F2); Pull verdict race and non-atomic ladder (DEF-F8); result rendering and patch apply re-opening an author-bound exfil channel (TASK-F2); Result Guard defined by the adversary through `result_schema` (TASK-F1); secrets reaching the immutable journal (MEM-F8); crypto-shred residue (MEM-F5); D6 overlap and pause-timeout-means-kill false positives (DEF-F2, DEF-F3, HUM-F5); author key takeover (PL-F3); our own TCB with no signed release path (ID-F2).

### 0.3 What was refuted (and what was not)

- **No audit finding was refuted.** The auditor's `verified` field is `confirmed` for 105 and `not-checked` for 27; none is `refuted`. I will not claim otherwise.
- What *was* refuted or retracted are **claims in v2** (they stay out of the guarantee list, section 6.2): "nothing leaves"; "canary hit alone never affects the author" (contradicted by v2 7.2); "ranking is recomputable by anyone"; "transparency log"; "revenue per run" as a metering fact; "byte-exact preview" for a live semantic query; "ZDR enabled by hub" for Pull; "per-task Nebius key with budget" for a host; "fresh context per phase" in a single Cell; "roll back U to a checkpoint"; "Hosted protects IP".
- **Suggested fixes the verifier narrowed or rejected as too heavy for this stage** (so they are *not* in the build plan): full TUF roles and multi-operator witnesses (PL-F7, ID-F5); a hub transparency-log design for host keys (HO-F3, replaced by TOFU-pinned signed keys); full hub-countersigned receipts and gateway for hosted metering beyond the hub gateway (HO-F4); the whole APPLY machinery for patches (TASK-F5, v1 returns inert results); connectors with credentials (TASK-F9, excluded from v1); a full folder-grant system (TASK-F11, deferred to a ticket); the SHA-1 concern (PL-F9, skipped, SHA-256 tree digest covers integrity); the full key hierarchy and hardware keys (PL-F3, ID-F7: hackathon implements only the cheap parts); ID-F1 rated high but "not a hackathon blocker".

### 0.4 Accepted risk (stated openly, not fixed)

- Pull has no fair exchange (requester can keep the output; supervisor is theirs). Mitigated: floor fee, reject-rate score, caps for new requesters, dispute path. Owner decision D-14.
- Covert timing channels and natural-language steganography in the allowed result text; size caps bound capacity but do not close it (DEF-F7, TASK-F4).
- Detector rules are public; slow exfiltration inside the lens may evade (DEF-F7). The guarantee is "the pack sees only the lens and the output channel is bounded", not "detectors prevent theft".
- Money recovery is bounded by the reserve and the 180-day dispute window; data already exposed to a malicious pack or host cannot be recalled (PAY-F7). PayPal seller protection for intangible AI services is UNVERIFIED, so the hub carries residual dispute risk.
- A malicious hub or MITM is out of scope for v1 (PL-F7, ID-F5); Unsealed Hosted host-key authenticity is hub-trusted.
- Hosted: host is root and reads the packet; a host that copies without using is undetectable; verdicts are host-attested (HO-F8, HO-F9).
- Sandbox 0-day; Nebius sees prompts; provider timing and size side channels.
- Class O packs (third-party runner loops) are partly blind to Progress Guard and cannot be replayed mid-step (WF s3.9, A.2 N2).
- Replay audits engine decisions, not model behavior; static analysis is only as sound as tool metadata (WF A.3).
- A stochastic or time-bomb pack may not reproduce under Certifier replay, so a real incident can end INCONCLUSIVE (SM s5.5).
- Authors of low-volume packs see no aggregate until k=20 distinct requesters exist (SM s3.10; k is a proposal); cold-start feedback comes from Certifier suites instead.
- The model call is treated as a sanctioned, labelled sink in the Rule-of-Two analysis (WF s4 #5), which differs from the research-v3 suggestion to treat it as external communication. It is a proposal, shown on the approval card, and in Hosted the sink is the hub gateway.
- Offline devices and lost devices keep data after a shred until they sync or are removed (MEM-F5, MEM-F6).

---

## 1. The harness, restated as an automated workflow

### 1.1 Definition (replaces v2 s5 intro, "folder with prompt and tool list" and the fixed three phases)

> A **harness** is a content-addressed, signed **program in a closed workflow language**, with four layers: (1) a **workflow graph** (`workflow.yaml`: typed steps, branches, bounded loops, bounded fan-out, verification gates, human checkpoints, milestones); (2) **step contents** (prompts, skills, schemas, rubrics, few-shot demos, fixed code leaves, tool-catalog selections: the H plane the improvement loop edits); (3) **policies** (retry, timeout, budget, stuck handling, context, human wait, recovery); (4) a **capability envelope** (per-step grants of tools, memory lens, model class, mounts, network class; the union is the ceiling on the approval card).
>
> An **agent** is a pinned model plus the executors that run its steps. A **pack** is a harness plus manifest, evals, license and provenance. The **engine** `flowd` is platform code, not part of the pack, versioned and certified separately.

What the harness controls: what is done, in which order, with which authority, and when it is considered done (gates and milestones, not the model's say-so). What it does not control: what the model says inside a step, or anything below the sidecar. The manifest stays "a request, never a grant".

Full design: [design-harness-workflow.md](design-harness-workflow.md). Summary of the parts that matter for the rest of this file:

### 1.2 The engine (WF s3)

| Aspect | Design |
|---|---|
| Where | `flowd`: own OS user, no NIC, unix sockets only, in the requester's sidecar process group; not inside the Supervisor and not inside the Cell (WF W2). Memory-safe language (Rust or Go, UNVERIFIED choice). A few thousand lines, fuzzed parser and template renderer, differential tests of label join and CEL evaluation. |
| Authority split | `flowd` is a **pure function of the run journal**. The **Supervisor** is the only journal writer, signer, lease holder, outbox owner and kill authority (WF W3). `flowd` validates step outputs; the Supervisor appends and signs (this resolves CC-2). |
| Journal and Run Store (plane R) | Append-only typed JSON lines with length+CRC framing, hash chain, signature; torn tail truncated with a recovery marker, only mid-chain mismatch is tamper. Blobs content-addressed, encrypted under a per-run key, with `derived_from_key_ids` so shred reaches them. Device-local, never replicated, never pack-writable (WF s3.2). |
| Step protocol | scheduled, started (fsync), execute, staged, gates, committed (fsync) with state delta and effect intents; effects are applied by the Supervisor idempotently by key `H(run_id, step_path, iteration_path, input_hash)` (WF s3.4, s3.7). A step never sees the blackboard, only its declared `reads`. |
| `llm` executor | Bounded agent loop run by `flowd` itself for tier-0 packs, so a data-only pack executes no pack code; every turn is journaled, which enables turn-level replay. Needs a Nemotron tool-calling smoke test first (UNVERIFIED). |
| Checkpoint and resume | Every `step_committed` is a checkpoint. Resume checklist (revocation, digest and engine major, model id, snapshot hash, hold and honor window, token, quarantine state) before any step; terminal-by-security outcomes are never resumed; single device in v1 (WF s3.6). |
| Retries and faults | Error classes `transient / invalid_output / gate_fail / budget_exceeded / step_timeout / policy_denied / resource_exhausted / fatal_security / human_timeout`; retries live inside budgets; infra retries are never charged to requester or author (WF s3.8). |
| Budgets | Hierarchical run > block > step; engine-held reserve that no step can spend; first cap hit moves the run to WINDING_DOWN and a schema-valid partial result is assembled **with no model call**; only `verified` items back milestones (WF s3.16). |
| Progress Guard | Stuck detection from the engine's own journal: nudge, replan, human, abort; never a strike (WF s3.9). |
| Human nodes | One pause mechanism (`human`: approve, ask, review, plus engine-injected `pause_review`); every timeout maps to a no-fault outcome (WF s3.10). |
| Liveness | INFRA_FAULT distinct from tamper; lease chain; monotonic clocks minus suspended time; sleep inhibitor; preflight with fast conformance subset (WF s3.11). |
| Hosted | Same stack under the host's root; no Nebius credential to the host; failover off; all verdicts host-attested (WF s3.13). |

### 1.3 The workflow spec (WF s2)

- **Format**: JSON or a strict YAML subset (no anchors, aliases, duplicate keys, YAML 1.1 coercions); one shared parser library with a conformance corpus; digest over raw bytes of every file; non-canonical input rejected, not normalized (WF s2.1).
- **Values carry labels** `{integrity, conf, src}` computed by the engine; declassification only through quarantined enum extraction (charged to a per-run bit budget), a `human` node, or a deterministic platform rule; never by LLM judgement (WF s2.2).
- **Expressions**: CEL with a cost limit, no clock, no randomness, no environment (WF s2.3; CEL library choice UNVERIFIED).
- **Closed step kinds**: `llm`, `tool`, `code` (leaf, nested no-network sandbox), `adapter` (third-party runner in a Cell), `gate`, `branch`, `loop` (bounded, with stagnation exit), `map` (bounded fan-out), `parallel` (at most 4 branches), `human`, `return`, reserved `subflow` (WF s2.6). Only `loop` blocks form cycles.
- **Gates have trust classes**: platform (P) and requester (R) checks may drive milestones, money and acceptance; pack code (K) and LLM judge (J) checks may only steer loops. Artifacts are hash-frozen before a gate and only the hash that passed may reach `return` (WF s2.7).
- **Scopes**: a scope with lens data and any network class is rejected; web research is a PUBLIC scope then a PRIVATE scope (WF s2.8).
- **Task contract is platform-owned**: closed output-kind registry, pack `result_schema` may only narrow; effective checks = platform + TaskSpec + pack extras (extras can only add); Accept is never a workflow node or an agent tool (WF s2.9).
- **Milestones**: reached only through committed P/R gates on frozen artifacts; author price fixed per accepted milestone, not per attempt or per token (WF s2.10).
- **Assurance classes** computed by the analyzer: S static, E enveloped (reserved), O opaque (adapter steps); ranked separately (WF s1.3).
- **Static analyzer** (18 checks; WF s4): termination and worst-case cost at or below declared cap, permission union and capability-set hash, Rule of Two per step, label-flow paths, untrusted-branch check, gate integrity, approval budget (proposal: 6 cards per run), context fit (at most 60% of declared context), similarity against registry, scope rule, the four-line "where your data goes" strip. The requester re-runs it on the downloaded digest.
- **Reference harnesses**: private-data analyst (class S, worst-case USD 2.87 of 3.00 declared, hand-computed) and code patcher (class O); templates `plan-work-return`, `plan-map-reduce`, `generate-verify-refine`, `long-task`, `route-then-specialist` (WF s2.11-s2.13).
- **Not expressible in v1** (with reasons and a designed hook each): untrusted data steering control flow, arbitrary cycles, model-spawned sub-agents, plan expansion, web and lens data in one scope, connectors with credentials, pack-to-pack delegation, pack-side persistent memory, LLM declassification, pack-defined money gates, mid-run free-form conversation, applying a patch to the live tree (WF s8).

### 1.4 Tooling and measurement (answers "how is it developed, measured, improved")

- Authoring: `bridge flow init/lint/analyze/graph/dry-run/run --synthetic/replay/chaos/test/coverage/cost/explain/optimize` (WF s7.1); trace viewer over the journal (WF s7.2).
- Quality measurement by the Certifier per (workflow digest, model id plus revision, mode, suite version, engine conformance hash): gate-backed success separately from judge-based success, pass^k, cost and time percentiles, retries and gate-fail per node, stuck rate, resume success rate, structural conformance tests (chaos-resume, replay determinism, effect idempotency, budget enforcement), fault injection, security fixtures including sleeper and fingerprint-resistance tests (WF s6.3).
- Improvement: optimizer edits typed H-plane content and parameters only; topology edits need human review; budgets, `max_iterations` and permissions never widen automatically; a permission or budget-cap widening is a MAJOR version; the optimizer iterates on a free public-dev suite and touches the private suite only at promotion (WF s6.4, v2 s5.5).
- Gap I found (N-3): the Certifier needs a scripted answerer for `human` nodes or its suites cannot run workflows that contain them (section 3.2).

---

## 2. State machines (summary)

Full tables: [design-state-machines.md](design-state-machines.md). Three rules run through all of them: **no component trusts another's claim about a domain it does not own** (hub owns money, lease, entitlement, revocation; Supervisor owns the Cell, stage, local incidents; vaultd owns records; SM s1.1); **every state change is one transaction plus outbox intents, fsynced before the side effect** (SM s1.3); **terminal states absorb** (late events are logged no-ops, SM s1.2).

| # | Machine (owner) | States (abridged) | Rules that changed v2 behavior |
|---|---|---|---|
| a | **Pull run** (Supervisor WAL + hub run row; SM s2) | CREATED, PREFLIGHT, STAGING, CARD_PENDING, APPROVED, AUTHORIZING, AUTHORIZED, STARTING, RUNNING (sub: STEP_ACTIVE, CHECKPOINTING, GATE_WAIT, STALLED, SUSPENDED_INFRA, PAUSED_DEFENSE, RESUMING, CANCELLING), WINDING_DOWN, ASSEMBLING, DRAINING, CLEANING, RESULT_READY, DONE | **Stage then card then AUTHORIZE last then start.** Requester mints `run_id`; every hub call carries `run_id:op:seq` as idempotency key and as `PayPal-Request-Id`. Token states ISSUED, BOUND, STARTED, SETTLED or VOIDED; token only starts, a hub **lease with epoch** continues. Cleanup precedes capture. Boot reconciler per WAL state (SM s2.12). Resume at most 3 times, checklist first, never on a second device. Hub reaper voids auth with no STARTED in 10 min. |
| b | **Payment ledger** (hub row, CAS on `rev`; SM s3) | NONE, ORDER_CREATED, AUTHORIZED, FLOOR_CAPTURING, FLOOR_CAPTURED, OUTCOME_CAPTURING, CAPTURED, RESERVED, PAYOUT_SCHEDULED, PAID; side: REAUTH_PENDING, AUTH_LAPSED, CAPTURE_DECLINED, VOID_PENDING, VOIDED, DISPUTE_HOLD, REFUND_PENDING, REFUNDED, CHARGEBACK, FROZEN | Hold is **never a guarantee**; non-refundable **floor fee** plus per-milestone **outcome fees**; authorization **segment of 66 h** (3 days minus 6 h); accept deadline `min(48 h, honor_left - 6 h)`; accept, kill, cancel, void and capture are mutually exclusive through one CAS row; outbox and reconciler; payout only after capture COMPLETED, by payer id, behind a rolling reserve; "payment hold", not "escrow". Master outcome-to-money table in SM s3.4. |
| c | **Hosted task** (hub authoritative; SM s4) | QUOTED, APPROVED, AUTHORIZED, DISPATCHED, RUNNING, RESULT_COMMITTED, RESULT_ACKED, ACCEPT_PENDING, SETTLING, DONE; HOST_LOST, TIMED_OUT, CANCELLED, VOIDED, DISPUTED, HOST_REFUSED, STALE_QUOTE | Hub co-signed quote bound to task, packet hash, host key; single-use signed **Hosted approval object**; sender-authenticated envelope, host checks hold before decrypting; **no Nebius credential to hosts** (hub gateway with per-task bearer); heartbeats then HOST_LOST then revoke gateway token and void; failover off; fault-split table; packet default-deny to user-confirmed `low` plus a deterministic scanner. |
| d | **Incident** (Supervisor, durable; SM s5) | DETECTED, INTENT_LOGGED, FROZEN, EVIDENCE_SNAPSHOT, KILLED, LOCAL_DENYLISTED, CLASSIFIED, CLAIM_QUEUED, CLAIM_FILED, ADJUDICATING, RESOLVED{UPHELD, REJECTED, INCONCLUSIVE, DATA_INDUCED}, MEMORY_REVERTED, APPEAL_OPEN, CLOSED | **Freeze, snapshot, then kill** (evidence is not destroyed first); idempotent rungs keyed `(run_id, rung)`; one incident per run, max severity wins; attribution step marks **DATA_INDUCED**; requester-attested claims go to **DISPUTE_HOLD** not VOID; hub-wide revocation needs Certifier reproduction (class C) or N=3 independent aged requesters (class N). |
| e | **Pack version, key, revocation** (hub; SM s6) | DRAFT, VALIDATED, SUBMITTED, CERTIFYING, REJECTED or CERTIFIED, PUBLISHED, DEPRECATED, YANKED, ADVISORY, SUSPENDED, REVOKED(reason); key: ACTIVE, ROTATING, COMPROMISED(distrust-from T); attestation: CURRENT, STALE, ORPHANED | Reason enum `malicious-confirmed, vulnerability, key-compromise, licence, author-request, advisory, superseded` each with its in-flight, money and memory action (SM s6.2); revocation is **one signed whole-file list** `{seq, issued_at, valid_until, prev_list_hash, entries}`, never a per-pack query; client max age by sensitivity 24 h / 12 h / 1 h; expiry mid-run pauses, never kills; free sideloaded packs labelled "unrevocable". Digest over author files only (raw bytes); attestation and listing are separate signed documents; capability-set hash enforces MAJOR on widening; write-once CAS on `(publisher, id, version)`. |
| f | **Vault write, Q, promotion, revert** (vaultd; SM s7) | CAPTURED, SCANNED, JOURNALED, EXTRACTION_PENDING, EXTRACTING, PROPOSED, GATED, ACTIVE; Q: PROPOSED, ENDORSED, REJECTED, EXPIRED, DISCARDED_RUN, STALE; record: ACTIVE, SUPERSEDED, INVALID, REVIEW, SHREDDED | **Secret scanner at capture before the journal**; taint set at capture; independence from disjoint ancestry in the journal DAG; Q read only by a Reader session; immutable `origin`/`derived_from`; endorsed-foreign = trust tier 1; **run-scoped compensating revert** replaces "roll back U"; shred contract with keyed commitment instead of plain content hash. |

Shared vocabulary (SM s1.5-s1.8), with the rename from CC-3 applied:

- **Attestation source** (who vouches): H hub-observed, R requester-attested, O host-attested, C certifier-reproduced, N independently corroborated (N=3 aged requesters, proposal). R may trigger local effects and a counted claim; it can **never** trigger a final VOID of delivered work, a payout freeze that outlives adjudication, a hub-wide revoke, a slash, or a public incident count.
- **Evidence kind** (what was seen; WF s6.2, with the letter `C` retired to avoid the collision): TAMPER, EGRESS, BOUNDARY, PROGRESS, INFRA, DATA_INDUCED. Default consequences: TAMPER and EGRESS kill; BOUNDARY deny and strike; PROGRESS nudge/replan/abort; INFRA freeze, retry, no strike; DATA_INDUCED contain, no author effect.
- **Fault classes** decide who pays and who is struck (SM s1.6): INFRA_FAULT, RESOURCE_EXHAUSTED, REQUESTER_FAULT, PACK_FAULT, DATA_INDUCED, UNCONFIRMED_PAUSE, INCIDENT_CLAIM, HOST_FAULT/AUTHOR_FAULT.
- **Waiting on a human** is one family with kind, channel, deadline, default and effect on each clock (SM s1.7, WF s3.10). No wait default is "kill and punish".
- **Unified run outcome enum** (resolves CC-5): `COMPLETE | PARTIAL(budget | cancel | human_timeout | revoked_drain) | FAILED_PACK | FAILED_INFRA (includes RESOURCE_EXHAUSTED and FAILED_RESTART) | ABORTED_CLEAN (includes UNCONFIRMED_PAUSE) | KILLED(evidence kind, attestation source)`; pre-run terminals with no hold: `REFUSED_PREFLIGHT`, `EXPIRED_APPROVAL`. User "cancel" yields PARTIAL(cancel) and keeps verified milestones; "abort clean" discards the result.
- **Master timers** (SM s2.13; all proposals): approval card 15 min; AUTHORIZING total 5 min; auth to STARTED 10 min (hub reaper); sidecar lease 10-15 s then kill after 60 s; hub lease 10 min / silence 30 min; gate 60 min, pause review 30 min, total wait cap 3 h (see CC-1); stall cap 20 min; run max 24 h; accept deadline `min(48 h, honor_left - 6 h)`; authorization segment 66 h.

The two diagrams that matter most to a reader: (1) the happy path is `CREATED -> PREFLIGHT -> STAGING -> CARD_PENDING -> APPROVED -> AUTHORIZING -> AUTHORIZED -> STARTING -> RUNNING -> ASSEMBLING -> DRAINING -> CLEANING -> RESULT_READY -> ACCEPT_PENDING -> SETTLED`; (2) every failure branch ends in one of the unified outcomes above, and the money for each is one row in SM s3.4.

---

## 3. Integration review: what is wrong between the two new designs, and what neither covers

I read both design files against each other and against v2, because the owner asked for a careful behavioral check. The ratings are mine, not the audit's. "Required edit" tells the owner of each design file what to change; I did not modify those files (task scope).

### 3.1 Contradictions between WF and SM (11)

| # | Rating | Conflict | Resolution adopted here | Required edit |
|---|---|---|---|---|
| CC-1 | medium | **Human wait ceilings.** WF reference harness uses `waiting_s: 86400` and gates of 24 h (WF s2.11, s3.10 table: approve 24 h, ask 2 h, review 24 h, pause_review 15 min). SM caps total waiting at 3 h, gate at 60 min, pause review at 30 min (SM s1.7, s2.13). | **Platform ceilings win; workflow values are requests.** v1 defaults: gate 60 min (author may declare lower, user may extend once), pause review 30 min, total wait 3 h. Longer waits need an explicit user "away mode" that raises the cap, bounded by the hold inequality in SM s1.7 rule 1. Tell authors at publish if declared values exceed the ceiling. Owner decision D-26. | WF s2.11, s3.10: lower the numbers or mark them "requested, clamped by platform". |
| CC-2 | medium | **Cell lifecycle and who commits.** SM s2.4 says "each step is its own Cell start, never reused" and the STARTED ack needs "driver boots Cell step 1". WF s3.4 allows Cell reuse when the data-capability class is identical and says tier-0 steps need no Cell. SM says the supervisor validates and commits outputs; WF says `flowd` validates and the Supervisor appends and signs. | **WF wins.** "Fresh context per step" holds because `flowd` builds a fresh context; "fresh Cell" holds whenever the data-capability class changes. STARTED ack = first `step_started` committed, and if that step needs a Cell, the Cell booted and the sidecar answered. `flowd` validates; the Supervisor appends, signs and commits. | SM s2.3, s2.4, s8 conflict 12. |
| CC-3 | low | **Letter collision.** WF evidence class `C` = claim (requester/host attested); SM evidence class `C` = certifier-reproduced. WF classes T, E, B, P, I, C, X vs SM classes H, R, O, C, N. They describe two different axes. | Two named axes: evidence **kind** (TAMPER, EGRESS, BOUNDARY, PROGRESS, INFRA, DATA_INDUCED) and **attestation source** (H, R, O, C, N). `C` only means certifier-reproduced. | WF s6.2 table. |
| CC-4 | medium | **D8 means two things.** WF: D8 is off-graph, deterministic, kill-grade (flowd alone sequences steps). SM s1.7 and s5: D8 is a probabilistic detector that raises AWAIT_PAUSE_REVIEW. | Split: **D8a off-graph** (step token used outside its step/attempt, request not matching a legal edge): evidence kind TAMPER, kill. **D8b residual in-step sequence anomalies** (read then encode then output inside one `adapter` or `code` step): BOUNDARY/pause review, never kill alone. | SM s1.7, s5.1; WF s6.2. |
| CC-5 | low | **Outcome enums differ** (WF s3.3: COMPLETE, PARTIAL(reason), FAILED_PACK, FAILED_INFRA, ABORTED_CLEAN, KILLED; SM s1.8: adds PARTIAL_BUDGET, CANCELLED, FAILED_RESTART, EXPIRED_APPROVAL, REFUSED_PREFLIGHT). | Unified enum in section 2. | Both. |
| CC-6 | medium | **When is a milestone captured?** WF s2.10: `milestone_verified` makes the Supervisor queue a capture request (reads as mid-run). SM s3.3: floor is captured at RESULT_READY and outcome fees only at accept or auto-accept (`cap_out:n`). | **v1: no mid-run capture.** `milestone_verified` is journaled and counted in `result_ready`; money moves only at RESULT_READY (floor) and ACCEPT_PENDING resolution (outcome fees). Reasons: milestone checks are requester-attested (Pull has no fair exchange), the honor window and accept window are already tight, and mid-run capture adds a race with kill. Multi-segment runs (more than one authorization) are not supported in v1 (run max 24 h). | WF s2.10 wording; SM unchanged. |
| CC-7 | medium | **Dispute clocks exceed the honor window for long runs.** SM s5.4 freezes payout to `min(72 h, honor_left - 6 h)` and s5.5 gives the author a 48 h rebuttal window plus a Certifier replay. After a 24 h run, `honor_left` at RESULT_READY is about 48 h, so the freeze deadline is about 42 h, shorter than the rebuttal window. | Rebuttal window = `min(48 h, freeze_deadline - replay_time)`. If that is under 12 h, the hub captures the remaining cap into hub balance before `honor_limit - 6 h` and adjudicates against the balance (refundable by hub, but this is custodial exposure, PAY-F9; counsel gate). Owner decision D-27. | SM s5.4, s5.5. |
| CC-8 | medium | **Digest vs commercial fields.** WF s2.1 and SM s6.4: the digest is SHA-256 over the **raw bytes of every file** and excludes certification, price and listing metadata. v2 s5.2 puts `commercial` and `tested_on` inside `pack.yaml`, which is inside the tree. Raw bytes of a file cannot exclude fields of that file. | `pack.yaml` keeps only digest-covered content (id, version, parent, speciality, runner, model requirement, modes, memory, evals, provenance, SPDX licence, workflow reference). `commercial.*`, `tested_on` and every listing field move **out of the tree** into signed side documents (`listing.json` v-numbered, attestation). SPDX licence stays inside the digest; licence **tier** and `ip_tier` live in the listing. A publish bundle = pack tree + side documents. | v2 s5.1-s5.2 (done in section 4 below); SM s6.4 add one sentence. |
| CC-9 | low | **"Tier" names five things** (pack tier 0/1, driver tier, trust tier, IP tier, licence tier; audit 11). SM resolves only trust tier (endorsed-foreign = 1). | Glossary rename: **pack level** L0 (no pack code) / L1 (code-bearing); **driver tier** T1/T2/...; **trust tier** 0-3; **IP class** open / licensed-watermarked / split-shell-brain / hosted-only; **licence class**; **assurance class** S/E/O. "Tier" alone is banned in specs. | v2 s2, s5.2; WF s1.3 text "tier 0 / tier 1". |
| CC-10 | low | **Tavily vs "no network tools in private-data runs"** (decisions.md and HACKATHONS.md add Tavily for the Nebius award; v2 never mentions it; v2 s3.1 forbids network tools in private runs). | Tavily is available **only** as the Search/Fetch Broker in a PUBLIC-scope step with an empty lens (WF s2.8); the demo shows it in a public step feeding a private step. No Tavily in any scope that holds lens data. | v2 s3.1, s8 (done below). |
| CC-11 | low | **Anchoring cadence.** SM anchors a checkpoint head to the hub after every node; WF says node-level timing is never exposed to authors and step counts are bucketed. Per-node anchors tell the (honest-but-curious) hub the workflow's shape and timing. | Hub-only exposure accepted (the hub already knows the digest). Anchor per milestone and at most every 5 min (proposal), not per node; never forwarded to authors. | SM s2.3 row "RUNNING, step finishes". |

### 3.2 New gaps neither design nor the audit covers (6)

| # | Rating | Gap | Why it matters | Fix adopted (proposal) |
|---|---|---|---|---|
| N-1 | **high** | **Silence after STARTED voids the hold, so the requester finishes the run, copies the result and never sends `result_ready`.** SM s2.12 step 4: the hub reaper "voids any run with no heartbeat past `run_deadline + grace`", and the floor is captured only on `result_ready`. In Pull the result already lies on the requester's disk. | Free work with zero floor, and the author is unpaid. This is the cheapest abuse in the whole payment flow and the floor fee, the main defense for PAY-F1, never fires. | The hub distinguishes **hub-observed progress** from silence: if the run reached STARTED and the hub holds at least one anchored checkpoint (attestation source H), then at `run_deadline + grace` it **captures the floor** (billable run) and routes the outcome fee to the ACCEPT_PENDING default (auto-accept rule), instead of voiding. Void only when no checkpoint was ever anchored. Add to SM s2.12 and s3.4 as outcome "requester silence". |
| N-2 | medium | **`human` `ask` in Hosted leaks requester text to the host.** `flowd` runs on the host in Hosted (WF s3.13); an `ask` answer typed by the requester flows back into the host's context, but the Hosted approval object binds only the packet hash (SM s4.3). | Data leaves the machine beyond the approved packet. | In Hosted v1, `ask` nodes are rejected at quote time. `approve` and `review` nodes return only a typed enum decision (not text). Any later `ask` support must put the answer into a re-previewed supplementary packet with a new approval object. |
| N-3 | medium | **The Certifier cannot run workflows with `human` nodes.** Neither file says how a suite answers `ask`, `approve` or `review`; wait time is also not excluded from cost and time statistics. | pass^k and cost percentiles are undefined for any pack with a human gate; authors would avoid gates or the Certifier would hang. | Suites carry a scripted answerer (typed answers per `question_id`, plus approve/review decisions) as part of the task fixture; human wait time is excluded from time and cost percentiles but reported as `human_gate_count`; an unanswered gate counts as `human_timeout`. |
| N-4 | medium | **Canary seed arrives after staging.** SM s2.3 stages the closed set before the card, but the hub issues the canary seed at AUTHORIZE (SM s5.1). The overlap check "no canary value appears in the staged slice" cannot run at staging time. | The planting-prevention step has no point in the sequence where it can run. | Add a guard on `AUTHORIZED -> STARTING`: Supervisor checks the hub's canary values (normalized and encoded) against the sealed staged slice and the artifact files. On overlap: void the authorization, re-request AUTHORIZE with a fresh seed under the same `run_id` (no new card, since nothing the user approved changed); after 2 overlaps, FAILED_INFRA. |
| N-5 | low | **Unbounded re-prompt loop.** SM s2.3: at AUTHORIZING a changed snapshot hash sends the run back to CARD_PENDING. A busy vault (the local agent writes episodic records) can change the lens set every time. | The user is re-prompted forever, or the rule is disabled in practice. | Allow at most 2 re-prompts per `run_id`, then refuse with "your vault is changing too fast for this lens; pause the agent or narrow the lens" (REFUSED_PREFLIGHT). A change that adds no records above the sensitivity shown and grows the set by less than X% (proposal 5%) re-uses the approval (SM s2.3 delta trigger). |
| N-6 | low | **Shred during ACCEPT_PENDING.** The result in plane R is encrypted under keys derived from the source records' key ids (SM s2.1, WF s3.2); if the user shreds a source record before the accept window ends, the result becomes undecryptable. | "Accept" on an unreadable result; ambiguity about money. | Result is marked `invalidated_by_shred`; the already-stored platform-check verdict (hash only) still drives auto-accept and floor capture (the requester caused it); the Reader session says why the result is unavailable; no author penalty. |

### 3.3 Findings still without an owning design document (7)

| Finding | What is missing | Needed document |
|---|---|---|
| CERT-F2, ID-F1 (key part) | Hub trust-domain split: Certifier workers hold no secrets, signer service in a separate account with KMS/HSM, per-role short-lived keys, offline root pinned in clients. SM s6.3 states the rules; infrastructure design absent. | Hub infrastructure and key-management design |
| CERT-F4 | Fingerprint-resistant Certifier and sleeper/time-bomb fixtures (partly WF s6.3 #6) | Certifier specification |
| CERT-F11 | Platform as suite author, grader, ranker and merchant; "platform-seeded" labelling; commit-reveal of retired suites | Ranking and governance note |
| CERT-F12 | "evaluated" not "safe" wording is adopted; counsel review, takedown, evidence retention, attribution before appeal | Legal note (no counsel review done; jurisdictions UNVERIFIED) |
| ID-F10 | Hub metadata privacy beyond whole-list fetch and batching | Privacy note |
| PAY-F10 | Anti-wash weighting details (payer age, spend, clusters) | Ranking and governance note |
| HUM-F8 | Non-WSL fallback driver (remote VM, Hyper-V/Windows Sandbox on Pro) | Driver ADR (phase 3) |

---

## 4. Every change to architecture-v2.md (diff table)

Columns: **Scope** H = needed for the hackathon build/demo path, P = production item, documented gap. Ids are audit finding ids; "audit 11" means the document-consistency audit (flow 11). "WF"/"SM" point to where the new text lives.

### 4.1 Front matter, sections 1 and 2

| # | v2 section | Old | New | Finding ids | Scope |
|---|---|---|---|---|---|
| 1 | Product sentence | Owner incentive: "revenue per run" | Owner revenue comes from certified-channel services (certified versions, signed updates, revocation checks, receipts and refund flow, support, optional hosted runs). A per-run price is claimed only for packs whose content is released against the run token (licensed-watermarked or split-shell-brain). The run token is settlement, not metering and not DRM; payment gating in Pull is cooperative | CON-F7, PAY-F12, ID-F8 | H |
| 2 | s1 table, row "Harness" | "Harness = a folder with a prompt and tool list" and a fixed three-phase policy | Harness = signed workflow program run by the trusted engine `flowd` (section 1) | owner round 3, CON-F12, PL-F6 | H |
| 3 | s1 principle 1 | "Nothing is sent to the foreign pack is structural only in Pull" | Add: all Pull verdicts, receipts and acceptance results are requester-attested; Hosted prompts are visible to the hub gateway; "Pull has no fair exchange" is stated | PAY-F1, DEF-F4, CON-F3, HO-F1 | H |
| 4 | s1 principle 2 | Fixed-schema, enum-only channels toward author and hub | Per-run receipts go to the hub only; authors get batched aggregates (k >= 20 distinct requesters, delayed, no per-run rows, no requester id, no duration/token buckets, no detector identity) | DEF-F6, PAY-F11, ID-F10 | H |
| 5 | s2 flaw row 1 (result channel) | Result Guard "inert render" | Add D15 (outbound reference in a result) and a concrete render contract (CSP `default-src 'none'`, URL stripping); patches never applied to the live tree | TASK-F2, TASK-F5 | H |
| 6 | s2 flaw row 3 (WSL2 driver) | Conformance suite; downgrade if it fails | Add a fast conformance subset (<10 s) before every private-data run and resume, and a 3-probe self-test at every Cell start; driver status shown on status bar and card, not on the listing; a downgrade forces re-approval; "bridge doctor" first-run | HUM-F8, CON-F12 | H |
| 7 | s2 flaw row 5 (memory promotion) | "Corroboration from independent source classes" | Independence is computed from disjoint ancestry in the journal DAG; any foreign taint forces Q whatever the actor; payment Accept is never a corroborating class; accepted foreign items are tier 1 "endorsed-foreign" | MEM-F3, MEM-F4, CON-F5, HUM-F1 | H |
| 8 | s2 flaw row 4 (Hosted claims) | Hosted verdicts owner-attested | Add: host key authenticity is hub-trusted in Unsealed; the hub gateway sees prompts; host incidents only void that run and downgrade the (host, pack) pair | HO-F3, HO-F9, HO-F1 | H |
| 9 | s2 flaw row 7 (demo) | 3:00 cut plus fallback clips | Scenes not live are labelled "replayed from certified run"; D5 sensor spec added | CON-F9 | H |

### 4.2 Section 3 (architecture)

| # | v2 section | Old | New | Finding ids | Scope |
|---|---|---|---|---|---|
| 10 | 3.1 diagram, Cell box | "phases planner -> worker -> returner"; "/in = ro staged snapshot" | Steps come from the workflow graph; a Cell exists only for `code`, `adapter` and verifier steps; no `/in` mount; records only through the Broker; tier-1 files only through accounted `materialize` into the step's tmpfs | PR-F6, CON-F2, MEM-F2 | H |
| 11 | 3.1 diagram, requester box | Supervisor, Sidecar; audit log signed in the Sidecar | Add `flowd` (own OS user, no NIC), Run Store R, Supervisor as sole journal writer and signer; the audit/journal signing key moves from Sidecar to Supervisor (separate OS user); chain head anchored to the hub | WF W2/W3, ID-F11, PR-F1, PR-F12 | H |
| 12 | 3.1 diagram, hub box | "Transparency log (Ed25519 + hash chain)", "Escrow" | "Hub-signed append-only Merkle log (RFC 9162 shape) with signed tree heads that clients pin"; the word "transparency" waits for an external witness; "payment hold" (authorize/capture/void) with a ledger state machine; add Model Gateway (Hosted), signer service separate from the Certifier, signed whole-list revocation | PL-F7, CERT-F3, ID-F1, ID-F5, CON-F6, PAY-F9, PAY-F4, HO-F1 | H (hash chain + pinned heads), P (witnesses) |
| 13 | 3.1 key split sentence | Supervisor separate from Sidecar | Also `flowd` separate from Supervisor; the Supervisor keeps the minimal kill path | WF W2 | H |
| 14 | 3.2 B1 | Requester machine fully trusted | Add row B1b: **requester vs author and hub**; the requester is an economic adversary in Pull; its attestations are claims | CON-F3, PAY-F1 | H |
| 15 | 3.2 B2 | "hub never gets vault content" | "Hub never gets vault content beyond the declared packet; the Hosted gateway sees Hosted prompts; the hub learns account, IP, payer, digest, time, bucketed duration and tokens, outcome enums, installed-pack list and relay sizes/timing" | ID-F10, HO-F1 | H |
| 16 | 3.2 B3 | Packet E2E encrypted to host key | Host X25519 key signed by its Ed25519 identity key, TOFU-pinned with fingerprint on the card; signed prekeys (~24 h); requester signs envelope; Unsealed key authenticity is hub-trusted | HO-F3 | H |
| 17 | 3.2 B5 | "ZDR account setting enabled by hub" | Per-mode ownership table: Pull = requester's own account and key (no ZDR claim unless confirmed; UI says "retention: provider default"); Hosted = hub gateway on the hub's account with a per-task bearer; Certifier and GEPA on a separate account | CON-F4, HO-F1, ID-F12 | H |
| 18 | 3.2 B7 | "inert render" (undefined) | Defined: closed output-kind registry, static view, CSP `default-src 'none'`, no remote images/fonts/previews, URLs shown as text unless in task inputs, patches go to a throwaway worktree with hard-flagged paths | TASK-F1, TASK-F2, TASK-F5 | H |
| 19 | 3.2 B9 | Certifier: separate pack and grader sandboxes | B9 plus **B9a hub trust domain**: Certifier workers hold no secrets (no role, no log or PayPal access); signer service accepts only fixed-schema numeric results; per-job short-lived Nebius key | CERT-F2, ID-F1 | P (design item), H (no secrets in worker) |
| 20 | 3.2 new row B10 | none | TCB supply chain: offline TCB signing key, pinned hash per release in the log, opt-in updates, no downgrade, vendored hash-locked crypto/Presidio/Biscuit with SBOM; reproducible builds are a goal, not a claim | ID-F2 | P |
| 21 | 3.2 scope sentence | none | A malicious hub or on-path attacker is out of scope for v1; pointer to PL-F7/ID-F5 fixes | PL-F7, ID-F5 | H (statement) |
| 22 | 3.3 Pull bullet | Author receives nothing; not guaranteed list | Add: every Pull verdict is requester-attested; no fair exchange (the result is on your disk before the payment decision); render- and apply-time fetches of URLs in results are not covered (mitigated by CSP and no auto-fetch); post-run aggregates exist with a bounded information rate (no hard bits-per-run claim); "pin means content fixed, not safe"; you trust the bridge binaries you installed; the pack sees only the lens and the output channel is bounded | PAY-F1, TASK-F2, DEF-F6, DEF-F7, ID-F2 | H |
| 23 | 3.3 Pull headline | "no network interface for the foreign pack" | Qualified: "for a driver tier that passed the conformance subset and the per-Cell self-test for this run" | CON-F12 | H |
| 24 | 3.3 Unsealed Hosted | "Do not use for private data" | Hosted packets contain only user-confirmed `low` items; hub gateway sees prompts; host key is hub-trusted | HO-F10, HO-F1, HO-F3 | H |
| 25 | 3.4 Receipt row | Single supervisor-signed receipt with duration bucket, token bucket, exact cost | Two parts: hub-signed payment receipt (auth id hash, capture ids, amounts, nonce, ledger state) and supervisor-signed run summary labelled `attestor=requester|host`; price tier or bucketed cost, never exact; step counts bucketed; per-run rows hub-only | PAY-F11, DEF-F6, CON-F12 | H |
| 26 | 3.4 Rating row | Integer 1-5 bound to a captured payment | Rating via a hub-issued single-use token bound to the capture id; counted only after holdback; reversed on refund or chargeback | PAY-F11, CERT-F7 | H |
| 27 | 3.4 Update check row | "Pack id and version query only" | Whole-list fetch of the signed index and revocation list; no per-pack query; batched and jittered | PL-F1, ID-F10 | H |
| 28 | 3.4 Hub metadata row | "Counts and digests" | Explicit list of what the hub learns (see row 15) | ID-F10 | H |
| 29 | 3.5 reuse | no rule engine named | Add CEL (cel-go/cel-rust/cel-python, choice UNVERIFIED) for expressions; no embedded LangGraph or Temporal in the TCB | WF W2 | H |

### 4.3 Section 4 (memory)

| # | v2 section | Old | New | Finding ids | Scope |
|---|---|---|---|---|---|
| 30 | 4.1 Q row | "excluded from retrieval or capped to a few slots for the local agent" | The write-capable local agent and the Scribe **never read Q**; a Reader session with no write tools does; fixed TTL (14 d), caps per pack and globally, rejection plus strike at cap, no bulk approve for high-risk types | MEM-F7 | H |
| 31 | 4.1 planes | U, Q, P, H, T | Add **R Run State plane** (Supervisor-owned, device-local, never replicated, never pack-writable, encrypted under shreddable keys, TTL) | TASK-F6, PR-F5 | H |
| 32 | 4.1 P row | "keyed by pack digest" | P is a vault namespace (same schema, journal, encryption, shred, migration), keyed `(author, pack lineage, digest)`, strikes inherited via `parent`, references not copies, lens widening suggest-only | MEM-F10 | H |
| 33 | 4.1 secret type | "Human only; never served" | "secret" is defined by the capture-time scanner and handle, not the extractor's label; secret records come only from explicit user action | MEM-F8 | H |
| 34 | 4.2 schema | `content_hash`, `invalid_at` for everything, `trust_tier` 0-3 | `content_commit = HMAC(record_key, content)`; `superseded_by` (system time) separate from `invalid_at` (valid time); immutable `origin {class, pack_digest, run_id, proposal_id, accepted_by, accepted_at}` and `derived_from []`; tier 1 = endorsed-foreign, tier 3 = typed or edited by the user; metadata encrypted under the shreddable key | MEM-F4, MEM-F5, MEM-F9, MEM-F11, HUM-F1 | H (origin, tiers), P (full encryption hierarchy) |
| 35 | 4.2 journal line | Merkle checkpoint every N events and before every task | Per-run-id reference points, **audit and diff anchors only, never restore targets**; payload encrypted per event; minimal hash-chain head in phase 5, Merkle hardening later | MEM-F1, MEM-F8, CON-F8, CON-F11 | H |
| 36 | 4.3 write path | capture, journal, extractor, proposal, gate | Add **step 0 scanner** before journal append (secrets become handles), taint = union of source classes in the context window set at capture, extraction queue with cursor, backoff, dead-letter, "extraction stalled" status; `proposal_id = hash(source event ids + extractor version)`; high-sensitivity text never sent to a remote extractor | MEM-F3, MEM-F7, MEM-F8, MEM-F6 | H |
| 37 | 4.3 promotion gate | "2+ independent source classes" | Disjoint ancestry in the journal DAG; foreign taint forces Q; only an explicit user "remember" or user-authored text counts as trusted-local; a session that ingested foreign text loses write rights or writes through the proposal channel; episodic outcome records hold only enum and id fields | MEM-F3, CON-F5, HUM-F1 | H |
| 38 | 4.3 Reader/Scribe | Scribe sees schema-validated proposals | Proposal schema is a hub-defined meta-schema (enums, numbers, hashes, references); free strings only as a user-visible diff, never to the Scribe, never auto-promoted | CON-F5, MEM-F7 | H |
| 39 | 4.4 read path | 9 steps, canaries "outside the granted lens" injected at step 8 | Add step 2b: drop records whose `origin.pack_digest` is on the local denylist or revocation list; step 5 adds a small slot cap for tier 1; canaries served only on off-lens or enumerative queries, never in in-lens results; reads run over the **closed staged set** (record id, version, content hash) not the live vault | PR-F6, CON-F1, DEF-F1, MEM-F9, HUM-F2 | H |
| 40 | 4.4 lens preview | "byte-exact preview" | Exact for the closed staged set and approved artifact files; the semantic filter is applied once at staging so the card lists the resulting set (counts, sensitivity histogram, sampled excerpts); no "byte-exact" for any live query path | MEM-F2, HUM-F2, TASK-F11 | H |
| 41 | 4.4 "no dump" | No dump tool in the Broker | Also true at staging: there is no whole-slice `/in`; tier-0 packs get no mount | CON-F2 | H |
| 42 | 4.5 "After an incident" | "Roll back U to the pre-task Merkle checkpoint" | **Run-scoped compensating revert**: delete the run's Q items; compute the causal set from `origin`/`derived_from`; set `invalid_at` or restore the predecessor by compensating events, only if the current version equals the tainted one (CAS); conflicts go to the user; promoted or mixed-ancestry records move to REVIEW; user-authored records without run ancestry are untouched | MEM-F1, MEM-F9, DEF-F9, HUM-F4, CON-F11, PR-F5, PL-F10 | H |
| 43 | 4.5 "True deletion" | "Drop the per-record key; tombstone hash" | Shred contract: per-record DEK under a rotating KEK in the OS keystore, keyed commitment so hashes do not confirm guesses, shred is a signed monotone tombstone, "complete only when every device acknowledged or was removed", documented residue (text already sent to Nebius, offline devices) | MEM-F5, ID-F11 | H (commit, tombstone), P (full hierarchy) |
| 44 | 4.5 "Concurrent edit" | CAS | Add `base_versions` on proposals; stale proposals flagged when a base record was invalidated or shredded | PR-F5 | H |
| 45 | 4.6 multi-device | "Open: CRDT vs plain journal replication" | Specified, built later: per-device signed sub-chains, version vectors with CAS as the local fast path, idempotent proposals, tombstones dominate, hybrid logical clocks, device removal rotates keys, no hub escrow by default | MEM-F6, ID-F11 | P (built after phase 1) |
| 46 | 4.6 demo benefit | "pack B already knows what pack A produced, accepted into U" | Two named mechanisms only: `artifact_from_task` typed handoff, or an explicit cross-pack lens tag on a tier-1 record shown as "derived from pack X"; no ambient retrieval; accepted pack-derived items excluded from Hosted packets | MEM-F4, TASK-F12 | H |
| 47 | 4.7 | Pull packs get no writable persistent store | Unchanged, plus the R plane is Supervisor-owned; step outputs are validated then committed by the engine | TASK-F6 | H |
| 48 | 4.8 table | 7 rows | Add rows: laundering through accept; secrets in journal; crypto-shred residue; Q flood; R-plane contents | HUM-F1, MEM-F8, MEM-F5, MEM-F7 | H |
| 49 | 4.9 migration | "invalidates the old one" | Use `superseded_by`; read-time upcasters with lazy rewrite; devices refuse to write newer schemas; downcast must preserve security labels or the pack is refused; migration is a checkpointed, resumable job with dry-run | MEM-F11 | P |
| 50 | 4.10 staged cut | Merkle checkpoints with phase 16 | Phase 5 ships a minimal hash-chain head plus an anchor before each task; Merkle hardening stays in the late phase | CON-F8, CON-F11 | H |

### 4.4 Section 5 (pack and harness)

| # | v2 section | Old | New | Finding ids | Scope |
|---|---|---|---|---|---|
| 51 | 5 intro definition | Harness = prompts, skills, three-phase policy, tool list | Section 1.1 of this file | owner round 3 | H |
| 52 | 5.1 layout | `pack.yaml`, AGENTS.md, skills, evals, code | Add `workflow.yaml`, `schemas/`, `prompts/`, `rubrics/`; `listing.json` and attestations are **outside the digest tree** | CC-8, PL-F5 | H |
| 53 | 5.1 digest | "normalized line endings, JSON-canonicalized manifest" | SHA-256 over **raw bytes** of every pack file; validate rejects non-canonical input (LF only, no CR in scripts); strict YAML subset or JSON; shared parser with conformance corpus; D9 hashes raw bytes against the same definition; a normative "digest-covered fields" list in the phase 0 spec | PL-F12, DEF-F11, PL-F5 | H |
| 54 | 5.2 `phases:` block | plan / work / return with per-phase memory and tools | `workflow:` graph (WF s2); `plan-work-return` is a built-in template; per-step grants; budgets and policies | PL-F6, CON-F12, PR-F6 | H |
| 55 | 5.2 `model.tested_on`, `certified_digest` | Filled by Certifier inside the manifest | **Deleted.** Certification lives in a separate signed attestation; `card.json` is generated from attestations | CON-F6, PL-F5, CERT-F8 | H |
| 56 | 5.2 `commercial` | Price, licence, ip_tier, refund inside the manifest | Moves to a versioned **Listing** document signed by the owner and countersigned by the hub; a price change is a listing update, not a new digest; re-approval only if the new price exceeds the card's cap; `refund.acceptance_checks` replaced by the platform check library | PL-F5, PR-F4, TASK-F1 | H |
| 57 | 5.2 `runner.pinned`, `provenance.upstream` | Pins declared by the author | The hub mirrors the pinned upstream tree at publish and records a SHA-256 tree hash; the **lock block** (runner image digest, engine version, model id plus provider revision, upstream tree hash) goes into the attestation; unmirrorable pins rejected; "pin means content fixed, not safe" | PL-F9, ID-F2 | H |
| 58 | 5.2 `modes` | Certified once per (version, model) | Certified per **(digest, model, mode)**; Hosted memory is a read-only packet snapshot behind the same `memory.search`; Pull LCB is shown on a Hosted listing only when a Hosted-mode certified run exists | HO-F12, CON-F12 | H |
| 59 | 5.2 core rule (semver) | "Any permission widening is MAJOR" (convention) | Hub computes a **capability-set hash** and diff versus the previous version of the same id and **rejects a non-MAJOR bump that widens**; the hub renders the card diff, not the author's changelog; prompt-only change shows a one-line "behavior changed, score x to y" | PL-F4, HUM-F10 | H |
| 60 | 5.2 result contract | Pack-declared `result_schema` | Not a grant: closed output-kind registry; pack schema may only narrow it (subschema check at publish and certify) | TASK-F1 | H |
| 61 | 5.3 step 2 validate | JSON Schema, SPDX, SBOM, secret scan | Add `bridge flow analyze` (18 checks; the requester re-runs it) | WF s4 | H |
| 62 | 5.3 step 4 certify | Private rotating suites, honeypots, cheater pack | Add: workers hold no secrets; same supervisor/sidecar/token/receipt path as production, randomized clocks, production-shaped canaries (fingerprint resistance); sleeper and time-bomb variants; coarse outcomes only (pass/fail plus fixed reason class), rate limit, cooldown, REJECTED state with one appeal; certification fee and quotas tied to a verified identity; scripted answerer for human nodes | CERT-F2, CERT-F4, CERT-F5, PL-F12, N-3 | H (no-secret workers, coarse outcomes), P (fees) |
| 63 | 5.3 step 5 sign | Attestation bound to (digest, model, suite version) | Attestation also binds capability-set hash, analyzer report hash, model revision, engine and sidecar version and conformance hash, adapter image digests, driver tier, Result Guard version, Certifier build, score LCB, per-task outcome hash vector, scoring version, run-log digest, `valid_until` (~90 d); states CURRENT, STALE, ORPHANED; stack change marks STALE; the log is "hub-signed" | PL-F5, PL-F9, CERT-F3, CERT-F8 | H |
| 64 | 5.3 step 6 publish | Immutable digest, card.json, account-age gate | Write-once CAS on `(publisher_id, id, version)`; immutable publisher id; tombstoned namespaces; confusable-name checks; closed speciality taxonomy claimable only with a passing certification; typed `card.json` (free text separate and inert); economic or identity-tier gate instead of account age; `parent` must be same-publisher or a signed fork record else "unverified lineage"; key lifecycle (rotation with delay, distrust-from-T, cooling period for a new key, payout freeze on destination change) | PL-F11, PL-F3, PL-F4, ID-F7, ID-F9, CERT-F9, CERT-F10 | H (CAS, distrust-from-T, cooling flag), P (rest) |
| 65 | 5.3 step 7 run | Approval per (digest, mode, lens, budget); diff re-approval | Approval binds `approval_hash` over digest, capability-set hash, mode, snapshot manifest hash, lens, TaskSpec hash, quote cap and id, model id, engine version, driver tier and conformance run id, `run_id`, expiry; never follows "latest"; scheduled workflows pin a digest; expiry only for high-sensitivity runs; computed re-approval triggers | PL-F4, HUM-F2, TASK-F11, HUM-F10 | H |
| 66 | 5.3 step 8 feedback | Receipt-bound ratings | Receipts to the hub only; author aggregates batched (k >= 20, delayed); rejected and voided runs recorded as lower-weight outcome records | DEF-F6, CERT-F7 | H |
| 67 | 5.3 step 10 revoke | "Supervisors check before every start and on each broker call" | Signed whole-file versioned list with `seq`, `issued_at`, `valid_until`; checking by the Supervisor outside the Cell against the **cached bounded-freshness list plus the local denylist**; stale start for medium or high fails closed, low warns; expiry mid-run pauses; version states and reason-to-action table (SM s6.1-s6.3); revocation terminal for a digest; reinstatement = new digest | PL-F1, PL-F8, ID-F3, ID-F1 | H |
| 68 | 5.4 "anyone can recompute" | Ranking recomputable by anyone from the signed log | "Ranking is a deterministic function of hub-attested numbers; anyone holding the log can recompute the aggregation; per-run suite scores and paid columns are hub-attested; distinctness of payers is hub-attested"; a published rotated-out slice for spot-check replay | CERT-F3, CON-F6, ID-F10 | H (wording) |
| 69 | 5.4 scoring | LCB of private-suite results | Scoring protocol v1: one counted certification per (digest, model, suite epoch); cluster bootstrap over tasks; baseline-normalised delta; anchor subset across epochs; judge model differs from the agent model; programmatic graders first; `scoring_version` frozen in the attestation | CERT-F6 | H |
| 70 | 5.4 paid completions | Count after acceptance | Count only after holdback, reverse on refund or chargeback, weight by payer age, spend and diversity, zero-weight payer-author links, per-payer caps; paid signals can only demote or tie-break relative to the Certifier LCB; free packs on a separate Certifier-only board; platform-seeded packs labelled; badge says "evaluated" with scope text, never "safe" | CERT-F7, CERT-F11, CERT-F12, PAY-F10 | H (wording), P (anti-wash detail) |
| 71 | 5.5 loop | Optimizer edits H-plane | Typed diffs against `workflow.yaml`; topology edits need human review; budgets, `max_iterations`, permissions never widen automatically; optimizer uses the public-dev suite only; private suite only at promotion with a per-lineage probe budget | CERT-F5, WF s6.4 | H |
| 72 | 5.6 IP honesty | open packs listed with per-run price | Lint rule: `open` plus per-run price is relabelled donation or convenience pricing; per-run charging requires licensed-watermarked or split-shell-brain | CON-F7 | H |

### 4.5 Sections 6 and 7

| # | v2 section | Old | New | Finding ids | Scope |
|---|---|---|---|---|---|
| 73 | 6.1 mode selector | Hosted if "low-sensitivity or tokenized" items | Default deny: only user-confirmed `low` items; never secret, high, untagged, Q or pack-derived; deterministic scanner (secret regexes, Presidio, entropy, vault identifier list) over final packet bytes; fresh random tokens per run; detokenized output marked sensitive; no digest-batched approvals for Hosted | HO-F10, CON-F10 | H |
| 74 | 6.1 agent authority | Local agent browses, picks mode, holds hire/pay tools | The agent is a proposer; sees only enums and hub-computed fields; free text only in an "author says, unverified" pane; lens is a policy object (user default and maximum); a session that has read foreign content cannot call hire, accept, reject, capture, void or reauthorize; Accept is a human click or a deterministic rule | HUM-F7, CERT-F10, PR-F11, TASK-F12, CON-F10 | H |
| 75 | 6.2 step 1 | verify signature, log inclusion, revocation, license, tested_on, driver tier | Verify a CURRENT attestation for (digest, requester's model); "uncertified on your model" shows no LCB and needs an override banner excluded from verified-paid ranking | CERT-F8, CON-F12 | H |
| 76 | 6.2 step 2 | Approval card with byte-exact preview | Card shows the four-line "where your data goes" strip, lens by sensitivity and count, worst-case and p50/p95 cost, gate count and expected cards, assurance class, attestation status; it is computed from the workflow, signed over `approval_hash`; staging precedes the card; phone protocol: nonce, expiry 2-5 min, first valid decision wins, Supervisor sole state authority, content-free push (nonce and expiry and first-wins are H; WebAuthn and recovery are P) | HUM-F2, HUM-F3, HUM-F9 | H / P |
| 77 | 6.2 step 3 | One-time run token + AUTHORIZE as "the metering anchor" | **Order: preflight, stage, card, AUTHORIZE last, start.** Requester mints `run_id`; idempotent hub calls; token ISSUED/BOUND/STARTED/SETTLED; hub lease with epoch; token re-bindable until STARTED; reaper voids at 10 min; token described as settlement not metering | PR-F3, PL-F6, ID-F8, PAY-F12 | H |
| 78 | 6.2 step 4 | vaultd stages `/in` with canaries outside the lens | Closed staged set sealed under a per-run key held by the Supervisor outside the VM; manifest of (record id, version, content hash) plus vault seq; stage hash recomputed at launch; canary overlap check on AUTHORIZED to STARTING (N-4) | PR-F5, HUM-F2, CON-F1, N-4 | H |
| 79 | 6.2 step 5 | Driver starts the Cell | Preflight (driver subset, 3-probe self-test, disk and RAM admission under the 6 GB WSL cap, concurrency, model pin, revocation freshness, sleep inhibitor); a Cell exists only when a step needs one | PR-F2, PR-F12, CON-F12 | H |
| 80 | 6.2 step 6 | planner, worker, returner; model calls and `memory.search` only via sidecar | Workflow execution by `flowd`; typed labelled hand-offs; per-step grants; budgets; Progress Guard; STALLED on model API failure; model proxy owns retries and returns only typed errors | PR-F6, PR-F8, PR-F9 | H |
| 81 | 6.2 step 7 | Result Guard, acceptance checks, Accept | Result Guard per output kind; platform check library in a throwaway no-network Cell; ACCEPT_PENDING with hub deadline `min(48 h, honor_left - 6 h)`; silence plus platform checks passed = auto-accept; Reject with fixed reason codes; Accept never means "applied" | PR-F4, PAY-F2, HUM-F6, TASK-F1, TASK-F5 | H |
| 82 | 6.2 step 8 | Proposals go to Q | Unchanged, but offered only after RESULT_READY, never auto-promoted, schema from the meta-schema, idempotent by content hash | MEM-F7, CON-F5 | H |
| 83 | 6.2 step 9 | "Partial/final capture, payout after holdback, receipt; Cell destroyed" | **Order reversed:** drain detectors, destroy Cell, wipe stage and keys (CLEANED), then capture; floor capture at RESULT_READY, outcome fees at accept or auto-accept, void remainder; payout by payer id after holdback and reserve; receipt "paid" only on payout SUCCESS | PR-F1, PAY-F5, DEF-F8 | H |
| 84 | 6.2 payment note | "payout after holdback against the 180-day dispute window" | Rolling reserve (proposal: 14 d on ~50% for new authors, remainder to day 180); the demo shows "demo holdback 0 s, production N days + reserve"; sandbox only, "test money" badge; "payment hold" replaces "escrow"; counsel gate before any real money | PAY-F6, PAY-F9 | H (label), P (money) |
| 85 | 6.2 failure branch | none | Boot reconciler per WAL state; resume checklist; INFRA_FAULT distinct from tamper; N-1 silence rule | PR-F1, PR-F2, N-1 | H |
| 86 | 6.3 steps 3-7 | Host quote with cap; per-task Nebius key to host; host-metered; capture split | Hub co-signed quote object; single-use signed Hosted approval object; sender-authenticated envelope; hold checked before decrypt; gateway bearer, **no Nebius credential on the host**; hub-observed heartbeats and start/finish; HOST_LOST path; failover off; fault-split table; `human ask` disallowed (N-2); host-signed incidents void that run only | HO-F1..F7, HO-F9, N-2 | H |
| 87 | 6.3 remaining gap | Hub spot checks with canary tasks | Probes use real payment instruments and history, same compiler and relay path, randomized size and timing; known-answer sub-tasks and honeytokens folded into real packets; **no confidentiality assurance from probes**, stated | HO-F8 | P |
| 88 | 6.3 Sealed | Nitro sketch | Enclave counters and caps live in the hub gateway; hub tracks used nonces; requester-supplied attestation nonce; Sealed is roadmap, no verifiable-build claim until reproducible builds exist | HO-F11 | P |
| 89 | 7.1 D1/D2 canaries | Canary read = strike; canary in outbound artifact = KILL; canaries "outside the lens" and injected | Three classes: outside-lens decoys (never in in-lens results), edge decoys (strike only), broker bait tools (not in the model-visible tool list). **D2-soft**: verbatim canary in a free-text result field = Result Guard reject, redact, strike, pause. **D2-hard**: transformed or encoded canary, canary in a non-free-text field, tool arg or proxy request to an external sink, or alongside D5/D6/D7 = kill. Hub-issued per-run seed committed in the run token; denied reads never return a canary | DEF-F1, CON-F1, PR-F10, N-4 | H |
| 90 | 7.1 D5 | Egress attempt = KILL | Needs a named sensor: loopback decoy resolver and listener, or a logging-only seccomp-notify/LD_PRELOAD shim; conformance fixture that a DNS exfil attempt yields a signed D5 event on every driver tier | CON-F9 | H |
| 91 | 7.1 D6 | Overlap with lens; kill on confirmation, timeout defaults to kill for high sensitivity | Sink taxonomy (expected-overlap sinks: result free text under a `quote_budget`, model path; strict sinks: tool args, queries, URLs, proposals, non-free-text fields); metric = longest verbatim overlap and fraction; "return step overlap is high-confidence" **removed**, replaced by a label-subset check; **log-only until its false-positive rate is measured**; timeout never kills (abort-clean) | DEF-F2, DEF-F3, TASK-F4, HUM-F5, PR-F7 | H |
| 92 | 7.1 D8 | Phase/tool-sequence violation, pause | Split D8a off-graph (TAMPER kill) and D8b in-step sequence anomaly (pause review) | CC-4 | H |
| 93 | 7.1 D9, D10, D11, D12 | Kill on drift, kernel rules, persistence/anomaly, tamper | D9 over raw bytes; D10 scoped after Cell init; D11 baseline-aware per (digest, model) and restricted to pack-originated deviations; D12 only on positive evidence (bad signature, unexpected peer, hash mismatch, unauthorized write); missing heartbeat is INFRA_FAULT; retries excluded from D4 | DEF-F11, PR-F2, PR-F8, DEF-F12 | H |
| 94 | 7.1 D13, D14 | Advisory | D13 guard model runs locally or never sees private text in lens-holding steps; D14 never affects ranking | DEF-F12, DEF-F11 | H |
| 95 | 7.1 new D15 | none | Outbound reference in a result (URL not in task inputs or allowlist): strike, shown on the Accept card, never auto-kill | TASK-F2 | H |
| 96 | 7.1 strike budget | "Honeypot decoy tools count as strikes" | Bait tools are not model-visible; honest-pack CI tests measure the D2 false-positive rate | DEF-F1 | H |
| 97 | 7.2 ladder | 9 rungs, "CRITICAL executes 4 through 9 immediately", rung 7 rolls back U, money: VOID plus freeze | Durable incident machine: fsynced intent, **freeze, snapshot, kill**, idempotent rungs keyed (run, rung) with a boot reconciler; evidence kind plus attestation source decide effects (SM s5.3); rung 7 becomes the run-scoped revert; money for a requester-attested claim is **DISPUTE_HOLD** with a deadline, never final VOID of delivered work; slash and hub revocation need class C or N; pre-capture barrier; a late detector after capture routes to dispute | DEF-F8, PAY-F1, PL-F2, DEF-F4, CERT-F1, ID-F4, CON-F3, PR-F10, TASK-F10 | H |
| 98 | 7.2 pause | "freeze, keep state" with kill on timeout | Three outcomes: resume, abort-clean, kill-incident; timeout or unreachable requester = abort-clean (discard result, no quarantine, denylist, revocation, slash or reputation effect; rate-limited per requester) | DEF-F3, HUM-F5, PR-F7 | H |
| 99 | 7.3 anti-framing | Canary alone never affects author; "log-verifiable" | Add attribution step (DATA_INDUCED when trigger text traces to a foreign lens or Q record), Certifier reproduction on a clean synthetic lens before any author-affecting action, injected-lens test and "injection-susceptible" label, per-requester claim rate limit, accuracy score and deposit; "log-verifiable" reworded to "the log proves chain integrity, not the truth of events" | DEF-F10, DEF-F4, ID-F4 | H |
| 100 | 7.4 | Hosted verdicts owner-attested | Plus: Pull verdicts requester-attested; "host-claimed" tag in every UI | HO-F9, CON-F3 | H |
| 101 | 7.6 regression | MINJA/MEXTRA suite, canary evasion | Add: poisoned web page to agent-written fact lands in Q; accept poisoned item then revoke; user write during run then CRITICAL leaves it intact; sleeper with 10 accepted runs; `cat /in` in a non-data step fails; planted-secret test (journal, extractor, audit, quarantine); malicious render/apply fixture; Accept-injection fixture; listing with injection text in every free-text field; model 429/5xx/model-gone chaos; sleep/wake gap; gate bypass; replay equivalence | MEM-F1, MEM-F3, MEM-F8, MEM-F9, PR-F6, TASK-F2, TASK-F12, CERT-F10, PR-F8, PR-F2 | H |

### 4.6 Sections 8 to 12

| # | v2 section | Old | New | Finding ids | Scope |
|---|---|---|---|---|---|
| 102 | s8 reuse list | no workflow engine, no Tavily | Add CEL library (UNVERIFIED choice); explicit "do not embed LangGraph or Temporal in the TCB"; Tavily only as the Search/Fetch Broker in PUBLIC-scope steps | CC-10, TASK-F8 | H |
| 103 | s9 demo, hook line | Guarantee line "no network interface for the foreign pack" | Hook line carries the qualifier and the four-line data-flow strip; no unqualified "nothing leaves" | HUM-F9, CON-F12 | H |
| 104 | s9 0:45-1:15 | Accept one proposed memory item into U; next hire already uses that context | "Endorse as pack-claimed" (tier 1); second hire demonstrated from a recorded artifact or a pre-baked run; payout shown with a "demo holdback 0 s" label | HUM-F1, CON-F9, PAY-F6 | H |
| 105 | s9 1:15-2:00 attack theater | Malicious pack tries canaries and DNS exfil; KILL, rollback, VOID, freeze | Uses reachable decoys and a real direct-read path so D1/D2 fire; shows DISPUTE_HOLD and run-scoped revert instead of VOID and U rollback; the scene is labelled "replayed from certified run" if not live | CON-F1, CON-F9, DEF-F1, PAY-F1 | H |
| 106 | s9 2:00-2:35 lifecycle | GEPA v1.0 to v1.1 live in 35 s | Replayed from a certified run; shows score delta, typed diff and permission delta for owner approval | CON-F9, CERT-F5 | H |
| 107 | s9 close table | Sealed row | Sealed shown as roadmap or removed from the 3:00 cut | CON-F9 | H |
| 108 | s9 judge access | none | A judge-runnable path (docker compose or hosted sandbox demo) and a Linux/EC2 fallback driver host; Nebius working-demo-URL requirement is from a secondary source (UNVERIFIED) | CON-F9 | H |
| 109 | s10 phases | 18 phases, wrong dependencies, no engine | Replaced by section 5 of this file | CON-F8, WF s3.17 | H |
| 110 | s11 owner decisions | 15 items | Replaced by section 7 | | |
| 111 | s12 table "GO" and "satisfied" | Prize fit asserted | All hackathon-fit statements read UNVERIFIED until the Devpost and Nebius rules are read; Nebius "must run on Nebius" versus AWS-hosted hub unresolved | CON-F9 | H |

### 4.7 Contradictions found by audit 11, with the correction applied

Sentence audit (audit 11 s3):

| v2 sentence | Contradiction | Corrected statement or mechanism |
|---|---|---|
| Pull: "the pack has no network interface" | True only if the driver passed on this machine, checked per run (not designed); WSL2 pass UNVERIFIED | Qualified in the guarantee text; per-run preflight subset and 3-probe self-test at every Cell start; refuse private-data Pull on failure (rows 6, 23, 79) |
| "Its only exit is a requester-owned sidecar" vs B5 "ZDR enabled by hub" | Pull key and account belong to the requester; the hub cannot configure ZDR there | Per-mode ownership table; no ZDR claim for Pull unless the requester confirms (row 17) |
| "The author receives nothing during the run" | Receipt "cost" is data-dependent; update check and receipts reach the hub | Receipts hub-only, bucketed or tiered cost; author sees only batched aggregates; whole-list update fetch (rows 4, 25, 27) |
| D7 "taint, CaMeL/FIDES style" | D7 was substring overlap only | Labels `{integrity, conf, src}` are computed by the engine on typed values and checked at sinks (WF s2.2); the claim is "CaMeL-inspired label propagation at typed-value boundaries", not full CaMeL; substring overlap stays D6 |
| Hosted: "only the approved packet leaves" | Nebius key and prompts via the host; tokenized private items allowed | Hosted packets `low` only; hub gateway; no credential on host; prompts visible to the gateway stated (rows 24, 73, 86) |
| Sealed: "you can verify the pack build" | Needs a reproducible build that no phase designs | Sealed is roadmap; no verifiable-build claim until reproducible builds exist (rows 88, 107) |
| "revenue per run" | An open Pull pack can be run offline for free | Row 1 and row 72 |
| "ranked on evidence", "anyone can recompute" | Scores come from private hub-run suites; log operator is the ranker | Row 68 |
| `tested_on` inside the digest | Self-reference | Rows 55, 53 |
| "canary hit alone never affects reputation" | Ladder voids, freezes and proposes revocation on D2 alone | D2-soft/D2-hard split, DISPUTE_HOLD, attribution (rows 89, 97, 99) |
| "Pack cannot write U" | Episodic auto-write of foreign output launders it | Taint at capture, tiers, origin (rows 34, 37) |
| "No dump, no enumeration" | Bypassed by the whole-slice `/in` | No `/in` (rows 10, 41) |

Terms (audit 11 s4), now defined:

| Term | Definition adopted |
|---|---|
| host / owner / author / requester | **Author** publishes a pack. **Owner** = the person who controls a machine or an account that holds a pack or a host daemon; in specs use "author" or "host operator", not "owner". **Host operator** runs the Hosted daemon. **Requester** hires a pack. One person may hold several roles; payments where requester, author and host share a key or device fingerprint are rejected and self-runs are labelled "own pack" and excluded from ranking (SM s4.10) |
| tier | Banned alone; see CC-9 |
| Sensor Hub | The component inside the Sidecar that collects detector events; its events are signed with sequence numbers and verified by the Supervisor; loss is INFRA_FAULT |
| Scribe session | The only session with vault write rights; it sees schema-validated, length-capped, inert proposal fields only |
| quarantine memory snapshot | Replaced by: hashes plus a metadata diff by default; plaintext only with user opt-in, encrypted under a shreddable key, retention-limited |
| run token | Short-lived hub entitlement for one `run_id`; starts the run; a lease carries it on; gates certified-channel use (revocation, ranking credit, receipts, refund flow), not file execution |
| acceptance checks | Platform check library, classes P (platform) and R (requester); run in a throwaway no-network Cell; verdict requester-attested; authors choose from the library, cannot add code |
| phase | Retired; "step" in a workflow graph. Rights are per step and enforced by the Broker, Biscuit and mounts |
| strike vs slash | **Strike** = counted denial or quality signal on a pack (no money). **Slash** = forfeit reserve and unreleased payouts, only after class C or N evidence |
| detector numbering vs research-v2/06 | v2 numbering is authoritative (D1-D15 here); research-v2/06 numbers are historical and must not be cross-read |
| implementation language | Not decided: `flowd` and the analyzer Rust or Go; vaultd, Supervisor, Sidecar stack to be fixed by one ADR in phase 0 (Biscuit JS support UNVERIFIED) |

Items audit 11 listed as "asserted but never designed", with disposition:

| Item | Where it is designed now |
|---|---|
| Requester-agent loop and hub MCP surface | Rules in row 74 (typed fields only, taint rule); the full local-agent design is still a missing document; build phase 9b |
| Extractor pipeline | SM s7.1 (queue, scanner, taint); extractor model still open (D-4) |
| Daily digest | SM s7.2 (ordering, no bulk-approve for high-risk types); UX copy not written |
| Run-token semantics | SM s2.5, s3.2; row 77 |
| Acceptance-check execution | WF s2.7, s2.9; SM s2.11 |
| Reauthorize and long-run handling | SM s3.5; PayPal reauthorization rules UNVERIFIED |
| Fair-share queue for Nebius | WF s3.15 (per-run token buckets); hub gateway scheduling in phase 16 |
| Refund policy for Hosted rejected results | SM s4.7 fault-split table |
| Per-run conformance probe | WF s3.11; row 79 |
| Phase enforcement | Per-step grants; Biscuit attenuation; mounts (WF s3.4) |
| Revocation-list freshness policy | SM s6.3 |
| Reproducible build for Sealed | **Still not designed**; Sealed is roadmap |
| Tavily | CC-10 |
| Workflow-grade harness | `design-harness-workflow.md` |
| Judge-accessible demo | Row 108; phase 18 |

Hackathon-fit claims (audit 11 s6): "GO" and "satisfied" in v2 s12 are relabelled UNVERIFIED (row 111). The submission-subset mapping in section 5.3 addresses the fixed deadlines.

---

## 5. Build phases (dependency order, no calendar)

Replaces v2 s10. Each phase: prerequisites and exit test. `E*` are the engine phases from WF s3.17 folded into the same numbering. "Needs" lists real dependencies after fixing the audit's ordering errors (CON-F8): revocation hub sync no longer sits before the registry; the Certifier security suite needs vault, broker and detectors; phone approval needs the relay; ranking before the leaderboard demo.

### 5.1 Phase table

| # | Phase | Needs | Exit test |
|---|---|---|---|
| 0 | Foundations: glossary (section 4.7), ADRs (language, driver, parser), threat model with the requester as economic adversary, guarantee table with "enforced by / tested by" (section 6), author-bound channel schema, **digest spec** (raw bytes, covered-fields list, side documents outside the tree), strict YAML/JSON **shared parser and conformance corpus**, unified outcome enum, evidence kind and attestation source vocabulary, Ed25519 sign/verify | none | Spec reviewed; parser corpus passes in two implementations; sign/verify round trip |
| 1 | **E0**: `pack.yaml` and `workflow.yaml` JSON Schemas, types and labels, CEL integration, validator, licence gate, SBOM and secret scan, canonical-form rejection | 0 | Rejects bad fixtures (duplicate keys, CR bytes, YAML 1.1 coercions, wider `result_schema`) |
| 2 | Reference packs, first set: static fixtures (prompt-only analyst, code-bearing, malicious) | 1 | Fixtures usable in every later suite |
| 3 | SandboxDriver interface and conformance suite: no-NIC, automount, socket on ro bind mount, the D5 sensor fixture, per-run fast subset, 3-probe self-test, OOM vs ENOSPC classification, sleep/wake case, **bridge doctor**; T1 driver on a dedicated WSL2 distro; spikes (Docker Engine in WSL2 on Win11 Home, DrvFs, OpenShell, microsandbox); a Linux/EC2 fallback driver host | 0 | Driver passes or is downgraded; results recorded as ADRs |
| 3b | **Nemotron tool-calling smoke test and model pin**, CEL/RE2 library spike | 0 | Error rate and format-failure rate recorded; decision before E3 |
| 4 | Sidecar and Supervisor: model proxy (typed errors, bounded retries, pinned model, STALLED), tool broker, egress proxy, Result Guard with output-kind registry and render contract, torn-tail-safe audit log, **Supervisor WAL run row, boot reconciler, lease chain, orphan reaper** | 3 | Cell reaches the model only through the proxy; kill the Supervisor mid-run and the reconciler cleans up; audit verify detects tamper and survives a torn tail |
| 5 | Vault: record schema with `origin`/`derived_from`/`content_commit`, journal with encrypted payloads, **step-0 secret scanner**, CAS write gate, Q tier, tiers 0-3, per-run-id reference points (minimal hash chain), run-scoped revert primitive, shred contract (commit and tombstone), schema versioning; vault engine bake-off | 0 | Bake-off ADR; planted-secret test passes; revert test (user write survives) passes |
| 5b | Extractor and Scribe pipeline, extraction queue with dead-letter, daily digest, Reader/Scribe split, taint at capture | 5 | Poisoned web page to agent-written fact lands in Q |
| 6 | Memory Broker: Biscuit lens, `memory.describe`, `memory.search` over the closed staged set, accounted `materialize`, budgets, provenance, canary classes, read accounting | 4, 5 | MEXTRA and enumeration fixtures blocked or flagged; `cat /in` in a non-data step fails |
| 7 (E1) | **Journal and Run Store**: Supervisor writer, framing, recovery, blob store, per-run key, reconcile | 4 | Torn-tail recovery; replay folds to the same state |
| 8 (E2) | **Scheduler and state**: kinds `tool`, `branch`, `gate` (P class), `return`; reducers; hash-frozen artifacts; chaos-resume and replay tests | 1, 7 | Replay equivalence; gate-bypass attempt caught |
| 9 (E7a) | **Static analyzer** (checks 1-4, 9, 10, 12, 14 first; rest follow): termination, worst-case cost, capability-set hash, approval budget | 1, 8 | Analyzer reproduces the hand-computed worst case of the reference harness (USD 2.87) |
| 10 (E3) | **`llm` executor and context manager** | 8, 3b | An analyst workflow completes on synthetic data; every turn journaled |
| 11 (E4) | Loops, `map`, `parallel`, budget hierarchy, reserve, WINDING_DOWN, Progress Guard | 8, 10 | Infinite-loop pack stops at cap; deterministic partial result with no model call |
| 12 (E5) | `code` leaves, verifier cells, `adapter` steps (mini-swe-agent, deepagents) | 3, 11 | Code leaf has no network and no sidecar socket; verifier cell holds no vault data |
| 13 (E6) | **Human nodes, leases, sleep handling, hire order and the Pull run state machine** against a hub stub; unbounded re-prompt rule; N-4 canary overlap guard | 8, 4 | `human` timeout maps to a no-fault outcome; sleep/wake and resume pass the checklist |
| 2b | Honest reference packs (5-10 imported open harnesses with pinned SHA and clean licence, plus archetype packs) | 9, 11, 12 | FPR measurement can start |
| 14 | Disclosure Compiler, closed-set preview, approval card with `approval_hash`, data-flow strip, mode selector | 6, 9 | Preview matches the staged manifest; changed snapshot re-prompts at most twice |
| 15 | Detectors D1-D15 (D6 log-only), evidence kinds and attestation sources, **durable incident machine**, attribution step, local denylist and signed-list client with freshness and fail modes; **FPR on honest packs** | 4, 6, 11, 2b | Malicious pack killed with evidence preserved; honest packs do not trip D2-soft; FPR reported |
| 16 | **Pull end to end** through CLI: honest pack completes, malicious pack ends in the ladder, Accept path with ACCEPT_PENDING, proposals to Q, run-scoped revert | 2, 13, 14, 15 | Acceptance test list of SM s2 and s5 for Pull passes |
| 17 | Requester agent loop and hub MCP surface (typed fields only, taint rule, `browse_agents`) | 16, hub stub | Listing with injection text in every free-text field leaves pack and lens choice unchanged; a session that read pack output cannot call hire or Accept |
| 18 | Eval runner and Certifier base (no-pack baseline, separate pack/grader sandboxes, workers with no secrets, scripted answerer for human nodes, coarse outcomes, cost caps) | 1, 2, 4, 10 | Cheater pack caught |
| 18b | Certifier security suite (exfiltration and memory-theft fixtures, MINJA/MEXTRA, injected-lens test, sleeper and time-bomb variants, fingerprint-resistance test, structural conformance suite of WF s3.17) | 5, 6, 15, 18 | Cheater pack that conditions on cert signals is caught |
| 19 | Registry, signing, **hub-signed Merkle log with signed heads**, `card.json` (typed), attestation and listing documents, signed whole-list revocation with `seq` and `valid_until`, capability-set hash check, write-once CAS, key lifecycle (distrust-from-T, cooling flag), signer separate from Certifier | 18b | Third party verifies inclusion and consistency, re-aggregates from attestations; a Certifier credential attempting Sign fails; a client rejects a rolled-back list |
| 20 | Hub ledger and payments: ledger state machine, outbox, reconciler, idempotent PayPal calls, floor and outcome fees, accept deadline, DISPUTE_HOLD, silence rule (N-1), payee binding, rolling reserve, retraction entries, requester risk score | 16, 19 | Kill the hub mid-flow and restart: exactly one payout; kill-versus-accept race: exactly one wins; lost capture response: one capture; silence after STARTED captures the floor |
| 21 | Improvement loop: DSPy+GEPA on typed diffs, public-dev suite, held-out gate, lineage, spike for multi-step workflows | 18, 9 | v1.0 to v1.1 passes the gate and the leak test |
| 22 | E2E relay and phone approval (nonce, expiry, first-wins, content-free push) | 14 | Replayed or late approval is dropped and logged |
| 23 | Requester console: marketplace, run status contract, trace viewer, node graph, detector panel, cancel in two taps, accessible card text | 16, 19, 20, 22 | Demo path runs |
| 24 | Unsealed Hosted: host daemon, hub gateway (after the Nebius pass-through ToS check, D-19), quote and approval objects, heartbeats, fault split, probes, packet scanner | 14, 20, 22 | Silent host, slow-loris host and dying host each void the hold and kill the gateway token |
| 25 | Hardening: Sealed spike (Nitro), microVM tier, Sigstore/Rekor, multi-device sync, Merkle hardening, Meta-Harness proposer, witness for log heads | 24 | Attestation verified client side; tamper changes PCR |
| 26 | Red-team CI (garak, PyRIT, regression suite of row 101), honest-claims review against section 6, demo rehearsal with fallback clips | all | Claims table matches measured results |

Parallelizable: 3 with 5; 7-13 (engine) with 5-6 (vault and broker) once 4 exists; 18 with 14-16; 23 with 20; 21 with 22.

### 5.2 What changed in ordering versus v2 s10, and why

- Engine phases (7-13) are new and sit before Pull end to end because Pull now runs a workflow, not a three-phase loop (WF s3.17).
- Revocation: local signed-list client in 15 and hub distribution in 19 (v2 had the hub sync in phase 8 before the registry existed).
- Certifier security suite split to 18b because it needs vault, broker and detectors (v2 listed 1, 2, 4).
- Minimal hash-chain checkpoints in phase 5, not phase 16, because run-scoped revert and the attack demo need them.
- Relay (22) precedes anything that needs phone approval; demo path needs ranking (19) and payments (20).
- Honest reference packs (2b) precede FPR measurement.
- Requester agent loop and extractor pipeline now have phases (17, 5b).

### 5.3 Submission subsets (fixed external dates; the subset content is my recommendation, effort is not estimated)

Dates from `HACKATHONS.md` (not re-read here for rule text; prize rules are UNVERIFIED): Amazon 23/10 (Alexa on hold; only the Open Source and AWS Builder mini challenges apply), Nebius x NVIDIA 30/10, PayPal 12/11.

| Milestone | Smallest phase subset that supports an honest demo | Demo path needing nothing unbuilt |
|---|---|---|
| M1, Amazon mini challenges, 23/10 | 0, 1, 2, 3, 4, 5, 6, 7-11 (engine core), 14 (CLI card), 15 (core detectors), 16 (Pull CLI); hub is a stub on AWS | Live honest run through the workflow engine; attack theater and recovery shown "replayed from certified run"; open-source repo, README, NOTICE |
| M2, Nebius x NVIDIA, 30/10 | M1 plus 18, 19 (minimal registry and signed attestation), 21 (replayed improvement), 23 (console subset) | Nemotron IDs in the cost header; v1.0 to v1.1 shown as a recorded certified run |
| M3, PayPal, 12/11 | M2 plus 20 (ledger, authorize/capture/void, payout in sandbox), 22 | Sandbox money with a "test money" badge; DISPUTE_HOLD path; "demo holdback 0 s" label |

Whether live resume or live GEPA fits the 3:00 cut is UNVERIFIED until phase 13 and phase 21 exist; the plan assumes recorded segments for both.

---

## 6. Guarantee list: only claims that have a mechanism

### 6.1 Claims we may print (each has an enforcer and a test)

| # | Claim (as printed) | Mechanism | Enforced by | Tested by | Caveat printed with it |
|---|---|---|---|---|---|
| G1 | The foreign pack has no network interface | `--network none` netns, ro rootfs, caps dropped, non-root; fast conformance subset before each private run; 3-probe self-test at Cell start | Driver, Supervisor | Driver conformance fixtures; per-run self-test | Only for a driver tier that passed; WSL2 result UNVERIFIED; sandbox 0-day |
| G2 | The pack's only exit is a requester-owned sidecar | Unix socket `/run/bridge` only; `flowd` has no NIC; Nebius key only in the requester's sidecar (Pull) | Driver, sidecar | No-NIC and socket fixtures | Result text and typed fields are still an output channel |
| G3 | The author receives nothing during the run | No author endpoint; hub never gets vault content; per-run receipts hub-only | Architecture, hub schema | Receipt schema test | Post-run aggregates exist (k >= 20, delayed); render- and apply-time fetches of URLs in results are not covered except by CSP and no auto-fetch |
| G4 | The pack sees only the lens | Closed staged set (record id, version, content hash); per-step grants attenuated by Biscuit; no whole-slice mount; slot caps by trust tier; read accounting | Memory Broker, Tool Broker, mounts | MEXTRA/enumeration fixtures; `cat /in` in a non-data step fails; phase-rights test | Detection of misuse is advisory; "detect, not prevent" for the output channel |
| G5 | The output channel is bounded | Typed narrow schemas, size caps, output-kind registry, Result Guard, non-streaming private runs, quote budget | Result Guard, `flowd` | Oversized and permissive-schema fixtures | Worst-case bits per run published; steganography and covert timing not closed |
| G6 | Foreign pack output cannot reach your durable memory without your decision | Proposals go to Q; Reader/Scribe split; taint at capture; tier 1 endorsed-foreign; immutable `origin`; Accept is not a corroborating class | vaultd write gate | Poisoned-page test; accept-then-revoke test | Approval fatigue is an open UX risk; one-click accept stores a pack claim, not a fact |
| G7 | A flagged run can be undone without destroying your other work | Run-scoped compensating revert by `origin`/`derived_from` closure; REVIEW state; CAS on tainted version | vaultd | User-write-survives test; sleeper test | Data already exposed cannot be recalled |
| G8 | Spend is capped | Hierarchical budgets, engine reserve, proxy token and USD caps; analyzer proves worst case at or below the declared cap; author price per accepted milestone | `flowd`, Model Proxy, analyzer | Looping-pack fixture stops at cap | Nebius billing in Pull is your own account; infra retries not charged |
| G9 | A long run survives a crash or sleep | Journal replay, memoized steps, lease and epoch, resume checklist | Supervisor, `flowd` | Chaos-resume test; sleep/wake fixture | Single device; at most 3 resumes; `adapter` and `code` steps restart from their start; model must still exist |
| G10 | One hire makes one hold, one capture, one payout | Idempotency keys `run_id:op:seq`, CAS ledger row, outbox, reconciler, token re-bind until STARTED | Hub | Kill-hub, kill-vs-accept and lost-response tests | A capture can still decline (PayPal risk); the hold is not a guarantee; honor-period limits (see SM s3.1) |
| G11 | Incident claims from your machine cannot, by themselves, void an author's work or revoke a pack | Evidence classes; DISPUTE_HOLD; Certifier replay; N=3 corroboration; claim rate limits | Hub, Certifier | Forged-claim fixture | Pull has no fair exchange; the requester can keep the output |
| G12 | Pack bytes match what was signed | Raw-byte digest, signatures, D9, hub-signed log with signed heads | Registry, supervisor | Digest conformance corpus; tamper fixture | The log is hub-signed, not independently witnessed; "pin means content fixed, not safe"; you trust the bridge binaries you installed |
| G13 | The ranking is a deterministic function of attested numbers | Scoring protocol v1, attestation fields, paid signals demote or tie-break only | Hub, Certifier | Third-party recompute of aggregation | Scores are hub-attested; payer distinctness is hub-attested; the badge means "evaluated on suite S for model M", not "safe" |
| G14 | Revoked packs do not start; in-flight handling follows the reason | Signed whole-file list with `seq` and `valid_until`; local denylist wins; stale list fail modes; reason-to-action table | Supervisor | Stale, rollback and outage tests | Packs without a hub token are "unrevocable"; hub outage never unblocks |
| G15 | What you approved is what runs | `approval_hash` over digest, capability-set hash, snapshot manifest, TaskSpec, cap, model, engine, driver; recompute at launch | Supervisor | Mismatch re-prompt test | Max 2 re-prompts per run |
| G16 | Hosted: only the approved packet leaves, and the host operator can read it | Compiler, deterministic scanner, single-use approval object bound to packet hash and host key, envelope signature | Compiler, relay encryptor | Packet-mismatch refusal test | Unsealed: host key is hub-trusted; host copies are undetectable; verdicts host-attested; low sensitivity only; no failover |
| G17 | Secrets are never given to a pack or written raw to the journal | Capture-time scanner and handles; dereference only in the Tool Broker | vaultd, Tool Broker | Planted-secret test over journal, extractor payload, audit log, quarantine | Scanner recall is imperfect (UNVERIFIED rate) |
| G18 | A shredded record cannot be read from this device | Per-record key destroyed; keyed commitment; index and embedding rows deleted | vaultd | Shred test across index and journal | Complete only when every device acknowledged; text already sent to Nebius or an offline device stays |
| G19 | A timeout never convicts a pack | Every human-wait timeout maps to abort-clean or a no-fault outcome | `flowd`, Supervisor | Pause-timeout mapping test | Rate-limited per requester to stop free-run abuse |
| G20 | Kill happens only on deterministic evidence | D2-hard, D5, D9, D12 (positive evidence), D8a; D6/D13/D14 advisory; D6 log-only until FPR measured | Detector engine | FPR on honest packs; cheater fixtures | Public rules; slow in-lens exfiltration may evade |
| G21 | Phone approvals cannot be replayed | Nonce, expiry, first valid decision wins, Supervisor sole state authority, kill needs no relay | Supervisor | Replay and late-delivery tests | WebAuthn, lost-phone revoke are production items |

### 6.2 Claims removed or rewritten (no mechanism, or contradicted)

"Nothing leaves your machine" (unqualified); "revenue per run" as enforced metering; "anyone can recompute the ranking" (now: anyone holding the log can recompute the aggregation); "transparency log" naming; "certified" read as "safe" (now "evaluated"); "byte-exact preview" for any live query; "ZDR enabled by hub" for Pull; "per-task Nebius key with budget" handed to a host; "fresh context per phase" in one Cell (now per step, by `flowd`); "roll back U to a checkpoint"; "Hosted protects pack IP"; "detectors prevent theft"; "canary hit never affects reputation" as a bare sentence (now enforced by evidence classes); "you can verify the Sealed pack build" (roadmap); "Pull verdicts are trustworthy to the requester" as a proof to anyone else.

---

## 7. Owner decisions (merged with the original 15)

### 7.1 Still open: needs your call

| ID | Decision | Origin | Recommendation |
|---|---|---|---|
| D-1 | Primary headline: marketplace-first or security-first | v2 #1 | Marketplace-first; lead the demo with the hire, show security as proof |
| D-2 | Vault engine: accept the bake-off, or fix SQLite plus our journal now | v2 #2 | Run the bake-off in phase 5; do not delay phase 5 for it |
| D-3 | Capabilities library: Biscuit (JS/WASM UNVERIFIED) vs macaroons | v2 #3 | Biscuit if a Rust/WASM path is confirmed in phase 0 |
| D-4 | Extractor model: local small model, or Nebius Nemotron with consent. Narrowed: high-sensitivity text is never sent to a remote extractor, and remote use is opt-in per sensitivity level | v2 #4, MEM-F5 | Local for high; Nebius with consent otherwise |
| D-5 | Promotion defaults that remain: daily digest vs per-item, and how many independent ancestries. (Decided: independence by DAG, no auto-promotion with foreign taint, Accept not corroborating) | v2 #5 | Digest for low-risk, per-item for profile and procedural |
| D-6 | Runner adapters beyond the built-in `flowd` loop (mini-swe-agent, deepagents, OpenClaw, Claude Code) | v2 #6 | Built-in first; adapters only as class O, one at a time |
| D-7 | Who authors private suites per speciality, without conflict of interest | v2 #7 | Platform-written, versioned, rotating, with commit-reveal of retired suites and a "platform-seeded" label |
| D-8 | Protected IP: is a Hosted-only tier acceptable; invest in split shell/brain | v2 #8 | Document only; do not build for now |
| D-9 | Demo target: WSL2-only, or add a Linux/EC2 fallback driver host and a judge-runnable path | v2 #9, CON-F9 | Add the EC2 fallback; plan a docker-compose judge path |
| D-10 | Streaming for private-data runs | v2 #10 | Non-streaming (the reference workflow already sets it) |
| D-11 | Sealed Hosted: build at all, and who operates the hosts | v2 #11 | Roadmap clip only |
| D-12 | Multi-device sync: build timing (the spec is closed, SM s7.10) | v2 #12 (modified) | After phase 1 of the vault ships |
| D-13 | Payments production path: PayPal partner/multiparty, counsel review (money transmission, tax on digital services, refunds, sanctions), fee percentages | v2 #13, PAY-F9 | Sandbox only for the hackathon; counsel review is a gate before real money |
| D-14 | **Is Pull's lack of fair exchange acceptable** if floor fee, reject-rate score and dispute path mitigate it? A positioning call | SM OD-1 | Accept and say so in the guarantees |
| D-15 | Floor fee size and what it covers | SM OD-2 | 20-30% of price (proposal, unsourced) |
| D-16 | Per-run price for open packs: require `licensed-watermarked` or `split-shell-brain`, else label donation | SM OD-3 | Yes (lint rule) |
| D-17 | Does v1 build resume, or only void-and-rehire with checkpoints written | SM OD-4 | Build void-and-rehire first; resume after phase 13 passes chaos tests |
| D-18 | Hosted gateway cost on host fault, and claim deposit size | SM OD-7 | Hub bears, bounded by cap, recovered from host holdback |
| D-19 | **Nebius terms for passing inference through to third parties (Hosted gateway)**: blocker before phase 24; fallback is a requester-supplied key | SM OD-13, CON-F4 | Read the terms first; UNVERIFIED |
| D-20 | Adjudicator and appeal SLA | SM OD-10 | Hub operator, replay first, 5 business days; you are that operator for the hackathon |
| D-21 | Reserve percentages and indeterminate splits | SM OD-8 | 50% reserve to day 180 for new authors; 50/50 on indeterminate (proposals) |
| D-22 | Are class O packs (adapter runner loops) admitted for private-data Pull in v1 or only class S | new | Admit with a visible label and a separate ranking column |
| D-23 | Treat the model call as a sanctioned sink in the Rule-of-Two analysis (shown on the card), or as external communication | new (WF s4 #5) | Sanctioned, listed on the card |
| D-24 | Approval budget ceiling per run (6 cards is a guess) | WF s4 #12 | 6, measure approval telemetry |
| D-25 | Engine language for `flowd`, the analyzer and the sidecar stack | WF s9 #1 | One memory-safe language for the TCB (Rust or Go), decided in phase 0 |
| D-26 | Human wait ceilings (CC-1): the reference harness assumes hours, the state machines allow 3 h total | new | Platform ceilings win; "away mode" extension for longer waits |
| D-27 | Long-run dispute clocks vs the honor window (CC-7): capture into hub balance for disputed runs (custodial exposure) or shorten the rebuttal window | new | Shorten the rebuttal window; capture-to-balance only with counsel sign-off |
| D-28 | Silence after STARTED captures the floor (N-1) instead of voiding | new | Yes |

### 7.2 Defaults adopted by the design (dropped from the open list; veto if wrong)

| Was | Adopted default | Where |
|---|---|---|
| v2 #14 free and open packs in ranking | Separate Certifier-only board; paid signals only demote or tie-break | CERT-F7; row 70 |
| v2 #15 which sensitivities are Pull-only; SM OD-15 | Hosted packets `low` only, user-confirmed; never secret, high, untagged, Q or pack-derived | SM s4.8 |
| v2 #12 root-key recovery | User root key with recovery phrase; no hub escrow by default | SM s7.7 |
| v2 #7 who pays certification tokens; SM OD-12 | Author pays up front, tied to a verified identity; platform subsidizes only seeded reference packs | SM s6.1 |
| SM OD-5 Hosted failover | Off; opt-in per task re-discloses and needs a new approval | SM s4.4 |
| SM OD-6 run length | 24 h per authorization segment in v1 | SM s3.5 |
| SM OD-9 revocation windows, N | 24 h / 12 h / 1 h by sensitivity; N=3; "aged" = 30 days and non-trivial spend | SM s6.3 |
| SM OD-11 tier numbering | Tier 1 = endorsed-foreign | SM s7.4 |
| SM OD-14 attestation override | Allowed with a banner and exclusion from verified-paid ranking | SM s6.5 |
| N-2 `ask` in Hosted | Rejected at quote time in v1 | section 3.2 |

### 7.3 Obsolete or answered by the facts

- v2 #6 "first runner adapters: builtin loop first (recommended)": answered, `flowd`'s `llm` executor is the built-in; the remaining question is D-6.
- v2 #12 CRDT vs plain replication: answered for design (per-device sub-chains plus version vectors); only timing remains (D-12).
- Round 1 "owner sees a preview of the result before it leaves" (decisions.md): obsolete for Pull (result stays local); in Hosted it becomes the host-side preview in the role matrix (SM s4.10).

---

## 8. What is still UNVERIFIED (honest list)

External facts and rules:

- **PayPal**: whether reauthorization is allowed during the honor period; `PayPal-Request-Id` retention and length limits; `final_capture` semantics with multiple captures; error codes for capture-after-void and void-after-capture; the refund window of a capture; the 180-day dispute window (secondary source, `research/09`); seller protection for intangible AI services; Payouts by payer id and the `sender_batch_id` dedupe window; "Log in with PayPal" mechanics; multiparty and `platform_fees` access for a hackathon account; whether an unattended re-authorization of a payer order exists; whether the sandbox reproduces dispute behavior; what the payer-id field exposes for wash-trading analysis. (Facts SM reports as verified: 29-day hold, 3-day honor, "subject to risk and money availability", reauthorization yields a new id, void exists; source URL above; not re-fetched here.)
- **Nebius**: per-key spend caps and scopes; per-key ZDR; whether pass-through to third parties is allowed by its terms (D-19); rate-limit uplift; stability of model ids and revisions; whether KV-cache benefits exist; whether Nemotron on Nebius gives reliable native tool calling (smoke test, phase 3b); availability of Nemotron Safety Guard on Nebius.
- **Hackathon rules**: the Devpost texts returned 503; prize categories, the Open Source and AWS Builder mini-challenge rules, the Nebius "must run on Nebius" reading versus an AWS-hosted hub, the working-demo-URL requirement (secondary source). All "GO" and "satisfied" claims in v2 s12 are unverified.
- **Platform and tooling**: WSL2 sleep and idle behavior (`vmIdleTimeout` 60 s noted in research-v2/07), parent-death behavior, DrvFs and automount fixtures, Docker Engine in WSL2 on Win11 Home, tmpfs behavior, Tetragon feasibility on WSL2; Biscuit JS/WASM support; Presidio, Tetragon, gVisor, Firecracker, libsodium, OPA/Cedar licences "UNVERIFIED in this run" (v2 s8); OpenShell licence and Windows Home support; CEL library choice and an RE2-class regex engine; Rekor fit for private metadata; NeMo Evaluator fit beyond its README; GEPA/DSPy on multi-step workflows; deepagents and mini-swe-agent per-step event hooks.
- **Sealed**: no documented GPU path from Nitro; reproducible-build requirement undesigned; trusted time inside the enclave.
- **Legal**: merchant-of-record exposure, money transmission, tax on digital services, sanctions, consumer refund law, warranty reading of "certified", defamation exposure of public incident attribution, erasure law applicability. No counsel review done.
- **Numbers and benchmarks**: Mem0 and other vendor benchmark scores (unreproduced); the 93% approval rate cited in v2 4.8 (secondary); PromptBridge (abstract level); CaMeL utility numbers (AgentDojo only).

Our own proposals that are untuned (every one needs measurement before any claim): all thresholds, TTLs, fees and percentages (floor 20-30%, reserve 50% to day 180, holdback 14 d, k >= 20, N=3, 66 h segments, 10-15 s lease, 3 resumes, 3 h wait cap, 6 cards per run, 60% context fit, Progress Guard thresholds borrowed from OpenHands and untuned for Nemotron, compaction trigger 0.70, bit budget 24); the 18-check analyzer's soundness (depends on tool metadata); whether label-driven gating makes real tasks unusably gate-heavy (utility cost UNVERIFIED); whether a P/R-only milestone set is rich enough for fair partial capture; false-positive rates of D2, D6, D8b, D14 on honest packs (not yet measured; D6 ships log-only); the secret scanner's recall; whether the Certifier's fingerprint-resistance tests actually catch a cert-aware pack; whether `flowd` plus an engine-owned agent loop is good enough with Nemotron; whether live resume and live GEPA fit a 3:00 cut.

Not verified by anyone yet because nothing is built: every "Tested by" entry in section 6 is a plan, not a result.

---

## Appendix A. Edits required in the two design files (not made here)

- `design-harness-workflow.md`: s2.11 and s3.10 numbers and `waiting_s` (CC-1); s2.10 mid-run capture wording (CC-6); s6.2 evidence-class letter `C` (CC-3) and D8 split (CC-4); s1.3 "tier 0 / tier 1" wording (CC-9); s3.3 outcome enum (CC-5); add the Certifier's scripted answerer for `human` nodes (N-3); reject `ask` in Hosted (N-2).
- `design-state-machines.md`: s2.3 and s2.4 Cell wording and STARTED ack (CC-2); s1.7 and s5.1 D8 (CC-4); s2.3 anchor cadence (CC-11) and re-prompt bound (N-5), canary-overlap guard on `AUTHORIZED -> STARTING` (N-4); s2.12 step 4 and s3.4 silence rule (N-1); s5.4-s5.5 rebuttal window (CC-7); s6.4 side-document sentence (CC-8); N-6 row in s3.4 or s2.11; s8 conflict 12 resolution text.
