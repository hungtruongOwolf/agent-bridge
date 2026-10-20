# Flow audit 02: the Pull run as a state machine

Date: 2026-10-07. Audited text: `architecture-v2.md` sections 3, 4.4, 5.2, 6.2, 7 and 3.4, plus `research-v2/05, 07, 08` and `research/09, 10` for facts. Nothing in architecture-v2 defines run states, so the machine below is **reconstructed by the auditor**; where the design is silent the cell says "UNDEFINED". Facts about PayPal (29-day hold, 3-day honor period, 180-day dispute window, `PayPal-Request-Id` idempotency) come from the research notes, which cite https://developer.paypal.com/docs/checkout/standard/customize/authorization/ and https://developer.paypal.com/docs/api/payments/v2/ . Nebius 429 and dynamic rate limits: https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md (per-model limits UNVERIFIED). WSL2 `vmIdleTimeout` and shared VM: https://learn.microsoft.com/en-us/windows/wsl/wsl-config and /about (exact suspend-on-sleep behaviour with a running container UNVERIFIED).

## 1. Actors and the state each one holds

| Actor | Durable state (survives its own crash?) | Volatile state |
|---|---|---|
| Requester LLM agent (local, Nemotron) | none defined; P-plane notes | conversation, chosen pack, any pack output it has read |
| Supervisor | UNDEFINED (no run table, no WAL) | cell handle, strike counters, kill authority |
| Sidecar (model proxy, memory broker, tool broker, egress, Result Guard, detectors, audit log) | audit log file | budget counters, Biscuit, canary map, read accounting |
| vaultd | journal (durable), index (rebuildable) | write gate, CAS versions |
| Cell | none (tmpfs T) | plan/work/return progress |
| Hub (run-token issuer, escrow, log, revocation list) | token state, PayPal authorization id, receipts | none |
| PayPal | authorization (29 d hold, 3 d honor) | none |
| Nebius | none we control | rate-limit window, usage |
| Relay / phone | none | approval prompts |
| User | the real source of Accept, clarification, approval | laptop lid |

## 2. State machine (reconstructed)

```
S0 BROWSING -> S1 PROPOSED(pack,digest,lens) -> S2 APPROVAL_PENDING -> S3 APPROVED
S3 -> S4 HOLD_PENDING (hub: create order AUTHORIZE, issue run token)
S4 -> S5 HELD(token ISSUED, authorization_id)
S5 -> S6 STAGING (vaultd copies lens slice to /in, canaries, Biscuit minted)
S6 -> S7 STAGED -> S8 STARTING (driver starts cell, token CONSUMED)
S8 -> S9 RUNNING { PLAN -> WORK -> RETURN }   sub-states (UNDEFINED in design): STALLED(model), PAUSED(detector), WAITING_USER
S9 -> S10 RESULT_GUARD -> S11 ACCEPT_PENDING (objective checks, then user Accept)
S11 -> S12 ACCEPTED | REJECTED | TIMED_OUT
S12 -> S13 CAPTURING (partial/final) | VOIDING
S13 -> S14 CLEANUP (destroy cell, wipe T, receipt) -> S15 HOLDBACK -> S16 PAYOUT -> S17 CLOSED
Sinks: FAILED, KILLED -> QUARANTINED -> REVOKED -> ROLLED_BACK -> INCIDENT_RECORDED
```

Order in the text of 6.2 step 9: capture and payout appear BEFORE "Cell destroyed, T wiped". The auditor treats that as an ordering defect (finding 1).

## 3. Step-by-step interrogation (fail / repeat / out-of-order / concurrent / timeout / malicious / offline / state changed)

