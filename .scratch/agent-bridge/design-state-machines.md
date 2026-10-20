# agent-bridge: behavioral flows as explicit state machines

Date: 2026-10-07. Scope: the six flows (a) Pull run, (b) payment hold and settlement, (c) Hosted run, (d) incident/kill/rollback/appeal, (e) pack version, key and revocation states, (f) vault write, Q, promotion and revert. Inputs: `architecture-v2.md`, `decisions.md`, `research/`, `research-v2/`, and the 132 audit findings supplied with the task.

Conventions
- Every decision is tagged with the finding it fixes, written `[PR-F1]`. Prefixes: PL = pack lifecycle, PR = Pull run, PAY = payment/escrow, HO = Hosted, MEM = memory, DEF = active defense, HUM = human-in-the-loop, CERT = certification/ranking, ID = identity/trust roots, TASK = task I/O model, CON = consistency audit. The number is the finding's `Fn` within its flow. Findings the audit marked "not-checked" are adopted conservatively and flagged `(unchecked)` in section 11.
- Anything not confirmed from a primary source is marked UNVERIFIED. All fees, TTLs, thresholds and percentages are our own proposals, not sourced. Section 9 lists the owner decisions; each is written `OD-n`.
- PayPal facts. Verified this session from https://developer.paypal.com/docs/checkout/standard/customize/authorization/ : a hold lasts 29 days; capture must happen in the 3-day honor period; "Payment capture is subject to risk and money availability"; multiple reauthorizations are allowed inside the 29 days, each gives a new authorization id and restarts the 3-day period; the API exposes a void link. Everything else about PayPal (reauthorize-during-honor rule, `PayPal-Request-Id` retention, error codes, `final_capture` semantics, 180-day dispute window, refund window, Payouts by payer id) is secondary-source (`research/09`) or UNVERIFIED; see section 10.
- "Payment hold" is used instead of "escrow" in user-facing copy; the design only uses authorize / capture / void [PAY-F9].

---

## 1. Shared primitives (used by all six machines)

### 1.1 Who owns which state

| State | Authority | Persistence | Why |
|---|---|---|---|
| Run entitlement, lease, money ledger, payout, revocation list, pack/attestation/listing state | **Hub** (single SQLite-WAL or Postgres row per run, CAS on a `rev` column) | Durable store; intent row written before any PayPal call | Only the hub can serialize accept/kill/void races [HO-F6, TASK-F7, PAY-F4] |
| Cell, stage, step checkpoints, local incidents, result store R, denylist, audit log | **Supervisor** (per-requester machine, SQLite-WAL, fsync per transition) | Local; head hash anchored to hub | Only the supervisor can destroy data and kill [PR-F1] |
| Vault records, journal, Q, provenance | **vaultd** (journal is truth; index is derived) | Hash-chained journal | Existing v2 rule |
| Hosted task state (distinct from Pull) | **Hub**, with host and requester as signed event sources | Same as hub | Host is untrusted [HO-F7] |

Rule: no component trusts another component's claim about a domain it does not own. The hub never trusts a supervisor about whether a result was good; the supervisor never trusts the hub about whether data should be destroyed.

### 1.2 Identifiers and idempotency [PR-F3, PAY-F4, TASK-F7, ID-F8]

- `run_id` is a ULID minted by the **requester** before the first hub call. All hub calls carry `Idempotency-Key = run_id:op:seq`. The hub stores `(run_id, op, seq) -> response` and returns the stored response on retry.
- `op` in {create_run, authorize, bind_token, started_ack, checkpoint_anchor, result_ready, accept, reject, cancel, incident_claim, capture_floor, capture_outcome, void, refund, reauthorize, payout}. `seq` increments only for a deliberate distinct repeat (for example capture of milestone 2).
- PayPal calls use `PayPal-Request-Id = run_id:op:seq` (length limit UNVERIFIED; fall back to a hash of that string). Do not rely on PayPal's key retention (6 hours in `research/09`, secondary, UNVERIFIED): on any retry older than 1 hour the sender first GETs the resource and reconciles, then retries only if the effect is absent.
- `epoch` is a hub-held integer per run. A supervisor event is accepted only if `event.epoch == run.epoch`. Resume on another device bumps `epoch`, so stale supervisors are rejected [TASK-F7, ID-F8].
- Terminal states absorb. Any event arriving after a terminal state is logged as `LATE_EVENT` and has no effect.
- Every hub-bound event is signed by the sender key and carries `(run_id, epoch, event_id, seq)`. Per-run event seq is monotonic; the hub drops duplicates (same event_id) and out-of-order events older than the last applied seq for the same source [HO-F11].

### 1.3 Durability pattern (write-ahead + outbox) [PR-F1, PR-F12, DEF-F8, PAY-F4, PAY-F5]

1. State change = one SQLite transaction that updates the run row and inserts zero or more `outbox` intents (target, op, idempotency key, payload hash, status).
2. fsync (WAL `synchronous=FULL`) before the side effect is attempted.
3. A sender worker drains `outbox`, retries with jittered exponential backoff, records the response, and marks the intent DONE. Intents are idempotent by key.
4. On boot, every machine runs its reconciler (section 2.12, 3.6, 5.8): re-drive unfinished outbox intents, then compare local state with the remote system by GET.
5. The local denylist write always comes first among incident steps; it needs no network.
6. Audit-log append failure is fail-closed: freeze the run, do not keep serving (see 2.9). Audit entries use length+CRC framing; a torn final frame is truncated and a recovery marker appended; only a mid-chain hash mismatch is "tamper" [DEF-F8]. The chain head is anchored (content-free hash) to the hub at each checkpoint so tail truncation is detectable [PR-F12, ID-F11].

### 1.4 Time [PR-F2, HO-F11, ID-F8]

- Run budgets use `CLOCK_MONOTONIC` with suspended time subtracted, plus a separate hub-side wall-clock TTL. Expiries on signed objects use **hub time** (hub stamps `issued_at`, relative TTL, bounded skew window of 2 minutes); device clocks are never authoritative for money or entitlement.
- After any gap longer than 30 seconds (sleep, VM pause) the supervisor revalidates: run lease, PayPal authorization status (via hub), revocation list freshness, Nebius reachability, sidecar lease. It does so before resuming any step.
- The supervisor holds a sleep inhibitor for the whole RUNNING period (Windows power request; WSL2 keepalive) and records a `suspend_count` and `suspended_ms` in the run summary. Sleep inhibitor failure is a preflight warning, not a refusal.

### 1.5 Evidence classes (what a signed claim is worth) [PL-F2, PAY-F1, DEF-F4, CERT-F1, ID-F4, CON-F3, HO-F9]

| Class | Meaning | May trigger |
|---|---|---|
| H, hub-observed | Hub saw it itself (gateway usage in Hosted, token states, payment events, heartbeat arrival) | Any hub action |
| R, requester-attested | Signed by a supervisor the requester controls (Pull) | Local effects, DISPUTE_HOLD, a counted claim. **Never** a final VOID of delivered work, a payout freeze that outlives adjudication, a hub-wide revoke, a slash, or a public incident count |
| O, host-attested | Signed by a Hosted host | Voids that run and downgrades the (host, pack) pair only |
| C, certifier-reproduced | Hub Certifier re-ran the same pack digest on a synthetic lens with the committed canary placement and the incident reproduced | Revocation, slash, public incident, author reputation |
| N, independent corroboration | At least N=3 independent, aged (account age and spend thresholds, OD-9) requesters with hub-committed canaries filed matching claims on the same digest | Same as C |

Pull verdicts are labelled "requester-attested" on every incident record and listing, the same way 7.4 of v2 labels Hosted [PAY-F1, DEF-F4, CON-F3].

### 1.6 Fault classes (decide who pays and who is struck) [PR-F2, PR-F7, PR-F8, DEF-F3, HUM-F5, PR-F12]

| Class | Examples | Pack strike / author effect | Requester effect | Money rule (see 3.4) |
|---|---|---|---|---|
| INFRA_FAULT | Sidecar heartbeat lapse, sleep/wake, VM stop, Docker down, Nebius 5xx/429 beyond retries, model not found or model field mismatch, hub unreachable at a required check, torn log, supervisor crash | none | none (re-queue offered) | void unspent; capture only milestones already accepted |
| RESOURCE_EXHAUSTED | ENOSPC, OOM (tmpfs counted against memory cgroup), stage too big | none | none | as INFRA_FAULT; no auto-retry |
| REQUESTER_FAULT | User cancel, pause or gate timed out, approval expired, requester caps hit before declared limits | none | counted in requester abort rate | accepted milestones + floor fee if the run was billable |
| PACK_FAULT | Budget burned inside the pack's own declared limits with no result, schema failures, loops to cap, Result Guard reject of verbatim canary or bulk quoting | non-security quality strike | none | void; accepted milestones captured |
| DATA_INDUCED | A detector fired because the trigger text traces to a foreign record in the lens or in Q | none | hygiene warning naming the record | floor captured, outcome void |
| UNCONFIRMED_PAUSE | A probabilistic-detector pause (D6, D8, D4) timed out with no human decision | none | counted in abort rate | treated as REQUESTER_FAULT money; no strike, no quarantine, no payout freeze |
| INCIDENT_CLAIM | Deterministic CRITICAL evidence, requester-attested | none until adjudicated | claim counted | floor to DISPUTE_HOLD, see 5.4 |
| HOST_FAULT / AUTHOR_FAULT | Hosted only, see 4.7 | host strike / author strike | none | split table 4.7 |

D12 (sidecar tamper) fires **only** on positive tamper evidence (bad signature, unexpected socket peer, hash mismatch, unauthorised write to the sidecar). A missing heartbeat or a dead process is INFRA_FAULT [PR-F2, DEF-F12].

### 1.7 Waiting on a human (single family) [PR-F7, HUM-F5, HUM-F12, DEF-F3, TASK-F3]

Every wait has: kind, channel, deadline, default on timeout, and effect on each clock.

| Kind | When | Channel | Deadline (default) | On timeout | Run/budget clock | Hold clock | VM / proxy / Nebius |
|---|---|---|---|---|---|---|---|
| AWAIT_APPROVAL | Before start | console, phone | 15 min | EXPIRED_APPROVAL, wipe stage, no hold exists yet | n/a | not started | n/a |
| AWAIT_GATE | Workflow human gate node (typed: choose/confirm/short_text<=200 chars) | console, phone | author declares, capped at 60 min, user may extend | default declared on the node: stop with partial result (never "destroy") | paused | **keeps running** (PayPal cannot be paused) | VM frozen, proxy stopped, Nebius key idle |
| AWAIT_PAUSE_REVIEW | Probabilistic detector pause (D4, D6, D8, strikes, D13) | console, phone, notification | 30 min, extendable once | UNCONFIRMED_PAUSE: ABORTED_CLEAN | paused | keeps running | frozen |
| AWAIT_REAUTH | Hold nearing honor limit during a long run | console, phone | 60 min | ABORTED_CLEAN, milestone capture | paused | keeps running | frozen |
| AWAIT_REFRESH | Revocation list expired mid-run, hub unreachable | automatic retry, then user | 30 min | ABORTED, INFRA_FAULT money | paused | keeps running | frozen |

Hard rules: (1) a wait deadline plus the remaining run time plus the accept window must be shorter than the hold's honor limit minus 6 hours, or the supervisor requests AWAIT_REAUTH first [PR-F7, PAY-F3, HUM-F5]; (2) total waiting is capped (default 3 h per run) and never consumes the run budget [PR-F7]; (3) no wait default is "kill and punish": kill-incident requires deterministic evidence or an explicit human "confirm theft" plus a second detector [DEF-F3, HUM-F5]; (4) gates are workflow nodes at step boundaries, not blocking calls inside a step; a pack that needs input mid-step ends the step with typed `NEEDS_INPUT` and the graph routes to a declared gate or to a partial-result terminal [TASK-F3]; (5) the question text is untrusted pack output: rendered as inert plain text, labelled "from pack, unverified", length-capped, passed through Result Guard and never fed to an LLM that has vault read access; answers are typed data from the human, or from a lens-limited answerer that goes through the Broker [PR-F7, TASK-F3]; (6) notifications are content-free ("a card awaits") [HUM-F3, HUM-F12]; (7) timers are configurable and extendable for accessibility [HUM-F12].

### 1.8 Terminal outcome catalogue (supervisor view)

COMPLETE, PARTIAL_BUDGET (`partial=true` + completed step list), FAILED_PACK, FAILED_INFRA (includes RESOURCE_EXHAUSTED), KILLED_INCIDENT, CANCELLED, ABORTED_CLEAN, FAILED_RESTART, EXPIRED_APPROVAL, REFUSED_PREFLIGHT [PR-F9, HUM-F5, TASK-F10]. Money for each is in 3.4.

