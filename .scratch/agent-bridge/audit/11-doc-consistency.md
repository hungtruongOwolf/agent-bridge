# 11 - Doc consistency audit (architecture-v2.md vs research/, research-v2/, decisions.md)

Date: 2026-10-07. Auditor: flow auditor. Scope: documents only. External facts are not re-verified here; UNVERIFIED tags are inherited from the sources.

## 1. The flow as a numbered sequence (as written in architecture-v2.md sections 3, 5, 6, 7)

Actors and the state each holds:
- REQ-HUMAN: approves cards, accepts results, promotes proposals.
- REQ-AGENT (Nemotron via Nebius, local): browses hub MCP, picks pack and mode, holds hire/pay MCP tools, reads U fully.
- VAULTD: U, Q, P planes, journal, index. Writer: user + local agent only.
- DISCLOSURE COMPILER / BROKER: lens, Biscuit, canaries.
- SUPERVISOR (separate process): kill, quarantine, revoke. SIDECAR: model proxy (holds Nebius key), memory broker, tool broker, egress proxy, result guard, sensors, signed audit log.
- CELL (untrusted pack): /in ro snapshot, /run/bridge socket, tmpfs.
- HUB (honest-but-curious): registry, certifier, log, escrow, run tokens, ranking, revocation list, relay.
- AUTHOR / HOST / PAYPAL / NEBIUS.

Pull run:
1. REQ-AGENT calls hub `browse_agents`; verifies signature, log inclusion, revocation, license, tested_on, driver tier.
2. REQ-HUMAN approves one card per (digest, mode, lens, budget) incl. "byte-exact lens preview" (phone via relay).
3. HUB issues one-time run token + PayPal AUTHORIZE (cap).
4. VAULTD stages ro snapshot of the lens slice to /in; canaries and decoys "outside the lens"; Broker mints Biscuit.
5. Driver starts Cell (--network none, socket only).
6. Cell runs plan -> work -> return; model calls and memory.search only via sidecar; D1-D14 run.
7. Result Guard (schema, size, inert render, canary/overlap scan), acceptance checks, human Accept.
8. Proposals -> Q.
9. Partial/final capture, payout after holdback, receipt, Cell destroyed.
Failure branch: deterministic hit -> ladder 4..9 (kill, quarantine, revoke, rollback U, notify, signed incident) + PayPal VOID + payout freeze.

Hosted run: mode select -> Compiler builds packet -> host quote + AUTHORIZE -> E2E packet via relay -> host runs same stack as root -> encrypted result + host receipt -> Result Guard -> split capture.

## 2. Per-step failure questions that produced findings (short log)

- Step 2/6: lens "byte-exact" but memory.search is query-time semantic filter, so the exact bytes visible are not known at approval. /in snapshot already holds the whole slice.
- Step 4: canaries "outside lens" cannot be reached by a Cell that only sees /in and a lens-filtered search; read path step 8 "injects" canaries, which makes them inside what the pack sees.
- Step 3/9: run token gates nothing unless pack content is withheld; Pull pack is on requester disk; manifest example is Apache-2.0 + open + $4/run.
- Step 7/9: acceptance checks, kill verdict, receipt, VOID trigger are all produced by the requester's supervisor; hub and author cannot verify. Requester can void or reject after reading the result locally.
- Ladder step 7: rollback of U after kill, though the pack cannot write U; merkle checkpoints are scheduled for phase 16; concurrent user/agent writes would be lost.
- Run twice concurrently: one Nebius pool (60 RPM default, no per-key caps), shared by hub certifier, GEPA, Hosted per-task keys and the demo.
- Hosted: host is root, sees per-task Nebius key; key budget cannot be enforced at Nebius (no per-key caps documented).
- Out of order: phone approval needs relay (phase 15) but demo path is phase 14; revocation list in phase 8, registry in phase 11; certifier security suite needs broker + detectors (6, 8) but lists 1, 2, 4.
- Offline: revocation check on "each broker call" with hub unreachable has no fail-open/closed rule. Conformance suite result is not re-checked per run.