| Transition | Key questions and result |
|---|---|
| S1 -> S2 approval | Approval is "once per (digest, mode, lens, budget)" (6.2 step 2) but a hold is per run. Does a stored approval let the local LLM agent hire again with no click? Agent has read untrusted pack output. Ambiguous. (finding 11) |
| S2 -> S3 preview vs stage | Byte-exact preview computed at T0; stage happens at T1 after a hub round trip and a PayPal call. Vault can change in between. Preview hash is not bound to staged bytes. (finding 5) |
| S3 -> S5 hold + token | Hub timeout after PayPal authorized: retry creates a second hold. No run id idempotency key defined. Token "one-time" is consumed at S8; cell start failure burns it. (finding 3) |
| S5 -> S6 staging | Disk full, symlinks, big lens, file edited while copying. No quota pre-check, no vault seq recorded. (findings 5, 12) |
| S6/S8 data paths | Step 4 puts the lens slice in `/in` as files; step 6 says data only via `memory.search` through the Broker with caps, accounting and D4. Both cannot be true. (finding 6) |
| S8 -> S9 phases | Phases planner/worker/returner declare different memory and tool rights, but one cell and one `/in` exist. Who switches rights, and what carries state between phases? UNDEFINED. (findings 1, 6) |
| S9 crash of supervisor | Orphan cell keeps running; hold dangles; stage dir stays; nothing reconciles on restart. (findings 1, 2) |
| S9 crash of sidecar | Cell sees ECONNREFUSED. Is that D12 (KILL) or a plain crash? Who restarts it with the same budget counters? (finding 2) |
| S9 vaultd crash/restart | `memory.search` fails; Broker returns error to pack; retry semantics undefined; snapshot makes this mostly moot only if `/in` is the data path (again finding 6). |
| S9 model call | 429, 5xx, timeout, outage, model id change. Proxy retry/backoff rules and what the pack sees are undefined. (finding 8) |
| S9 budget | Token/USD cap hit during WORK: no reserve for RETURN, so no result at all. Partial result and capture policy undefined. (finding 9) |
| S9 clarification | No channel from cell to user. Pack guesses, fails, or smuggles a question into the result. (finding 7) |
| S9 laptop closes | Supervisor, WSL VM, sidecar suspend; hub heartbeat and hold timers keep running; wake-up clock jump expires budgets and tokens. (finding 2) |
| S9 detector pause | D6 confirmation "user click, default timeout kill for high sensitivity" while user is away: kill by absence. PAUSED has no deadline. (finding 7) |
| S9 canary hit by honest pack | D2 is KILL plus void, but 7.3 says a canary alone never affects author reputation. A malicious requester can exploit this. (finding 10) |
| S10 -> S11 accept | Acceptance checks are declared by the author in the manifest; who executes them and where? Timeout behaviour is only in research-v2/08 ("auto-accepts"), not in architecture-v2. Honor period 3 days. (finding 4) |
| S12 -> S13 capture | Idempotency, partial capture after hold lapse, and who triggers capture (the LLM agent has the PayPal MCP tools per research/09 step 8). (findings 4, 11) |
| S14 cleanup | Only T is wiped; staged `/in`, VM disk residue and quarantine copies are not covered; crypto-shred does not reach them. (finding 5) |
| Ladder 4-9 | Multi-step, non-atomic, includes a hub call (void). Crash or hub outage in the middle leaves a half-executed ladder. (finding 12) |
| Revocation check | "before every start and on each broker call": offline hub means fail-open or fail-closed? UNDEFINED. (finding 12) |

## 4. Determinism and retry table (what the design should say, none of it is stated today)

| Step | Deterministic? | Retry policy that is safe |
|---|---|---|
| Approval, hold, token, stage, start | yes (engine code) | Idempotent with a requester-generated run id; retry freely until S8 |
| Pack phases | no (LLM) | Never auto-retry a whole run (costs money, new nondeterministic output); resume from supervisor-held phase checkpoint only |
| Model call | no | Proxy-owned retry on 429/5xx with Retry-After; pack sees only typed final error |
| Result Guard, acceptance checks | yes | Re-runnable, pure |
| Capture/void/payout | yes | Idempotent with `PayPal-Request-Id` derived from run id + op |
| Ladder | yes | Write-ahead intent, replay on restart |

## 5. Consistency with other flows and the guarantee text

- 3.3 says "author receives nothing during the run". Hub run-token issuance, the receipt and ratings are the only channels; the receipt's token-count bucket varies with data but 3.4 lists it as allowed while forbidding "counts that vary with data". Low severity, noted only.
- Hosted flow 6.3 relies on "void path when defense fires" with host-attested verdicts; the same D2-void-without-corroboration problem is worse there.
- 4.5 "roll back U to pre-task checkpoint" contradicts 4.1 (packs cannot write U) and 4.5 "conflicts surface to the user": a time-based rollback also deletes the user's own concurrent edits. (finding 5)
- 4.3 promotion gate and Accept: Accept is described as the requester action; research/09 exposes capture/void to the Nemotron agent loop. Rule of Two violated if that agent has read pack output. (finding 11)

## 6. Findings

See the structured list returned with this audit (12 items, ranked). Short index:

1. No durable run record, no phase checkpoint, no reconciliation; cleanup ordering wrong.
2. No fail-closed liveness between supervisor, sidecar, cell, hub; sleep/wake and clock handling.
3. Hire is not idempotent: duplicate holds, burned one-time tokens, orphan authorizations.
4. Accept window, auto-accept, author-defined acceptance checks and PayPal 3-day honor period.
5. Snapshot lifecycle: preview-to-stage gap, staleness, forget, residue, time-based rollback.
6. `/in` snapshot defeats the Broker read path and per-phase memory rights.
7. No human-wait model: clarification, D6 confirm, pause, accept all lack channel, deadline, default.
8. Model API failure semantics: retries, 429 across concurrent runs, model drift, billing of retried calls.
9. Budget exhaustion with no returner reserve; partial-result and capture policy; who pays Nebius.
10. D2 kill+void contradicts anti-framing; malicious requester can obtain free work.
11. Approval scope and the LLM agent as confused deputy (re-hire, accept, capture); concurrent runs.
12. Failure handlers are not crash-safe: ladder atomicity, hub outbox, audit log and disk full, offline revocation list.