---

## 2. (a) Pull run

### 2.1 Records

- **Hub run row**: `run_id, requester_key, pack_digest, capset_hash, mode=pull, approval_hash, epoch, lease{lease_seq, last_cp_hash, expires_at}, token_state, canary_commit, ledger_state (section 3), quote{floor, outcome, cap}, deadlines{auth_t0, honor_limit, run_deadline, accept_deadline}, state`.
- **Supervisor run row (WAL)**: `run_id, state, step_id, iter, epoch, auth_id (opaque ref from hub), token_id, cell_label, stage_ref (+ per-run key ref in OS keystore), audit_head, checkpoint_head, approval_hash, billable (bool), resumes, suspend_ms, outcome`. One row per run, plus append-only `run_event`.
- **R store**: supervisor-owned, content-addressed, encrypted under keys derived from the vault key ids of the records the artifact derived from (so shred invalidates dependents) [TASK-F6, PR-F5]. A pack never writes R; step outputs are validated by the supervisor and committed.

### 2.2 States (supervisor machine)

`CREATED -> PREFLIGHT -> STAGING -> CARD_PENDING(AWAIT_APPROVAL) -> APPROVED -> AUTHORIZING -> AUTHORIZED -> STARTING -> RUNNING -> [WINDING_DOWN] -> ASSEMBLING -> DRAINING -> CLEANING -> RESULT_READY -> (settlement owns the rest) -> DONE`

RUNNING has sub-states: STEP_ACTIVE, CHECKPOINTING, GATE_WAIT, STALLED (model API), SUSPENDED_INFRA, PAUSED_DEFENSE, RESUMING, CANCELLING.
Terminal: see 1.8.

### 2.3 Transition table

| From | Event | Guard | To | Durable side effects (in one txn, then outbox) |
|---|---|---|---|---|
| (none) | user hires pack | pack not on local denylist | CREATED | mint run_id; fix TaskSpec; insert row |
| CREATED | start | revocation list fresh for sensitivity (6.3), driver fast conformance subset passes (<10 s: virtualization, automount off, no /mnt/c, unix socket on ro bind, no-NIC probe) [HUM-F8, CON-F12], disk and tmpfs quotas, RAM admission under the 6 GB WSL cap, concurrency limit, model pinned and probed, sleep inhibitor taken | PREFLIGHT ok -> STAGING | else REFUSED_PREFLIGHT with plain-language reason and remedy ("what failed, what it means for your data, what you can still do") [HUM-F8]. **No hub payment call has happened yet** [PR-F3] |
| STAGING | lens evaluated once | closed set = (record_id, version, content_hash) + vault seq + sensitivity histogram; secret-type never included; folder inputs: symlink-inside-grant only, `.git` and dotfiles excluded, secret scan [TASK-F11] | CARD_PENDING | write sealed slice (encrypted under per-run key held by supervisor keystore, outside the VM); compute `snapshot_hash`; wipe if card not decided in 15 min |
| CARD_PENDING | user approves (console or phone) | decision signature valid over `approval_hash = H(pack digest, capset_hash, mode, snapshot_hash, lens def, quote cap + quote id, driver tier + conformance run id, run_id, expiry)`; nonce unused | APPROVED | store nonce; record approval use counter in audit log [PR-F11] |
| CARD_PENDING | user denies / expiry | | EXPIRED_APPROVAL or CANCELLED | wipe stage |
| APPROVED | first hub call | recompute snapshot hash and delta triggers (new matching record above sensitivity shown, set grows more than X%, driver fingerprint changed); on mismatch go back to CARD_PENDING | AUTHORIZING | outbox: `create_run` then `authorize` (idempotent, run_id keyed). AUTHORIZE is the **last step before start** to shrink orphan-hold windows [PR-F3] |
| AUTHORIZING | hub ok (token ISSUED, hold exists, canary seed + commitment, lease epoch 1) | | AUTHORIZED | record auth ref, token id, canary commit |
| AUTHORIZING | hub timeout | retry same idempotency key; never create a second order | AUTHORIZING | after 5 min total: cancel op, void, REFUSED/FAILED_INFRA |
| AUTHORIZED | driver boots Cell step 1 and sidecar answers first call | | STARTING -> RUNNING | `started_ack` to hub: token BOUND -> STARTED; hub records canary placement commitment hash. Until STARTED, the token can be re-bound to the same run_id and hold, so a retry does not pay twice [PR-F3]. Hub reaper voids any auth with no STARTED within 10 min |
| RUNNING | step finishes | outputs validated | CHECKPOINTING -> RUNNING | write signed checkpoint; anchor head hash to hub (also lease heartbeat) |
| RUNNING | any cap hit (wall, tokens, USD, rpm, retries, step or run) | first cap wins; precedence only for labeling | WINDING_DOWN | stop model proxy except reserved slice; cause recorded |
| WINDING_DOWN or all steps done | | | ASSEMBLING | Result Guard; for budget stop, **supervisor deterministically assembles a schema-valid partial result from validated step outputs, no model call** [PR-F9]; optional model summary only from a reserve slice enforced by the proxy |
| ASSEMBLING | result accepted by Result Guard and platform check library (throwaway no-net cell) | | DRAINING | platform check verdict stored (requester-attested) |
| DRAINING | all detectors and async Q-proposal scans drained (pre-capture barrier) | max 60 s | CLEANING | If a detector fires here the incident machine (5.2) takes over before any settlement [DEF-F8] |
| CLEANING | destroy Cell, wipe stage and tmpfs, destroy per-run keys, mark CLEANED | on failure: retry; if still failing: record CLEAN_FAILED and tell hub to void instead of capture [PR-F1] | RESULT_READY | `result_ready{result_hash, outcome, checks, suspend_count, billable}` to hub. Result lives in R only |
| RESULT_READY | hub settlement terminal | | DONE | wipe R after retention |

Reorder vs v2 6.2 step 9: **cleanup precedes capture**; capture and payout never occur while live data exists [PR-F1].

### 2.4 Workflow graph and checkpoints (this replaces the fixed plan/work/return phases) [PL-F6, PR-F9, CON-F12, TASK-F6]

The manifest `phases:` block becomes `workflow:`: nodes + edges. Node types: `step` (agent or tool step with declared tools, memory rights, data capability yes/no), `branch` (typed predicate over the previous output), `loop` (bounded: `max_iter`, per-iteration cap), `verify` (platform check library gate), `human` (typed gate, 1.7), `milestone` (marks a unit of accepted work and its fee share). Every node has `{max_tokens, max_wall_s, max_retries, max_usd}`. Checks:
- Publish-time validation and the Certifier reject workflows with unbounded loops or with `worst_case_cost > declared cap`, and reject workflows whose gate count exceeds an approval-budget ceiling [HUM-F10].
- The price is fixed **per accepted milestone**, not per attempt, so a retry loop cannot burn requester budget for the author's benefit [PL-F6]. Requester budget is capped per step and per run; the approval card shows them.
- Each step is its own Cell start (fresh Cell, never reused). Only steps declared `data: read` get the data capability (their own attenuated Biscuit); other steps get no mount and a Biscuit without read. Phase state is owned by the sidecar, so a pack cannot claim a phase [PR-F6, CON-F2].
- **Checkpoint** (written after each node): `{run_id, pack_digest, engine_major, step_id, iter, state_hash, artifact_hashes, prev_cp_hash, seq, budget_spent, ts_mono}` signed by the supervisor. Control state is typed JSON; files are content-addressed in R and remounted read-only into the next fresh Cell. A hand-off between nodes is a typed, size-capped, labelled output marked untrusted [PR-F6].
- Budgets are cumulative across resumes (persisted in the checkpoint) so crash-resume loops cannot yield free extra work [PL-F6].

### 2.5 Lease, resume, crash handling [PL-F6, ID-F8, TASK-F6, PL-F11]

- Token states (hub): `ISSUED -> BOUND(run_id) -> STARTED -> SETTLED | VOIDED`. The token starts the run only; at STARTED the hub issues a **run lease** `{run_id, epoch, lease_seq, last_cp_hash, expires_at}` bound to the requester device key. One live lease per run_id (CAS on epoch). Renewals ride on checkpoint anchors and a 60 s best-effort heartbeat. Hub-side lease TTL is 10 min; silence of 30 min marks `STALE_LEASE` (no money action). Money actions occur only at hard deadlines (3.5).
- Hub unreachable during RUNNING: continue to the next checkpoint under the cached lease (`lease_grace` 30 min); then SUSPENDED_INFRA (freeze, keep state, retry). Never kill because the hub is unreachable [PL-F1, ID-F3].
- **Resume** (state RESUMING) is allowed only from the last checkpoint the hub knows (or local ahead by at most one un-anchored checkpoint), at most 3 resumes per run, with this checklist run before any step: (1) pack not revoked, revocation list fresh, digest and engine major equal; (2) staged `snapshot_hash` equal, or user approves a re-stage; (3) hub issues a fresh lease with epoch+1; Biscuits re-minted locally, never persisted; (4) hub GETs the authorization: status, honor time left vs remaining work, else AWAIT_REAUTH; (5) quarantine, strike and denylist state re-read; (6) any source record shredded or invalidated since the checkpoint invalidates the dependent steps, which re-run or the run is discarded; (7) model pin still valid; (8) resume of a run from a replicated journal on a **second device is forbidden** in v1: the other device may view or cancel only [TASK-F7]. Terminal outcomes (kill, quarantine, revoke, policy deny) destroy R; resumable outcomes are crash, budget soft-stop, human wait, detector pause [TASK-F6].
- A step interrupted mid-way is re-executed from its input checkpoint; steps must be idempotent or side-effect free (results are inert artifacts; the pack never writes outside `/out`) [TASK-F5].
- Model context is never carried across steps: each step starts a fresh context from a capped hand-off summary classed as Q-tier derived content [TASK-F6].

### 2.6 Data path and staging [PR-F5, PR-F6, CON-F2, MEM-F2, HUM-F2, TASK-F11]

One data path per record type:
- **Records** (memories) are served **only** through `memory.search` over the closed staged set. The sidecar holds the sealed slice in memory (decrypted with the per-run key); there is no `/in` mount of records. Slot caps, accounting, canaries and D4 apply to every read [CON-F2].
- **Artifact files** (tier 1 packs): `materialize(selector)` through the Broker, accounted, written to a per-step tmpfs sized separately from the memory cgroup, wiped at step end. A tier 0 pack gets no mount at all. In PLAN-style steps `cat /in` fails (no mount) and `memory.search` is denied; this is a conformance test [PR-F6].
- The byte-exact preview is exact for the closed staged set and artifacts. The semantic filter is applied once at staging, so the card lists the resulting set; it never claims byte-exactness for a live query path [MEM-F2, HUM-F2].
- Residue: per-run keys are held outside the VM and destroyed at CLEANED or on shred; quarantine keeps hashes and a metadata diff by default and plaintext only with user opt-in; the doc states that crypto-shred does not cover a copy not encrypted under a shreddable key [PR-F5].
- Events during a run: a `forget`, `invalidate` or reclassify on a record in the staged set raises AWAIT_PAUSE_REVIEW; the default for sensitivity high or secret is stop with a partial result. Q proposals carry `base_versions` and are flagged stale on promotion if a base record was invalidated or shredded [PR-F5].

### 2.7 Wait handling

See 1.7. The clarification op is a typed `NEEDS_INPUT` step outcome plus a workflow gate; the brief at hire time (task-brief form on the card) reduces ambiguity [PR-F7, TASK-F3]. Timeout of D6 is UNCONFIRMED_PAUSE, never a kill or a strike [PR-F7, DEF-F3, HUM-F5].

### 2.8 Model API failure semantics [PR-F8]

- The Model Proxy owns retries: bounded, jittered exponential backoff, honours `Retry-After`, idempotent per `call_id`. The pack sees only `UPSTREAM_UNAVAILABLE | RATE_LIMITED | MODEL_GONE` after retries are exhausted, never raw provider text.
- STALLED is a run sub-state: run clock and wall budget pause; separate stall cap (default 20 min); then the requester gets wait, suspend-and-checkpoint, or abort.
- Model-not-found, deprecated, 5xx, or a response `model` field different from the id pinned in the run token: INFRA_FAULT, run marked uncertified if continued. D11 is restricted to pack-originated deviations.
- Budget accounting: reserve max tokens up front per attempt; reconcile from `usage` after; timed-out calls counted conservatively; infra retries are never charged to the requester's cap.
- Per-run token-bucket share of the key's RPM, with a reserved slice for the local agent and extractor; admission warns when concurrent runs would exceed the key limit. Chaos fixture (429, 5xx, timeout, model-not-found) is part of the Certifier and Phase-4 tests.
- Who pays tokens in Pull: the requester's own Nebius key, held only by the requester's sidecar; the author fee is independent of token spend; the card shows token and USD cap next to the price cap [PR-F9].