## 3. Guarantee text vs mechanism (sentence audit)

| Sentence | Mechanism present? | Verdict |
|---|---|---|
| Pull: "the pack has no network interface" | --network none; driver conformance | True only if driver passed on that machine, checked per run (not designed); WSL2 pass UNVERIFIED |
| "Its only exit is a requester-owned sidecar" | unix socket; sidecar holds key | OK, but Pull key ownership vs "ZDR enabled by hub" contradictory (B5) |
| "The author receives nothing during the run" | no author endpoint | OK for the run. Update check, receipts, ratings go to hub; receipt allows "cost" (data-dependent) |
| "Not guaranteed: leakage via result text, tool args, search queries (detected not prevented)" | D6, D7 | D7 "taint" is substring overlap only (no CaMeL-style planner), claim of CaMeL/FIDES style is stronger than mechanism |
| Hosted: "only the approved packet leaves" | Compiler, preview | OK, plus Nebius key and prompts via host's sidecar; mode selector may send "tokenized private" items though text says "do not use for private data" |
| Sealed: "you can verify the pack build" | Nitro attestation | Needs reproducible build; no phase designs it (phase 16 spike) |
| Product sentence: "revenue per run" | PayPal hold + run token | No mechanism stops offline free use of an open Pull pack |
| Product sentence: "ranked on evidence", "anyone can recompute" | signed attestation log | Scores come from private suites; third party can recompute aggregation only |
| "Rank per (pack version, model)" via manifest tested_on | Certifier fills tested_on | Self-reference with digest (manifest is inside the digest) |
| "canary hit never affects reputation alone" | 7.3 rule | Contradicted by ladder: D2 alone => revoke proposal to hub + payout freeze + VOID |
| "Pack cannot write U" | vaultd gate | OK; but episodic auto-written by local agent from foreign output is laundering |
| "no dump, no enumeration" | no read_graph tool | Bypassed by /in snapshot of the whole lens slice |

## 4. Terms used but not defined or inconsistent
- host vs owner vs author (used interchangeably; Hosted split-capture implies different parties).
- "tier" used for pack tier (0/1), driver tier, license tier, trust tier, IP tier.
- "Sensor Hub", "Scribe session", "quarantine memory snapshot", "run token" (what it gates), "acceptance checks" (who runs them), "phase" (enforced how in one Cell), "stakes/strike" vs "slash".
- Detector numbering differs from research-v2/06 (arch D9 = research D10, etc.); anyone cross-reading will mis-map.
- Implementation language/runtime of vaultd, supervisor, sidecar never stated (Biscuit JS support UNVERIFIED).

## 5. Items asserted but never designed
Requester-agent loop and hub MCP surface; extractor pipeline; daily digest; run-token semantics; acceptance-check execution; reauthorize/long-run handling; fair-share queue for Nebius; refund policy for Hosted rejected results; per-run conformance probe; phase enforcement; revocation-list freshness policy; reproducible build for Sealed; Tavily (decisions.md add-on, absent from arch and conflicts with "no network tools in private-data runs"); workflow-grade harness (owner feedback this round; v2 still fixed plan/work/return; research-v3 not integrated); judge-accessible demo (Nebius requires a working demo URL per secondary source).

## 6. Hackathon-fit claims on UNVERIFIED rules
Nebius "must run on Nebius" (secondary blog) vs AWS-hosted hub (Amazon claim); Open Source and AWS Builder mini-challenge rules unread; PayPal prize categories unread; payer-id field for wash-trading UNVERIFIED; partner approval UNVERIFIED; Nebius resale/aggregation terms for hub-issued keys unread; Amazon deadline 23/10 and Nebius 30/10 are fixed even though "no calendar" build order has no mapping to a submission subset.

See the returned findings for ranked, concrete scenarios and fixes.