### 2.9 Liveness, sleep/wake, resources [PR-F2, PR-F12]

- Lease chain: supervisor grants the sidecar a lease (10-15 s, renewed over a local socket). Sidecar serves the Cell only while the lease is valid. A watchdog freezes the Cell when it lapses, kills it after a 60 s grace, and drops keys. Sidecar and Cell die with the supervisor (`PR_SET_PDEATHSIG` or cgroup), and an orphan reaper runs at supervisor start.
- Sleep/wake: on wake do the revalidation in 1.4. TLS/Nebius sockets that died are retryable faults. A lapse is INFRA_FAULT, never D12.
- Disk, tmpfs, OOM, ENOSPC are RESOURCE_EXHAUSTED. Preflight checks stage size and free disk; tmpfs is sized separately from the memory limit. No strike, no author penalty, no auto-retry.
- Audit append failure: freeze run; resume only when the append works; otherwise FAILED_INFRA.
- Ladder atomicity and crash safety are in 5.2 and 5.8.

### 2.10 Approval, phone protocol, authority separation [PR-F11, HUM-F3, HUM-F7, TASK-F12, CON-F10, HO-F2]

- Approval is a bounded grant: `{max_runs=1 default, total_budget, expiry, lens_hash, capset_hash}`. Standing approvals are opt-in, with TTL, run-count cap, and the delta trigger of 2.3. Concurrent runs under one approval count against the aggregate budget and a concurrency limit. Each run gets its own Cell, Sidecar, canary set, Biscuit and proxy sub-budget. Pull approval never covers Hosted.
- **Taint rule**: once the local agent session has read pack output, listing free text, or other foreign content, `hire`, `accept`, `reject`, `capture`, `void`, `reauthorize` are not callable by it. The next hire needs a fresh human card. Escrow tools are not in the Reader session's tool list; they are exposed only to the supervisor and hub. Accept is a human click or a deterministic rule (platform checks + timeout auto-accept); never an agent tool [PR-F11, TASK-F12, CON-F10].
- The agent is a proposer. It sees only enums and hub-computed fields (LCB, tier, price, capability union, attestation status), never card free text; free text appears to the human only in an "author says, unverified" pane. The lens is a policy object: user default and maximum; the agent may propose subsets only; any widening shows a red "widened vs your default" diff [HUM-F7].
- **Phone protocol**: the desktop creates the card; the phone can only decide existing cards. Decision = phone-key signature over `(card_hash, run_id, decision, nonce, expires_at)`, expiry 2-5 min, nonce single-use and stored by the supervisor. The supervisor is the sole state authority; first valid decision wins; later or conflicting ones return `already_decided`; an approve after KILLED/expiry is dropped and logged. Each approval needs WebAuthn/biometric user verification (production path). The phone shows a deterministic summary + `card_hash`; byte-level lens preview only on desktop; push payloads content-free. Kill is desktop-local and needs no relay; phone cancel is idempotent and shows "cancel requested" until the supervisor confirms. Max 2 paired phones; desktop or recovery code can revoke one. Pairing is out of band (QR with key fingerprint), never through the hub [ID-F6]. Hackathon scope: nonce/expiry, first-wins, local kill; the rest is the documented production path [HUM-F3].

### 2.11 Result delivery, accept, apply [PR-F4, PAY-F2, HUM-F6, TASK-F1, TASK-F2, TASK-F5]

- **Result kinds**: closed registry (answer, report, patch, file_set, table, proposal). Each kind has a platform envelope schema and guard. A pack `result_schema` can only narrow it (checked as subschema at publish and certify, ignored if wider at runtime). Hard global size cap by kind; TaskSpec (requester-set) supplies the kind, `max_bytes`, required checks. Effective checks = platform checks + TaskSpec checks + pack extras; extras can only add [TASK-F1].
- **Render**: static view, CSP `default-src 'none'`, no remote images/fonts/link previews, no HTML passthrough; URLs shown as plain text with domain, unless present verbatim in the task inputs or an allowlist; a result outbound reference is a deterministic strike (D15), shown on the Accept card [TASK-F2].
- **Acceptance checks** are a platform-owned library; the author picks from it and cannot add code. They run in a throwaway no-network Cell at ASSEMBLING; the requester cannot weaken them. Their verdict is requester-attested (the hub never sees result bytes, only the hash) [PR-F4, PAY-F2].
- **Apply is not Accept.** Accept triggers capture and means nothing about the working tree. Patches never go to the live tree: they materialise in a throwaway worktree with a deterministic diff summary; executable/config paths (git hooks, `.git/*`, CI, package scripts, lockfiles, dotfiles, build scripts, symlinks, binaries) are hard-flagged and need per-file approval; install and hooks are disabled during apply (`core.hooksPath=/dev/null`, `--ignore-scripts`); base_hash recorded at TaskSpec, rejected on drift; an undo journal is kept. v1 scope: results are inert artifacts and the requester's local agent applies under its own policy; `patch` is an opt-in later capability [HUM-F6, TASK-F5].
- **ACCEPT_PENDING** is hub-side with `accept_deadline = min(48h, honor_left - 6h)` stamped by the hub at RESULT_READY. Requester choices: Accept, Reject(reason code from a fixed list, with check report), Dispute, or silence. Silence at the deadline = auto-accept when the platform checks passed (requester-attested verdict), else outcome fee goes to arbitration default (3.4) [PR-F4, PAY-F2].
- Q proposals from the run are only offered after RESULT_READY and never auto-promoted (section 7).

### 2.12 Crash recovery (supervisor boot reconciler) [PR-F1, PR-F12]

Run once at supervisor start, before accepting new work:
1. List containers/VMs carrying the bridge label; kill any whose run is not RUNNING in the WAL; wipe any stage dir with no live run.
2. Re-drive unfinished `outbox` intents (idempotent).
3. Per WAL state:

| WAL state at crash | Action |
|---|---|
| CREATED, PREFLIGHT, STAGING, CARD_PENDING, APPROVED | wipe stage; mark EXPIRED_APPROVAL; no hold exists |
| AUTHORIZING | ask hub for `run_id` status; if ISSUED or BOUND with no STARTED, re-bind or void and mark FAILED_RESTART; offer re-hire that **supersedes** the old run_id so the user is never charged twice |
| AUTHORIZED, STARTING | void (hub), wipe stage, FAILED_RESTART |
| RUNNING, STALLED, SUSPENDED_INFRA, GATE_WAIT, PAUSED_DEFENSE | if a valid checkpoint exists and resumes < 3: offer RESUMING with the 2.5 checklist (user confirms; staged data needs the per-run key still in keystore); otherwise ABORT and void; mark FAILED_RESTART. Never auto-resume without checklist |
| WINDING_DOWN, ASSEMBLING, DRAINING | restart assembling from last checkpoint if keys exist, else FAILED_RESTART |
| CLEANING | finish cleanup; if cleanup cannot finish, tell hub to void; never capture over live data |
| RESULT_READY | nothing local; ask hub for settlement state; resume ACCEPT_PENDING UI |
| any incident INTENT_LOGGED | continue the ladder (5.8) |

4. Hub-side reaper (periodic, and at hub boot): void any authorization with no STARTED within 10 min; void any run with no heartbeat past `run_deadline + grace`; list open PayPal orders against `run_id`s and void orphans [PR-F3]. Billable stats and holdback are driven by receipts only (STARTED + at least one metered call), never by tokens [PR-F3].

### 2.13 Timeout summary (Pull)

| Timer | Default | On expiry |
|---|---|---|
| Approval card | 15 min | EXPIRED_APPROVAL |
| AUTHORIZING total | 5 min | cancel, void |
| Auth to STARTED | 10 min (hub reaper) | void |
| Sidecar lease | 10-15 s | freeze, kill after 60 s (INFRA) |
| Hub lease TTL / silence | 10 min / 30 min | SUSPENDED_INFRA at next checkpoint / STALE_LEASE |
| Gate / pause review | 60 / 30 min | per 1.7 |
| Total wait cap | 3 h | ABORTED_CLEAN |
| Stall cap | 20 min | user choice, then abort |
| Run max | declared, hard cap OD-6 (default 24 h v1) | WINDING_DOWN |
| Accept deadline | min(48h, honor_left - 6h) | auto rule |
| Authorization segment | 66 h (3 days minus 6 h margin) | AWAIT_REAUTH or segment close |

---

## 3. (b) Payment hold and settlement (real PayPal semantics)

### 3.1 What PayPal gives us (and what we must not assume)

Verified: 29-day hold; capture only guaranteed inside a 3-day honor period; capture "subject to risk and money availability" (so DECLINED after work is possible); reauthorization allowed within the 29 days, new authorization id, restarts honor; void exists. UNVERIFIED (check Payments v2 reference before coding): whether reauthorize is allowed during the honor period (`research/09` audit says no; treat REAUTHORIZATION_NOT_ALLOWED as an expected, handled state), `final_capture` semantics for multiple captures, error codes for capture-after-void and void-after-capture, `PayPal-Request-Id` retention, refund window for a capture, dispute window (180 days per `research/09`), Payouts by PayPal payer id, whether a hackathon account can use multiparty/`platform_fees`.

Consequences designed in: hold is never treated as a guarantee [PAY-F3]; a non-refundable floor is captured early so a failed outcome capture cannot strand all pay [PAY-F3, PAY-F2]; per-segment authorizations stay inside the honor period; reauthorization is a fallback with the new id linked to the old in the ledger.

### 3.2 Quote and fee components

Quote (hub-signed, hub-time expiry): `{run_id, pack digest, capset_hash, listing_version, floor_fee, outcome_fees[milestone], gateway_cost_cap (Hosted only), host_fee (Hosted only), cap = sum, honor segment plan}`. `cap` is bound into the approval hash, the run token and the AUTHORIZE amount, so a price rise after approval can never exceed what the requester approved [PL-F5]. Listing price changes are listing updates (not new digests) and need re-approval only if the new price exceeds the card's cap.
- `floor_fee`: non-refundable once the run is billable and delivered (covers platform + author's minimum). Doubles as the wash-trading minimum.
- `outcome_fee`: per accepted milestone.
- Pull has no compute line (requester's own Nebius key). Hosted adds `gateway_cost_cap` and `host_fee`.
- State plainly: **Pull has no fair exchange** (result lands on the requester's disk before the payment decision); mitigations are the floor, the reject-rate score, caps for new requesters, and the dispute path [PR-F4, PAY-F2]. Payment gating is cooperative; the token gates certified-channel use (revocation list, ranking credit, receipts, refund flow), not file execution; it is described as settlement, not metering or DRM [PAY-F12, CON-F7, ID-F8].

### 3.3 Ledger state machine (one row per run; hub; CAS on `rev`)

States: `NONE -> ORDER_CREATED -> AUTHORIZED -> FLOOR_CAPTURING -> FLOOR_CAPTURED -> OUTCOME_CAPTURING -> CAPTURED(final) -> RESERVED -> PAYOUT_SCHEDULED -> PAID`
Side branches: `REAUTH_PENDING`, `AUTH_LAPSED`, `CAPTURE_DECLINED`, `VOID_PENDING -> VOIDED`, `DISPUTE_HOLD`, `REFUND_PENDING -> REFUNDED`, `CHARGEBACK`, `FROZEN`.

| From | Event (source) | Guard (CAS precondition) | To | Outbox action (key) |
|---|---|---|---|---|
| NONE | `create_run` (requester) | run_id new | ORDER_CREATED | PayPal create order (`run_id:create:0`) |
| ORDER_CREATED | payer approval + authorize | token ISSUED | AUTHORIZED | PayPal authorize; store `auth_id`, `t0`; honor_limit = t0 + 72h |
| AUTHORIZED | `started_ack` | token BOUND | AUTHORIZED (token STARTED) | none |
| AUTHORIZED | `result_ready` (outcome COMPLETE/PARTIAL, billable) | not terminal, honor_left > margin | FLOOR_CAPTURING | capture `floor_fee`, `final_capture=false` (`run_id:cap_floor:0`) |
| FLOOR_CAPTURING | capture COMPLETED (webhook or GET) | status COMPLETED, not PENDING | FLOOR_CAPTURED | record capture id, net |
| FLOOR_CAPTURING | PENDING | | stay; poll | |
| FLOOR_CAPTURING | DECLINED | | CAPTURE_DECLINED | try reauthorize if allowed (outbox); else notify author and requester; no run re-dispatch; requester risk score down |
| FLOOR_CAPTURED | accept / auto-accept at deadline / milestone accepted | no DISPUTE_HOLD, no KILLED | OUTCOME_CAPTURING | capture outcome fee, `final_capture=true` on last (`run_id:cap_out:n`) |
| FLOOR_CAPTURED | reject w/ check_failed within reject-rate cap | | CAPTURED (floor only) + void remainder | void remainder (`run_id:void:0`) |
| any pre-capture | `cancel` / terminal fault | per 3.4 | VOID_PENDING -> VOIDED or partial capture then VOID_PENDING | void remainder |
| AUTHORIZED / FLOOR_CAPTURED | `incident_claim` (class R) | not CAPTURED final | DISPUTE_HOLD | floor captured (if not yet) into **hub balance, no payout**; outcome portion: keep authorization until adjudication deadline |
| CAPTURED | `incident_claim` or dispute | | DISPUTE_HOLD | payout frozen; refund path ready |
| DISPUTE_HOLD | adjudication result | see 5.5 | CAPTURED / REFUND_PENDING / VOID_PENDING | per table |
| AUTHORIZED | honor_left < 6 h and work not done | | REAUTH_PENDING | AWAIT_REAUTH (1.7); reauthorize only after the honor period (UNVERIFIED rule), link new `auth_id` to the old |
| REAUTH_PENDING | reauth fails (funds moved, not allowed) | | AUTH_LAPSED | capture whatever is capturable (floor), end the run PARTIAL; offer invoice/credit for the rest |
| CAPTURED | holdback elapsed, dispute window clear | | RESERVED -> PAYOUT_SCHEDULED | see 3.7 |
| CAPTURED / RESERVED | chargeback webhook | | CHARGEBACK | net against future payouts and reserve; evidence pack |

Mutual exclusion: accept, kill, cancel, void and capture are all transitions out of the same row; the first to commit wins. A capture is rejected in KILLED/VOIDED; a void is rejected after CAPTURED (final); kill after capture -> DISPUTE_HOLD, refund of the capture from the held balance, payout frozen [PAY-F4, HO-F6, TASK-F10]. Deterministic ids: `invoice_id = run_id:seq`. A periodic reconciler compares ledger rows to `GET authorization/captures` [PAY-F4].

### 3.4 Outcome-to-money table (master)

| Outcome | Floor | Outcome fee | Remainder / hold | Payout | Strike |
|---|---|---|---|---|---|
| COMPLETE, accepted or auto-accepted | capture | capture (final) | none | schedule after reserve | none |
| COMPLETE, silent past deadline, platform checks passed | capture | auto-capture | none | schedule | none |
| COMPLETE, rejected `check_failed` (supervisor report) within requester reject-rate cap | capture | void | void | floor only | pack quality strike (not security) |
| COMPLETE, rejected `check_failed` above cap, or rejected without a failing check | capture | to arbitration: default if no resolution in 72h = capture | hold until resolved | per result | requester reject-rate++ |
| PARTIAL_BUDGET, accepted partial | capture if >=1 milestone passed | prorated milestone fees | void rest | schedule | none |
| PARTIAL_BUDGET, declined | capture only if >=1 milestone passed checks | void | void rest | | none |
| FAILED_PACK | void | void | void | none | quality strike |
| FAILED_INFRA / RESOURCE_EXHAUSTED | void | accepted milestones only | void rest | | none |
| CANCELLED / ABORTED_CLEAN / UNCONFIRMED_PAUSE | capture if billable (STARTED + >=1 metered call) | accepted milestones | void rest | | none; requester abort rate++ |
| DATA_INDUCED kill | capture | void | void | floor | none |
| KILLED_INCIDENT (class R) before RESULT_READY | capture into DISPUTE_HOLD | void | void | frozen until adjudication | none until C/N evidence |
| KILLED_INCIDENT after RESULT_READY or after capture | existing | dispute, never VOID | hold | frozen | none until C/N |
| FAILED_RESTART | void | void | void | none | none; re-hire supersedes, no second charge |
| EXPIRED_APPROVAL | no hold exists | | | | |

Rationale: a requester cannot get free full work by fabricating an incident: they pay the floor at minimum, can be refunded only when a claim is reproduced (class C or N), and each unreproduced claim costs reputation [PAY-F1, PL-F2, DEF-F4, CERT-F1, ID-F4]. "Pull cannot be fully protected; the goal is to cap the loss" is stated in the guarantees text [PAY-F1].

### 3.5 Honor period and long runs [PAY-F3, PL-F6, ID-F8, PR-F4, PR-F7]

- One authorization **segment** ends at `t0 + 66 h` (3 days minus 6 h margin). `run_max + min_accept_window(4 h)` must be <= segment length; v1 caps `run_max` at 24 h (OD-6). Longer tasks are split into milestone segments, each a **new order and authorization requiring a human step** (a pause at AWAIT_REAUTH), because unattended re-authorization of a payer order is not assumed available (UNVERIFIED).
- Before each Hosted metering interval and before RESULT_READY the hub GETs the authorization; if not CREATED/PARTIALLY_CAPTURED or honor nearly over, the run pauses. Hosted blocks are capped at 2 h each (research-v2/08).
- Accept deadline stamped by the hub as `min(48 h, honor_left - 6 h)`. Pause waits are bounded by the same inequality (1.7).
- New or low-trust requesters: lower caps, prepaid credit or deposit.

### 3.6 Idempotency, outbox, reconciler [PAY-F4, PAY-F5]

Hub runs a startup reconciler and a periodic scheduler: (1) re-drive outbox intents; (2) for each row not terminal, GET the PayPal resource and move state; (3) for rows past `release_at` or stuck in SUBMITTED, reconcile payouts by GET; (4) compare open orders to `run_id`s and void orphans. Rule: never rely on a voidable-but-stale hold for state that must be correct. Exit test (phase 12): kill the hub mid-flow and restart -> exactly one payout; kill-vs-accept race -> exactly one wins; lost capture response -> retry produces one capture [PAY-F4, PAY-F5].

### 3.7 Payout machine and payee binding [PAY-F5, PAY-F8, PL-F3]

Payout row per (run_id, recipient): `SCHEDULED(release_at) -> SUBMITTED -> SUCCESS | FAILED | UNCLAIMED -> RETRY`, plus `FROZEN`.
- Create a payout only after capture status COMPLETED (webhook or GET). `sender_batch_id = H(run_id, recipient)`; a duplicate-batch response is treated as success after fetching batch status (dedupe window UNVERIFIED).
- "Paid" receipt and author notification only on SUCCESS; until then show "payout pending".
- Solvency check before scheduling: `balance >= pending payouts + dispute reserve`.
- **Payee binding**: onboard via Log in with PayPal and store the verified payer id (mechanics UNVERIFIED); pay by id, never raw email or phone, which removes UNCLAIMED. A signed binding record `(publisher_id, payer_id)` goes in the hub log. A destination change needs a signature from the old key (or recovery key), step-up auth, notifies the old destination, starts a 7-day cooldown that freezes payouts and holdback releases, and payouts are blocked while any version of the author is under distrust [PL-F3, PAY-F8].
- Single currency (USD), payee bears conversion. Compliance screening is a production gate; which obligations fall on hub vs PayPal is UNVERIFIED. Demo payees are seeded, pre-verified sandbox accounts.

### 3.8 Reserve, disputes, retraction [PAY-F6, PAY-F7, PAY-F10]

- Rolling reserve: new authors get a short holdback (proposal 14 d) on about 50% of payouts and the remainder held to day 180; established authors (dispute rate, accepted volume) a smaller reserve. Percentages are proposals (OD-8). Net disputes against future payouts; platform fee set above PayPal fee plus expected dispute loss. Seller protection for intangible AI services is UNVERIFIED.
- Dispute evidence pack: requester-signed quote and Accept bound to payer id, result hash, hub payment receipt, log inclusion proof; host-signed logs labelled self-attested.
- **Retraction**: a signed retraction log entry (compensating, no rewrite) referencing original receipts; ranking excludes retracted completions; versions with confirmed-malicious incidents are marked "tainted" on every score row. Slash = forfeit reserve + unreleased payouts; refunds to affected requesters come from the reserve first, then a hub fund, capped at what the requester paid. Money recovery is bounded by the reserve and the 180-day window; data already exposed cannot be recalled (stated in guarantees). Author bond: production item only.
- Completions count toward ranking only after holdback, reverse on refund/chargeback, are weighted by payer age/spend/diversity, zero-weighted for payer-author links, per-payer capped; free packs rank on a separate Certifier-only board; paid signals can only demote or break ties, never promote past the Certifier LCB (the remainder of anti-wash design lives in the ranking doc) [PAY-F10, CERT-F7].
- Demo: on-screen label "demo holdback 0 s, production N days + reserve"; section 6.2 payout wording becomes "after holdback and reserve release" [PAY-F6].

### 3.9 Scope [PAY-F9]

Demo uses sandbox funds with a "test money" badge. No real-money flow ships without counsel review (money transmission, tax on digital services, refunds, sanctions). Preferred production design is multiparty with the author as payee and delayed disbursement, so the hub never holds author funds; fallback is a licensed payments partner. All UNVERIFIED until PayPal's platform/marketplace documentation is cited. Pitch line: "production payments need partner approval and legal review."

### 3.10 Token role and receipts [PAY-F11, PAY-F12, DEF-F6]

Two-part receipt: hub-signed payment receipt (auth id hash, capture ids, amounts, run-token nonce, ledger state) and a supervisor-signed run summary labelled `attestor=requester|host`, reporting bucketed or tiered cost, not exact. Receipts are hub-only; authors receive only batched aggregates (k >= 20 distinct requesters, delayed, no per-run rows, no requester ids). Ratings use a hub-issued single-use token bound to the capture id.

### 3.11 Crash recovery

Hub crash between any two ledger transitions: rows replay from the outbox (`intent` is durable before the PayPal call). Crash after capture, before payout intent: the reconciler finds CAPTURED rows with no payout row and creates it. Crash during payout submit: GET by `sender_batch_id` before retry.

---

## 4. (c) Hosted run

Hosted is **hub-authoritative** because the host is untrusted and the requester should not trust a host-signed meter. The Pull machine's checkpoint/lease ideas apply, but state lives on the hub.

### 4.1 Records

Hub task row: `task_id (= run_id), requester_key, host_key_id, pack_digest, capset_hash, hosted_approval_hash, quote_id, state, epoch, seq, canary/probe flags, gateway_token_id, ledger_state, deadlines{dispatch, run_max, result_ttl, accept}`. Requester keeps a **disclosed-to ledger** per packet (`packet_hash -> host_key_id`).

### 4.2 States

`QUOTED -> APPROVED -> AUTHORIZED -> DISPATCHED -> RUNNING -> RESULT_COMMITTED -> RESULT_ACKED -> ACCEPT_PENDING -> SETTLING -> DONE`
Terminal/side: `HOST_LOST`, `TIMED_OUT`, `CANCELLED`, `VOIDED`, `REJECTED_CHECKS`, `DISPUTED`, `HOST_REFUSED`, `STALE_QUOTE`.

### 4.3 Transitions

| From | Event | Guard | To | Effects |
|---|---|---|---|---|
| (none) | requester asks quote | pack digest + Hosted mode certified for (digest, model, mode) [HO-F12] | QUOTED | hub co-signed quote: `task_id, requester key, host key id, pack digest, packet hash or size bucket with max bytes, model, unit price, gateway_cost_cap, host_fee, outcome fees, cap, hub-time expiry, nonce` |
| QUOTED | Disclosure Compiler builds packet; user approves **Hosted approval object** | `(packet SHA-256, host key id, quote id, cap, expiry)` signed on the user device, single use; never a standing approval; deterministic scanner clean (8) | APPROVED | encryptor refuses to run unless packet hash and host key match the approval |
| APPROVED | hub AUTHORIZE | one live task per task_id (idempotency) | AUTHORIZED | hub-signed run token proving AUTHORIZE |
| AUTHORIZED | requester sends envelope via relay | host verifies run token and envelope signature **before decrypting** | DISPATCHED | AAD = `(task id, quote id, host key id, packet hash, run token, seq, direction)`; duplicate task ids rejected; relay deletes ciphertext after TTL |
| DISPATCHED | host decrypts, signs `RUN_STARTED` | within dispatch deadline (10 min) | RUNNING | hub issues gateway token (4.5); heartbeats begin |
| RUNNING | signed monotonic heartbeat every T=30 s | | RUNNING | hub compares progress vs gateway usage |
| RUNNING | host posts signed result-hash commitment | | RESULT_COMMITTED | hub never re-dispatches a task that has a commitment |
| RESULT_COMMITTED | requester fetches ciphertext, checks hash against commitment, acks | within `result_ttl` (24 h) | RESULT_ACKED | requester runs the Result Guard and platform checks locally |
| RESULT_ACKED | result_ready from requester supervisor | | ACCEPT_PENDING | same accept deadline rule as Pull; floor capture as 3.3 |
| RUNNING | heartbeat miss x N (N=3 of T=30 s) or `run_max` | hub-observed | HOST_LOST or TIMED_OUT | revoke gateway token, void unspent hold, host strike; failover is OFF |
| any non-terminal | cancel (signed, epoch+seq) | | CANCELLED | revoke gateway token; hub refuses host receipt beyond hub-metered usage after lease expiry |

### 4.4 Host key, sender auth, replay [HO-F3, HO-F2, ID-F6, HO-F5, HO-F11]

- Say plainly: in Unsealed Hosted the host key authenticity is hub-trusted; a malicious hub can read the packet. Sealed takes the key only from an attestation the requester verifies itself.
- Host registers an X25519 encryption key signed by its Ed25519 identity key; the requester pins the identity key on first hire (TOFU), shows its fingerprint, and a change needs explicit re-approval and an alert. Host prekeys are signed, valid ~24 h, deleted after use.
- Requester signs the envelope; host checks signature, then checks the hold with the hub, then decrypts. No automatic failover: switching host needs a fresh approval and card; a retry to the same host may reuse the same ciphertext only within approval expiry.
- Ordering by per-task sequence numbers and hash-chained protocol events; seen-nonce sets; idempotent handlers; single-use gateway tokens; a result for task X cannot be accepted for task Y because AAD binds task id and packet hash.
- Hosted is never approved under a standing approval [HO-F2].

### 4.5 Gateway and metering [HO-F1, ID-F12, CON-F4, HO-F4]

- **No Nebius credential ever reaches a host.** The hub runs a model gateway on the hub's own account; the sidecar presents a per-task signed bearer (Biscuit/JWT) bound to quote id, model allowlist, max tokens, USD cap, RPM, parallelism and expiry; the hub holds the only key and meters tokens itself, revoking at void/kill/timeout/capture. Per-host spend ceiling and rate limit. Certifier/GEPA use a separate Nebius account so their load cannot starve live runs.
- Token cost is an explicit quote line with a hard cap inside the AUTHORIZE amount, so the hub never fronts unbounded cost. Hosted B2 wording narrows to "hub never gets vault content **beyond the declared packet**; the gateway sees Hosted prompts". Whether Nebius ToS allows passing inference through to third parties is unread: UNVERIFIED blocker before building the gateway; fallback is requester-supplied key [CON-F4].
- Receipt tokens and model id come from the gateway usage log; the hub checks the response `model` against the pack's certified model; mismatch voids the run and flags the host. Hosted time is billed from hub-observed signed start/heartbeat/finish; per-task fixed quotes, not hourly buckets. Probes and sleep are not billable.
- For Sealed: PCR-gated key release via KMS; Nebius metering in that path UNVERIFIED.

### 4.6 Liveness and failure [HO-F7]

Hub reaper moves RUNNING to HOST_LOST after N missed heartbeats or hard wall clock; in order: revoke gateway token, void unspent hold, host strike, freeze host payout if reputation is low. Tick-only progress without gateway usage, or usage without progress, counts as stall. Hold lifetime >= `run_max + accept window` or the hub re-authorizes/fails explicitly; never lets a hold lapse silently. Optional phase checkpoints: the host returns signed encrypted per-phase partial results the hub stores as ciphertext. Failover default OFF; if the requester opts in, the compiler warns "disclosed to host A and host B" and the ledger records it. State: packet exposure to the host is irreversible, deletion is host-attested, only Sealed changes this. Acceptance tests: host silent after accept, slow-loris host, host dies mid-run: each voids the hold and kills the key.

### 4.7 Settlement split [HO-F6, HO-F4, HO-F9]

| Fault | Host fee + gateway cost | Author fee | Strikes |
|---|---|---|---|
| HOST_FAULT (lost, wrong model, filler failing checks, abort after decrypt) | void; hub bears gateway spend (bounded by cap, withheld from host's holdback) | void | host strike; (host, pack) pair downgraded |
| AUTHOR_FAULT (garbage the pack produced on an honest host) | capture | void | author quality strike |
| REQUESTER_FAULT (cancel, no ack, silent) | capture pro-rata to hub-observed usage | per accepted milestone | none |
| INDETERMINATE | split 50/50 on host fee, author fee void (OD-8) | | none |
| Accepted | capture all | capture | none |

Result free-riding: result is E2E to the requester, so the hub cannot hold bytes back; the floor captured at RESULT_COMMITTED and auto-capture on silence are the levers, same residual as Pull. Optional later hardening: hub-held release key at accept/deadline (breaks content-free hub if hub holds ciphertext; not adopted). Chargeback: risk-based holdback plus host stake, not flat 180 days.

### 4.8 Packet safety [HO-F10]

Default deny: only user-confirmed sensitivity `low` (or explicit per-item pick); never secret/high/untagged/Q/pack-derived items. A deterministic scanner (secret regexes, Presidio, entropy, vault identifier list) runs over the **final packet bytes** and blocks on hits. Tokenization uses fresh random tokens per run. Detokenized output is marked sensitive and cannot enter outbound packets or tool args without a new Disclosure Compiler pass. No digest-batched approvals for Hosted.

### 4.9 Probes [HO-F8]

Spot checks measure result quality, receipt honesty and billing honesty; they give **no confidentiality assurance** (stated). Probes use sponsor/opt-in requesters with real payment instruments and history, realistic synthetic vaults through the same compiler, randomized size/timing, same relay and approval path. The compiler also folds known-answer sub-tasks and per-host honeytokens into real packets, shown as decoys. Probe budget is funded by the hub/sponsor and is part of the host fee schedule. Residual: a host that copies packets without using them is undetectable.

### 4.10 Attestation limits and roles [HO-F9, HO-F12, HUM-F11]

Host incident reports void that run and downgrade the (host, pack) pair only; global revocation, payout freezes elsewhere and author reputation require class C; host-signed evidence is tagged `host-claimed`; hosts with abnormal incident rates are flagged. Hosted memory is a read-only packet snapshot behind the same `memory.search` interface; certification is per (digest, model, mode); the Pull LCB is shown on a Hosted listing only if a Hosted-mode certified run exists. Pack distribution: registry digest-pinned, per-host license for non-open tiers; host identity cost or stake (Sybil). Role matrix: requester approves packets; host approves an incoming job class under a tight policy and sees a result preview before return (or returns only schema-checked fields); author approves publish and improvement candidates with score delta, H-plane diff, permission delta; payments where requester, author and host share a key or device fingerprint are rejected, and self-runs are labelled "own pack" and excluded from ranking.

### 4.11 Crash recovery

Hub: task rows replay; reaper (4.6). Requester supervisor: same WAL as Pull; a Hosted task in DISPATCHED or later is re-queried at boot by task_id; no automatic re-send (re-sending is re-disclosure). Host daemon: orphan reaper kills Cells whose task is not RUNNING on the hub.

---

## 5. (d) Incident, kill, rollback, appeal

### 5.1 Detector classes (re-specified) [DEF-F1, DEF-F2, CON-F1, DEF-F11, HUM-F9]

Canaries:
- Hub-issued per-run seed committed in the run token; the supervisor commits the placement hash before STARTED and the hub records it. The requester chooses neither value nor placement. At staging, a check rejects the run if a canary value (normalized/encoded) appears in the staged lens content (removes the planting path). Denied D1 reads never return a canary value (removes honest-echo). Canaries are minted in the sidecar, never written to U or the replicated journal; logs hold salted hashes; the extractor ignores pack scratch [MEM-F2, DEF-F1].
- Three classes: (a) outside-lens canaries reachable only via off-lens or enumerative queries or decoy paths an honest task has no reason to touch; never injected into in-lens search results; (b) edge decoys at the lens boundary (strike only); (c) broker-served bait tools, not placed in the model-visible tool list. A direct filesystem read of an out-of-lens decoy is observable only through the same enforcement as D3 (state it).

| Evidence | Detector | Local response | Money/author effect |
|---|---|---|---|
| Verbatim canary in a free-text result field | D2-soft | Result Guard rejects and redacts, strike, pause | none |
| Canary transformed (base64/hex/split/reordered), in a non-free-text field, a tool arg, a proxy request to an external sink, or alongside D5/D6/D7 | D2-hard | kill | class R claim, 5.4 |
| Egress attempt (connect, DNS, non-allowlisted endpoint, pack credential) | D5 (needs sensor: loopback decoy resolver/listener or LD_PRELOAD/seccomp-notify used for logging only, signed event) | kill | class R claim |
| Pack drift: D9 hashes **raw bytes** against the digest definition | D9 | kill | class R claim |
| Kernel/Tetragon, D10 | D10 (WSL2 UNVERIFIED) | kill, scoped after Cell init | class R claim |
| Persistence or endpoint change | D11 | kill; model/params deviation by honest runner defaults is baseline-aware | class R claim |
| Sidecar tamper with positive evidence | D12 | kill | class R claim |
| Overlap with lens (D6) | D6 | **log-only until FPR measured per task class**; thereafter: expected-overlap sinks (result free text, Nebius path) measured by quote budget (longest verbatim n-gram and fraction vs per-step `quote_budget` on the card); strict checks only on tool args, queries, proposals, URLs, typed non-free-text fields; return-step overlap is **not** a high-confidence rule (replaced by a taint-label subset check) | over budget: deny/redact and flag; encoding/canary hit on non-free-text: pause; kill only on canary, egress, or a second detector; timeout = UNCONFIRMED_PAUSE |
| D1 reads, D3, D4 | boundary | deny, strike; D4 excludes retry loops | none |
| D13, D14 | probabilistic | flag/advisory, never ranking | none |

Each detector carries a benign-behaviour baseline per (digest, model) from the Certifier (failed connects, params, file touches); kill only on deviation from baseline combined with lens data involved, else deny and log [DEF-F11]. D12/sensor events use a signed heartbeat with sequence numbers verified by the supervisor; loss is INFRA_FAULT. The guard model (D13) never receives private text and runs locally or is excluded from private steps. Evidence cards render only supervisor-generated fields; pack text is escaped, truncated and labelled as a quote [DEF-F12].

### 5.2 Incident machine (supervisor, durable) [DEF-F8, PR-F12, PL-F11]

One incident per run; states:
`DETECTED -> INTENT_LOGGED -> FROZEN -> EVIDENCE_SNAPSHOT -> KILLED -> LOCAL_DENYLISTED -> CLASSIFIED -> CLAIM_QUEUED -> CLAIM_FILED -> ADJUDICATING -> RESOLVED{UPHELD, REJECTED, INCONCLUSIVE, DATA_INDUCED} -> MEMORY_REVERTED -> APPEAL_OPEN -> CLOSED`

| Step | Rule |
|---|---|
| DETECTED | duplicate/concurrent detector events append as evidence; severity is monotonic (max wins) |
| INTENT_LOGGED | fsynced intent record `{run_id, severity, detector_id}` before any rung |
| FROZEN, EVIDENCE_SNAPSHOT, KILLED | order: freeze, then snapshot (diff, logs, hashes; plaintext copy only with opt-in; encrypted under vault keys, retention-limited), then kill (so evidence is not destroyed first) |
| LOCAL_DENYLISTED | written first among non-evidence steps; applies to **all runs of the digest on this machine** and their Q proposals; local denylist always wins over any hub signal |
| CLASSIFIED | attribution: does the triggering instruction (or a near-paraphrase) appear in a foreign lens or Q record that was in context? If so, DATA_INDUCED (record quarantined/demoted, hygiene warning, no author effect). Taint IDs and per-turn context logs support this [DEF-F10] |
| CLAIM_QUEUED -> CLAIM_FILED | outbox to hub: content-free signed claim (salted HMACs of canary values only, never lens content hashes) |
| ADJUDICATING | 5.5 |
| MEMORY_REVERTED | run-scoped revert of 7.6 |
| Idempotency | every rung is idempotent keyed `(run_id, rung)` with done-markers; a boot reconciler resumes incidents with unfinished steps |

Pre-capture barrier: Accept is not final until detectors are drained (DRAINING); a late detector after capture routes to dispute, not VOID.

### 5.3 Response matrix by evidence (local / money / reputation / revoke) [DEF-F1, DEF-F3, DEF-F10, PL-F8]

| Evidence | In-flight | Money | Memory | Author reputation | Hub revoke |
|---|---|---|---|---|---|
| Deny/strike only | continue | none | none | none | no |
| Probabilistic pause, human resume | continue | none | none | none | no |
| Probabilistic pause timeout (UNCONFIRMED_PAUSE) | ABORTED_CLEAN | requester-fault rule | discard Q of run | none | no |
| Deterministic CRITICAL, class R only | kill | floor to DISPUTE_HOLD; payout frozen only until adjudication deadline | discard Q; REVIEW set of promoted records | none | SUSPENDED advisory only after N claims |
| Class C or N confirmed | kill (already) | void remainder, refund floor, slash reserve | full revert + REVIEW cascade | strike, public incident | REVOKED(malicious-confirmed) |
| DATA_INDUCED | kill/pause | floor, void outcome | discard Q, demote offending record | none | no |
| Honest vulnerability or licence | per 6.2 (drain) | per 6.2 | flag | none | per 6.2 |

### 5.4 Money on incident [PAY-F1, DEF-F4, PL-F2, CERT-F1, ID-F4, CON-F3, TASK-F10]

Covered by the ledger rows in 3.3-3.4: a requester-attested claim never produces a final VOID of delivered work; money goes to DISPUTE_HOLD; payout stays frozen until adjudication, but the freeze has a deadline: `min(72 h, honor_left - 6 h)`, after which the default applies. Output of a killed run is held encrypted by the sidecar and never exposed to U or Q; the requester can still read the model I/O they saw (stated). Per-requester claim rate limits, accuracy score, a small refundable claim deposit (burned on confirmed-false claims), weights near zero for new or low-history accounts; per-pack kill rate across requesters (a pack killed only by one requester is probably not malicious).

### 5.5 Adjudication [DEF-F4, DEF-F10, PAY-F1, ID-F4, PL-F2, CERT-F1]

1. Hub replays the claim: checks canary ∈ committed list and the value appears in a sidecar egress record; checks rate limits and requester weight.
2. Certifier re-runs the **same pack digest** on a same-shape synthetic lens with the committed canary placement; also an injected-lens test to detect DATA_INDUCED.
3. Results: reproduced (class C) -> UPHELD; not reproduced -> REJECTED (outcome fee captured per default, requester strike, claim counted, author never struck); inconclusive after 72 h -> INCONCLUSIVE: capture floor plus 50% pro-rata of outcome fee (OD-8), void the rest, no author or requester penalty. Claims from stochastic or time-bomb packs may not reproduce: accepted residual, mitigated by class N corroboration and mystery-shopper probes [CERT-F4].
4. Author gets a rebuttal window of 48 h with the evidence bundle summary (coarse enum only; appeal evidence comes from Certifier re-run, not detector internals).

### 5.6 Revocation governance [DEF-F5, PL-F2, ID-F3]

- One report cannot revoke. Global REVOKED requires class C or N. Between: SUSPENDED advisory shown on the card and ranking; new runs need explicit override; in-flight runs pause and ask. Proposals are weighted per account; linked or new requester/author pairs get no weight. SUSPENDED created automatically from requester claims expires at 72 h unless a human confirms [ID-F3].
- Revocation is terminal for the digest (6.1). Republishing under a new digest/key inherits negative signals: near-duplicate content check at publish, key lineage, parent chain [CERT-F9]; positive history never inherited without shrinkage.
- Local denylists persist, but a hub-signed exoneration notice lets the requester lift it (their choice).

### 5.7 Appeal [DEF-F5]

Appeal reuses the Certifier replay; reinstatement is a new digest through the Certifier (6.1). Adjudicator and SLA: OD-10 (default: hub operator, 5 business days, automated replay first).

### 5.8 Crash and hub-outage behaviour [PR-F12, DEF-F8]

Supervisor crash mid-ladder: boot reconciler continues from the last done-marker. Hub unreachable: claim stays in outbox, retried with backoff; the local denylist and kill are already done; the hold simply continues toward its honor limit, and the hub's own deadline defaults apply (money never depends on the claim arriving: no claim by the accept deadline = normal settlement). Disk full, audit failure: freeze, RESOURCE_EXHAUSTED.

### 5.9 Channels to the author [DEF-F6, PAY-F11]

Author sees only batched aggregates (k >= 20 distinct requesters, time-delayed), coarse incident bit, payout totals; no per-run receipts, no duration/token buckets, no detector identity. The 3.3 text adds: post-run aggregates exist with a bounded information rate; no hard bits-per-run bound is claimed.

### 5.10 Limits stated openly [DEF-F7]

Rules are public; the guarantee is "the pack sees only the lens and the output channel is bounded", not "detectors prevent theft". The Result Guard caps typed-output entropy (enums, quantized values, no free text where the kind allows) and publishes worst-case bits per run; a per-(requester, pack lineage) ledger of output bits and denials lives only on the requester side; canary mix is randomized per run. Residual: covert timing and natural-language steganography in free text.

---

## 6. (e) Pack versions, revocation, keys

### 6.1 Version state machine (hub)

`DRAFT -> VALIDATED -> SUBMITTED -> CERTIFYING -> (REJECTED | CERTIFIED) -> PUBLISHED`
From PUBLISHED: `DEPRECATED(successor, reason)`, `YANKED`, `ADVISORY`, `SUSPENDED`, `REVOKED(reason)`.

| State | Meaning | New resolution | Existing approvals / in-flight |
|---|---|---|---|
| PUBLISHED | normal | yes | continue |
| DEPRECATED | successor exists | yes with banner; MAJOR (widening) successor never offered as one-click upgrade; successor links show capability diff | continue |
| YANKED | buggy but honest; hidden from new resolution | no | continue with warning |
| ADVISORY | upstream CVE or superseded dependency; keeps running with banner until owner republishes | yes with banner | continue |
| SUSPENDED | hub advisory on credible but unconfirmed report | explicit override | in-flight pause and ask |
| REVOKED(reason) | terminal for that digest | no | per 6.2 |
| REJECTED | Certifier refusal | n/a | n/a |

`REJECTED` returns only pass/fail plus a fixed reason-code class (no case ids, no sub-threshold scores), per-publisher rate limit, exponential cooldown, one appeal [CERT-F5, PL-F12]. Certification cost: fee paid up front tied to a verified identity (not an API key), per-identity and per-instrument rate limits, global spend ceiling with admission queue; decision on who pays: OD-12 [CERT-F5]. One counted certification per (digest, model, suite epoch); concurrent runs of one key are locked; attempts logged and pooled [CERT-F6].
Reason enum: `malicious-confirmed, vulnerability, key-compromise, licence, author-request, advisory, superseded`.

### 6.2 Reason -> action table [PL-F8, PL-F9, PL-F1, PL-F10]

| Reason | In-flight | Money | Memory | Slash/VOID rules |
|---|---|---|---|---|
| malicious-confirmed (C/N) or runtime-CRITICAL confirmed | **kill** + quarantine | void remainder, refund floor, slash | selective revert + REVIEW cascade (7.6) | yes |
| vulnerability | **drain** current step, checkpoint, stop; tell user what was paid for | prorate: capture accepted milestones, void rest | flag | **never** slash |
| key-compromise | distrust-from T: versions after T revoked; drain | as vulnerability | flag records from versions after T | none on innocent author |
| licence | drain | prorate | flag | none |
| author-request | drain | prorate | none | none |
| advisory | continue with banner | none | none | none |
| superseded | continue | none | none | none |

Reinstatement = a new digest through the Certifier; appeal reuses 5.5.

### 6.3 Revocation list and freshness [PL-F1, PL-F7, ID-F3, ID-F1, ID-F5, PR-F12]

- One **signed, versioned, whole-file object** (card index + revocation list): `{seq (monotonic), issued_at, valid_until (default 24 h; 4 h for security revocations), prev_list_hash, entries[{digest|key_id, reason, effective_at}], tree_head}`. Clients fetch the whole list; there is never a per-pack query, so the hub cannot see which pack matters (update checks fetch the whole index too). Hash anchored in the transparency log.
- Client keeps the highest `seq` seen and rejects lower or expired lists. Client max age since fetch before **starting** a private-data Pull: low 24 h, medium 12 h, high/secret 1 h (OD-9). Expired -> refuse start (fail closed) for medium and above; low may proceed with a visible "revocation status stale" label. The window is configurable and shown on the approval card.
- Checking is done by the supervisor outside the Cell; no Cell NIC is needed. "On each broker call" means "against the locally cached bounded-freshness list plus the local denylist". Re-fetch on a timer during runs.
- List expiry mid-run: PAUSE at the next checkpoint (AWAIT_REFRESH), keep state, never kill; unreachable hub is never grounds to unblock.
- Free or sideloaded packs with no hub token have no revocation channel: labelled "unrevocable"; private-data Pull refused unless the user pins the digest, or limited to vault-isolated (no private data) use.
- Signed log heads: the hub signs the log head (tree size, root, time); client stores the last head and requires an RFC 9162-style consistency proof on each fetch; heads are pushed to a public git repo as a cheap witness. Ranking labelled "hub-operated, auditable, not independently verified"; "anyone holding the log can recompute". A malicious hub or MITM is out of scope for v1 (stated in 3.2); full TUF roles and multi-operator witnesses are post-hackathon [PL-F7, CERT-F3, ID-F5].
- Key hierarchy: offline root pinned in the client; short-lived role keys (attestation, log, revocation, run-token, quote) in KMS/HSM in a separate account; the Certifier role cannot call Sign; a small signer service accepts only fixed-schema numeric results. Exit test: a Certifier credential attempting Sign fails; a client rejects a rolled-back log or a dropped revocation [ID-F1, CERT-F2: noted, full trust-domain split is a hub-infra design item].

### 6.4 Publish pipeline, digest, races [PL-F5, PL-F4, PL-F11, PL-F12, ID-F9]

- **Digest** = SHA-256 over author-authored files only, raw bytes (no normalization). Not covered: `model.tested_on`, `certified_digest`, `commercial.*`, listing metadata, attestations. Covered: phases/workflow, tools, network, memory, modes, runner, licence. A normative "digest-covered fields" list lives in the phase-0 digest spec.
- Validate requires canonical forms (LF only, no CR in scripts, reject rather than normalize). Manifest is JSON or a strict YAML subset (no anchors, no duplicate keys, explicit types); one shared parser library with a conformance corpus is used by validator, hub, supervisor. D9 hashes raw bytes against this definition [PL-F12, DEF-F11].
- **Capability-set hash** = canonical hash over tools, namespaces, max_sensitivity, network, workflow nodes, proposes, `learns_from_requesters`, `result_schema`, runner, model requirement and price ceiling. Hub compares with the previous version of the same id and **rejects a non-MAJOR bump that widens**; the hub renders the diff shown on the card, not the author's changelog [PL-F4].
- **Write-once CAS** on `(publisher_id, id, version) -> digest`; `publisher_id` is immutable; ids bind to it; deleted namespaces are tombstoned permanently; transfer needs a signed handover from the old key and shows an "ownership changed" banner; confusable-name checks (Unicode normalization, edit distance); closed platform taxonomy for speciality tags, claimable only with a passing certification; browse returns structured fields only [PL-F11, CERT-F10, ID-F9]. Sybil defence is economic (identity tier, deposit), not account age; the doc says sybil resistance is economic, not absolute [ID-F9].
- `parent` must be a published digest owned by the same publisher id, or a signed fork record; else "unverified lineage", no ranking carry-over. Ranking is per (pack version, model) so lineage carries no rank weight [PL-F4].
- Pins: the hub mirrors pinned upstream trees at publish, records a SHA-256 tree hash and rejects pins that cannot be mirrored; "pin means content fixed, not safe" is stated [ID-F2]. The TCB itself (supervisor, sidecar, vaultd, Disclosure Compiler, CLI) is released under an offline TCB key, pinned hash per release in the log, opt-in updates with no silent update and no downgrade, vendored hash-locked crypto/Presidio/Biscuit dependencies with an SBOM; reproducible builds are a goal, not a claim [ID-F2].

### 6.5 Attestation and listing states [PL-F5, PL-F9, CERT-F8, CERT-F6, CON-F6, CERT-F3]

Separate signed documents referencing the pack digest:
- **Certification attestation** (in-toto predicate): pack digest, model id + provider revision, suite version and epoch, engine/sidecar version, runner image digest, driver tier, Result Guard version, Certifier build, `score_lcb`, run-log digest, per-task outcome hash vector, k, formula/grader versions, baseline vector, `valid_until` (90 d), plus a `lock` block (runner image digest, engine version, upstream {repo, commit, sha256 of vendored tree}).
- **Listing** (price, licence tier, ip_tier, refund terms): own version number, signed by the owner, countersigned by the hub, appended to the log. A price change is a listing update, not a new digest.
- Attestation states: `CURRENT -> STALE (stack component changed, TTL expired, suite rotated) -> ORPHANED (model id retired)`. A run needs a CURRENT attestation for (digest, requester's sidecar model); otherwise the card says "uncertified on your model", shows no LCB, and start needs an explicit override banner (override runs are excluded from verified-paid ranking). Private-data Pull requires a non-stale attestation or an explicit requester override. Re-certify automatically on engine, model or suite change, in staggered waves (top packs first). Badge wording is "evaluated" (scope text embedded: suite, epoch, model, date, exclusions), never "safe". Reverse index from upstream (repo, sha) and runner version to dependent digests drives ADVISORY; critical severity forces SUSPENDED.
- Scoring protocol v1 in 5.4: cluster bootstrap over tasks, baseline-normalised delta, anchor subset across epochs, judge model different from the agent model, programmatic graders first, `scoring_version` frozen in the attestation; retired suites published with commit-reveal [CERT-F6, CERT-F3].

### 6.6 Publisher identity and key states [PL-F3, ID-F7, CERT-F9]

Publisher = stable id with a key-history chain in the transparency log; all timestamps are hub log times, never author-supplied. Publish needs both hub-account auth and a key signature over `(digest, version, nonce)`.

`KEY: ACTIVE -> ROTATING (72 h delay, notifies prior installers) -> ACTIVE'`; `ACTIVE -> COMPROMISED(distrust-from T)`.
- Rotation: signature from the old key or an offline recovery key registered at signup. Hub-assisted recovery with a 14-day delay announced in the log and to contacts.
- COMPROMISED is a hub-signed, monotonic log event (from the author via the recovery key, or from hub detection): revokes all versions published after T and reverts "recommended" to the last version before T; a key cannot un-revoke; the author publishes under a new key.
- A new key on an existing pack id is "new, not yet cooled" for installers; it does not become "latest" until a cooling period (proposal 72 h) passes; the diff card is prominent when the key changed or logins were anomalous; auto-follow is opt-in.
- Hackathon scope: hub-signed distrust-from-T, log timestamp, cooling flag, payout freeze on destination change. The rest is a documented production gap.

### 6.7 Approval binding and upgrades [PL-F4, HUM-F10]

Approval binds to `(digest, capability-set hash, mode, lens, budget)`; it never follows "latest"; scheduled workflows pin a digest. Re-approval is **computed**: any change in capability hash, tools, model class, price above cap, mode, data-flow labels or gate set = full card; prompt-only change = one line "behaviour changed, certified score x -> y, safety suite passed" with the diff one click away; expiry (90 d) only for high-sensitivity runs. Approval budget per run is shown on the listing; workflows above a ceiling are refused at publish; auto-allow inside an already-approved envelope, ask at irreversible/high-sensitivity transitions.

### 6.8 Lineage and laundering [CERT-F9]

Negative signals propagate to descendants, the author identity cluster and near-duplicate content; positive history is inherited only with shrinkage and unchanged permissions; certified score is never inherited; a new release of a ranked pack from a new key epoch is held for a visible window before becoming default.

### 6.9 Failure matrix (lifecycle)

| Step | Failure | Handling |
|---|---|---|
| validate | parser disagreement | impossible by shared parser + corpus |
| certify | Certifier crash | job retried by id; attempt logged; no partial attestation published |
| sign | signer down | publish blocked; no unsigned publish |
| publish | duplicate (id, version) | CAS rejects |
| install | list stale/unreachable | 6.3 |
| run | revoked mid-run | 6.2 |
| revoke | forged/replayed old list | monotonic seq + hash chain + expiry |

---

## 7. (f) Vault write, Q, promotion, rollback

### 7.1 Write path with state

`CAPTURED -> SCANNED -> JOURNALED -> EXTRACTION_PENDING -> EXTRACTING -> PROPOSED -> GATED -> ACTIVE`; failures: `RETRY`, `DEAD_LETTER`.

| Step | Rule |
|---|---|
| Step 0 SCANNED | Pattern + entropy secret scanner (gitleaks/trufflehog-style) at capture, **before journal append**. A hit replaces the span with a handle `{{secret:h_xxxx}}`; the value goes only to the OS keychain / encrypted store; never to the journal, extractor (especially remote), audit log or quarantine. Secret-type records come only from explicit user action ("store as secret handle?"). Dereference only in the Tool Broker, which scrubs output. "secret" is defined by scanner + handle, not by the extractor's classification [MEM-F8]. Journal payloads are encrypted under a per-event key so shred keeps the chain valid |
| JOURNALED | Each capture event records the **union of source classes in the context window** (web, document, pack output, tool output, user) and `parents` (event ids consumed). Taint is set at capture, not in the extractor [MEM-F3] |
| EXTRACTION_PENDING | Extraction queue lives in the journal: cursor, attempts, backoff, dead-letter, extractor version stamp, visible "extraction stalled" status; dead-letter items re-run when extractor or endpoint approval is restored. Journal stays truth [MEM-F7]. Remote extractor use is opt-in per sensitivity level; high sensitivity is never sent remote [MEM-F5] |
| PROPOSED | Proposal id = `hash(source event ids + extractor version)` (idempotent, deduplicated) |
| GATED | 7.5 |

### 7.2 Q state machine

`PROPOSED -> (ENDORSED | REJECTED | EXPIRED | DISCARDED_RUN | STALE)`
- Cap Q per pack and globally; fixed TTL (14 d) with expiry notice; once a pack's cap is hit new proposals are rejected with a strike. Digest is sorted by risk and sensitivity type; profile/procedural/secret shown separately; batch-reject by pack; **no bulk-approve for high-risk types** [MEM-F7].
- **Only a Reader session with no write tools reads Q.** The write-capable local agent and the Scribe never read Q; the Scribe gets only schema-validated, length-capped, inert fields. The "few slots" option is deleted [MEM-F7].
- Proposal schemas are constrained to a hub-defined meta-schema: enums, numbers, hashes, references; free strings only if shown to the user as a diff and never passed to the Scribe or auto-promoted [CON-F5].
- Review UI shows source run, the exact text in the pack's words and a deterministic "pack X claims this" reason; demo wording changes from "accept into U" to "endorse as pack-claimed" [HUM-F1].

### 7.3 Record states

`ACTIVE -> SUPERSEDED (system time, `superseded_by`) | INVALID (valid-time `invalid_at`) | REVIEW (tainted by an incident) | SHREDDED`. Migration uses `superseded_by`, not `invalid_at`, so bi-temporal queries stay correct; read-time upcasters with lazy rewrite; devices refuse to write schemas newer than they know; downcast must preserve security labels or the pack is refused; migration is a checkpointed, resumable job with dry-run [MEM-F11]. Retention: per-type policy with summarising compaction that keeps provenance; TTL means hide vs shred and is stated per type; quotas per namespace and source class; ranking not purely recency-weighted; incremental indexing with a rebuild-cost budget [MEM-F12]. Episodic outcome records store only enum/ID fields (task id, pack digest, accept/reject, cost), no free text from a result [CON-F5].

### 7.4 Origin, taint and trust tiers [MEM-F4, MEM-F9, MEM-F10, HUM-F1, CON-F5]

Record schema additions: immutable `origin: {class: foreign|local|user, pack_digest, run_id, proposal_id, accepted_by, accepted_at, content_hash}` and `derived_from: [{pack_digest, run_id, proposal_id, record_id}]`. vaultd computes and propagates them (extractor output, episodic summaries, consolidation, Scribe derivations); acceptance never erases origin. A derived record is never promoted above its lowest-tier ancestor.

Tiers (resolving a conflict between findings, see 8): 0 foreign/Q-unreviewed; **1 endorsed-foreign / pack-derived** (user accepted for storage; not user-authored); 2 local-agent observation (trusted-local, no foreign taint); 3 user-authored text (typed or edited by the user). v2's example schema stays valid. Rules for tier 1: never counts as an independent source for corroboration; low slot cap; served only to the origin author's packs or to a pack whose lens names its tag/namespace (shown on the preview as "derived from pack X"); excluded from Hosted packets by default; always rendered with its provenance label; default TTL with reconfirmation; sensitivity at acceptance = max(sensitivity of everything in the producing run's read accounting, floor medium) and the user cannot lower it without a distinct override; lens-grantable tags come only from user-confirmed records, and unlabeled or extractor-labelled records default to sensitivity high with an empty tag set until confirmed.

P-plane is a vault namespace with the same schema, journal, encryption, shred and migration; keyed by `(author, pack lineage, digest)` with strikes inherited via `parent`; stores references not copies; lens widening is suggest-only; hub queries are batched and cached, and no outbound request carries P-derived data [MEM-F10].

### 7.5 Promotion gate

- Auto-promote only if no foreign taint in the ancestry **and** source class is trusted-local, or corroborated by 2+ independent source classes where independence is computed from **disjoint ancestry in the journal DAG**, not the stamped class label. Only explicit user "remember" or user-authored text counts as trusted-local. Any foreign taint -> Q whatever the actor. Payment Accept is a distinct event type and is never a corroborating class.
- Agent-initiated writes while foreign content is in context go to Q with per-item acceptance; a session that ingested foreign text drops write rights or routes writes through the schema-validated proposal channel [MEM-F3].
- Profile, procedural, secret: always human approval (digest, diff). Test: poisoned web page -> agent-written fact -> must land in Q.

### 7.6 Run-scoped revert (replaces "roll back U to checkpoint") [MEM-F1, MEM-F9, MEM-F10, PR-F5, DEF-F9, HUM-F4, CON-F11, PL-F10, HUM-F1]

Never truncate or rewind the journal. Checkpoints (per run id, so overlapping runs are unambiguous) are audit and diff anchors only.
1. **Automatic part** on a confirmed incident or REVOKED(malicious-confirmed): delete the run's Q items and pending proposals; compute the **causal set** = records whose `origin`/`derived_from` traces to the run or the pack digest, plus records written by the local agent in a session that read Q or pack output from that run.
2. For each record in the causal set: set `invalid_at` or restore the predecessor via a **compensating event**, only if the current version equals the tainted version (CAS); on mismatch raise a conflict to the user, never overwrite. Records with no run ancestry, tier 3 user-authored records, and records from concurrent unrelated runs are untouched.
3. **Human part**: promoted or mixed-ancestry records move to REVIEW (excluded from lens retrieval for packs, visible to the local agent with a flag) pending a decision: keep, invalidate, or crypto-shred. Show a preview of the revert list; auto-apply only to records that were auto-promoted and never user-edited. 30-day restore tombstone.
4. Read path adds a step between 2 and 3: drop records whose `origin.pack_digest` is on the local denylist or the revocation list (takes effect immediately, no rollback needed).
5. Severity scoping: CRITICAL confirmed by a deterministic detector -> automatic exclusion plus review diff; advisory-only (D13, D14) -> flag only.
6. Provenance index on `pack_digest` and `run_id`; `bridge vault trace <pack>`.
7. Regression tests: (a) accept poisoned item, revoke pack, assert it is gone from all later lens retrievals and unrelated concurrent records survive; (b) user write during a run then CRITICAL kill leaves that write intact on every device; (c) sleeper pack with 10 accepted runs then CRITICAL leaves none of its items or derivatives retrievable until re-accepted.
Revoke after accept applies to "a record accepted from pack A and used by pack B" through the `derived_from` closure.

### 7.7 Shred contract [MEM-F5, ID-F11, PR-F5, MEM-F2]

Per-record DEK wrapped under a rotating KEK in the OS keystore (backups hold only wrapped DEKs; KEK excluded or escrowed separately). `content_hash` is replaced by `content_commit = HMAC(record_key, content)` so shredding makes it unconfirmable; record metadata (ns, lens_tags, type) is encrypted under the same shreddable key, leaving only opaque id and seq in the clear. A shred is a signed monotone tombstone that replicates; each device deletes key, ciphertext, index and embedding rows and rebuilds; compaction removes stale ciphertext. Audit and quarantine entries sit under the same hierarchy with retention limits and hold references and hashes, not content snapshots. Per-run staged keys are destroyed on shred. Key hierarchy: user root key (recovery phrase) -> vault master -> per-namespace -> per-record; no hub escrow by default; device removal rotates namespace keys. Shred shows "complete only when every device has acknowledged or been removed". Unremovable residue (text already sent to Nebius, offline devices until sync) is documented.

### 7.8 Checkpoints

A minimal hash-chain head and an anchor before each task are in phase 5; Merkle hardening in phase 16. The audit signing key is held by the supervisor or a separate signer running as a different OS user from the Cell driver and sidecar data path; forward-secure key evolution; chain head periodically anchored to the hub or a paired phone [ID-F11].

### 7.9 Crash recovery

Journal append is the commit point. Index and extraction queue are rebuilt from the journal at boot. A run's Q items carry `run_id`, so an interrupted incident revert resumes from its done-markers (5.2).

### 7.10 Deferred: multi-device [MEM-F6]

Specified now, built after phase 1: per-device signed sub-chains `{device_id, dseq, prev_hash}`; checkpoint = vector of per-device heads + Merkle root; records carry version vectors with CAS as the local fast path; concurrent edits produce an explicit conflict event; proposals idempotent by id; **tombstones dominate** and an offline device applies pending tombstones before pushing; hybrid logical clocks for ordering; device revocation rotates keys. Data already on a lost device stays exposed (stated).

---

## 8. Conflicts between findings and how they were resolved

| # | Conflict | Resolution |
|---|---|---|
| 1 | Endorsed-foreign tier: HUM-F1 says tier 2, MEM-F4/MEM-F9 say cap at tier 1, v2 defines tier 2 as local-agent observation | Tier 1 (7.4). Tier 2 stays "trusted-local" |
| 2 | Clarification: PR-F7 wants a blocking sidecar `clarify` op, TASK-F3 forbids mid-task blocking | Gates are workflow nodes at step boundaries; mid-step need ends the step with `NEEDS_INPUT` (1.7) |
| 3 | Pause timeout money: DEF-F3 says release hold minus floor, HUM-F5 says no-fault void | UNCONFIRMED_PAUSE: no pack effect, money follows the requester-fault rule (floor + accepted milestones). OD-8 |
| 4 | D2 handling: DEF-F1 (Result Guard reject, no kill for verbatim in free text), PR-F10 (kill + HOLD), CON-F1 (kill only on egress) | Split by evidence (5.1): verbatim in free-text field is soft; transformed/egress/non-free-text is hard |
| 5 | VOID vs HOLD: v2 7.2 voids immediately; PAY-F1, DEF-F4, PR-F10 say HOLD | HOLD/DISPUTE for any requester-attested claim, VOID only for uncaptured, never-delivered work with class C/N evidence (3.4) |
| 6 | Hub re-verifying acceptance checks (PAY-F2) vs hub never seeing result bytes (B2) | Hub cannot recompute; check verdict is requester-attested; limits are floor, reject-rate score and auto-accept on silence |
| 7 | Staging before card (HUM-F2) vs AUTHORIZE before staging (v2 6.2, PR-F3 wants authorize last) | Stage -> card -> authorize -> start (2.3) |
| 8 | Rollback "per-device" (CON-F11) vs "compensating events replicate" (MEM-F1) | Compensating journal events (replicate normally); no per-device rewind |
| 9 | Payout holdback vs 180-day dispute window | Rolling reserve; production vs demo label (3.8) |
| 10 | Revocation freshness: 24 h (PL-F1) vs 1 h for high sensitivity (ID-F3) | Hub-set `valid_until` 24 h; client max age by sensitivity (6.3) |
| 11 | One-time token vs resumable run (PL-F6, ID-F8, PR-F3) | Token starts; lease continues; both bound to run_id (2.5) |
| 12 | Pull "fresh context per phase" (PR-F6) vs single Cell | Each step is a separate Cell start; claim retained only because implemented that way |

---

## 9. Owner decisions needed

| ID | Decision | Recommended default |
|---|---|---|
| OD-1 | Is Pull's lack of fair exchange acceptable if floor + reject-rate + dispute path mitigate it? (This is a product-positioning call.) | Accept; say so in the guarantees |
| OD-2 | Floor fee size and what it covers | 20-30% of price (proposal, unsourced) |
| OD-3 | Do packs that must charge per run require `licensed-watermarked` or `split-shell-brain`, with `open` + per-run price relabelled donation? | Yes (lint rule) |
| OD-4 | Does v1 support resume from checkpoint, or void-and-rehire only? | Design as in 2.5; hackathon builds void-and-rehire with checkpoints written |
| OD-5 | Hosted failover policy | Off; opt-in per task with disclosure ledger |
| OD-6 | Max run length per authorization segment | 24 h v1 (must be below 62 h by 3.5) |
| OD-7 | Who bears Hosted gateway cost on host fault; claim deposit size | Hub bears bounded by cap, recovered from host holdback |
| OD-8 | Indeterminate and inconclusive splits; reserve percentages | 50/50; 50% reserve to day 180 for new authors |
| OD-9 | Revocation max-age by sensitivity; thresholds for "aged" requesters (class N) and N itself | 24 h / 12 h / 1 h; N=3; age 30 d and non-trivial spend |
| OD-10 | Who adjudicates and the appeal SLA | Hub operator; replay first; 5 business days |
| OD-11 | Tier numbering (tier 1 = endorsed-foreign) accepted | Yes |
| OD-12 | Who pays certification tokens | Author pays up front; platform subsidises only seeded reference packs |
| OD-13 | Is the Nebius pass-through (Hosted gateway) allowed under Nebius terms? Blocker before building 4.5 | Read ToS; fallback requester-supplied key |
| OD-14 | Do Pull private-data packs require a CURRENT attestation or may the user override? | Override allowed with banner and ranking exclusion |
| OD-15 | Hosted Sensitivity ceiling | `low` only, user-confirmed |

---

## 10. UNVERIFIED items carried by this design

- PayPal: reauthorize-during-honor rule; `PayPal-Request-Id` retention and length; `final_capture` multi-capture semantics; error codes for capture/void races; refund window of a capture; 180-day dispute window; seller protection for intangible AI services; Payouts by payer id and `sender_batch_id` dedupe window; multiparty/`platform_fees` access; whether an unattended re-authorization of a payer order is possible.
- Nebius: per-key caps/scopes, ZDR per key, ToS on pass-through, rate-limit uplift.
- WSL2: idle/suspend behaviour, DrvFs/automount fixtures, Tetragon feasibility, tmpfs behaviour.
- Presidio, Biscuit JS/WASM, Rekor fit for private metadata.
- Legal: merchant-of-record, money transmission, tax, sanctions, warranty reading of "certified", defamation exposure for public incidents.
- Percentages, TTLs and thresholds listed above are proposals.

---

## 11. Coverage matrix (every audit finding)

Format: id -> where resolved. `(R)` = accepted residual risk with the reason. `(P)` = outside these six state machines, pointer to the design doc that must carry it. `(u)` = audit marked not-checked; decision adopted conservatively.

**PL (pack lifecycle)**
PL-F1 6.3, 2.5, 5.6. PL-F2 1.5, 5.4-5.6. PL-F3 6.6, 3.7. PL-F4 6.4, 6.7. PL-F5 6.4, 6.5. PL-F6 2.4, 2.5, 3.5. PL-F7 6.3 (full TUF/witness network (R): post-hackathon). PL-F8 6.1, 6.2. PL-F9 6.5. PL-F10 7.6. PL-F11 (u) 6.4, 2.10, 5.2. PL-F12 (u) 6.4, 6.1.

**PR (Pull run)**
PR-F1 2.3, 2.12. PR-F2 1.4, 2.9. PR-F3 1.2, 2.3, 2.12. PR-F4 2.11, 3.4 (no fair exchange (R)). PR-F5 2.6, 7.6. PR-F6 2.4, 2.6. PR-F7 1.7, 2.7. PR-F8 2.8. PR-F9 1.8, 2.3, 3.4. PR-F10 5.1-5.5. PR-F11 2.10. PR-F12 (u) 5.2, 5.8, 2.9.

**PAY (payment)**
PAY-F1 5.4, 5.5 (requester can always take the output (R)). PAY-F2 2.11, 3.4. PAY-F3 3.1, 3.5. PAY-F4 3.3, 3.6. PAY-F5 3.7, 3.11. PAY-F6 3.8. PAY-F7 3.8 (bounded recovery (R)). PAY-F8 3.7. PAY-F9 3.9. PAY-F10 (u) 3.8 (full anti-wash weighting (P) ranking doc). PAY-F11 (u) 3.10, 5.9. PAY-F12 (u) 3.2, 3.10.

**HO (Hosted)**
HO-F1 4.5. HO-F2 4.4. HO-F3 4.4. HO-F4 4.5, 4.7. HO-F5 4.3, 3.5. HO-F6 4.7, 3.3. HO-F7 4.6. HO-F8 4.9 (copy-without-use (R)). HO-F9 (u) 4.10. HO-F10 (u) 4.8. HO-F11 (u) 4.4, 1.2, 1.4 (Sealed enclave counters live in hub gateway). HO-F12 (u) 4.10.

**MEM (memory)**
MEM-F1 7.6. MEM-F2 2.6, 7.7. MEM-F3 7.1, 7.5. MEM-F4 7.4. MEM-F5 7.7. MEM-F6 7.10 (built later). MEM-F7 7.1, 7.2. MEM-F8 7.1. MEM-F9 7.6. MEM-F10 (u) 7.4. MEM-F11 (u) 7.3. MEM-F12 (u) 7.3.

**DEF (active defense)**
DEF-F1 5.1. DEF-F2 5.1. DEF-F3 1.7, 5.3. DEF-F4 5.4, 5.5. DEF-F5 5.6. DEF-F6 5.9. DEF-F7 5.10 (public rules (R)). DEF-F8 5.2. DEF-F9 7.6. DEF-F10 5.2, 5.5. DEF-F11 (u) 5.1. DEF-F12 (u) 5.1, 5.2.

**HUM (human-in-the-loop)**
HUM-F1 7.4, 7.2. HUM-F2 2.3, 2.6. HUM-F3 2.10. HUM-F4 7.6. HUM-F5 1.7, 1.8, 2.13. HUM-F6 2.11. HUM-F7 2.10. HUM-F8 2.3 (non-WSL fallback driver (P) phase 16). HUM-F9 (u) (P) guarantee copy and strip belong to the UX/guarantee text doc; mechanism side: 3.2 and 4.5 label what leaves the machine. HUM-F10 (u) 6.7. HUM-F11 (u) 4.10. HUM-F12 (u) 1.7.

**CERT (certification and ranking)**
CERT-F1 5.4, 5.5. CERT-F2 (P) hub trust-domain split, 6.3 key rule only. CERT-F3 6.3, 6.5. CERT-F4 (P) sleeper/fingerprint resistance belongs to the Certifier doc; 5.5 handles non-reproduction (R). CERT-F5 6.1. CERT-F6 6.5. CERT-F7 3.8. CERT-F8 6.5. CERT-F9 (u) 6.6, 6.8. CERT-F10 (u) 6.4. CERT-F11 (u) (P) platform-seeded labelling in the ranking doc. CERT-F12 (u) (P) legal wording; 6.5 badge text, 3.9.

**ID (identity and trust roots)**
ID-F1 6.3. ID-F2 6.4. ID-F3 6.3. ID-F4 5.4, 5.5. ID-F5 6.3. ID-F6 4.4, 2.10. ID-F7 6.6. ID-F8 2.5, 3.5, 1.4. ID-F9 6.4. ID-F10 (P) metadata privacy: 6.3 whole-list fetch and 5.9 batching; rest in the privacy doc. ID-F11 7.7, 7.8. ID-F12 (u) 4.5.

**TASK (task I/O model)**
TASK-F1 2.11. TASK-F2 2.11. TASK-F3 1.7. TASK-F4 5.1 (D6 policy), stego capacity (R). TASK-F5 2.11. TASK-F6 2.4, 2.5. TASK-F7 1.2, 2.3, 2.5. TASK-F8 (P) web research two-stage tasks belong to the task spec doc. TASK-F9 (P) connectors out of v1, kill revokes any session. TASK-F10 3.3, 5.4. TASK-F11 2.6. TASK-F12 2.10.

**CON (consistency)**
CON-F1 5.1. CON-F2 2.6. CON-F3 5.4, 1.5. CON-F4 4.5. CON-F5 7.2, 7.4. CON-F6 6.4, 6.5. CON-F7 3.2. CON-F8 (P) build-phase reordering belongs to the build plan. CON-F9 (P) demo scene realism belongs to the demo script; D5 sensor spec in 5.1. CON-F10 (u) 2.10. CON-F11 (u) 7.6. CON-F12 (u) 2.4, 6.5 (guarantee-sentence rewrite itself (P)).
