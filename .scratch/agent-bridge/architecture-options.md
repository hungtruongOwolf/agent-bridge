# agent-bridge: architecture options and recommendation

Date: 2026-10-07. Synthesis of 3 designs, 3 judge reviews and research digests 01-13. Devpost rules for all three hackathons were unreadable (503) on 2026-10-07, so rule-dependent items are UNVERIFIED. Nemotron tool-calling on Nebius, Docker in WSL2 on Win11 Home, gVisor in WSL2, and PayPal Payouts in sandbox are UNVERIFIED until the day-2 spikes.

## 1. The three designs, compressed

| | Security-first | Demo-first | Reuse-first |
|---|---|---|---|
| Thesis | Honest threat model is the headline; "attack theater" proves controls | One vertical slice that always works on camera; security shown as attack theater | Glue only: ~90% pinned upstream OSS |
| Owner side | bridge-agentd daemon, own cell launcher, gVisor if possible, broker + model proxy + egress proxy as separate pieces | bridge-owner daemon, cell on Docker `--internal` net, one proxy+broker sidecar pair | Native OpenClaw as owner console + our OpenClaw plugin; cell + combined sidecar |
| Isolation | no network, ro rootfs, cap-drop, nested no-net python cell, Rule-of-Two phases, per-call manifest re-hash | `--internal` net, sidecars hold keys, Rule-of-Two named | same as Demo-first plus hash-chained audit in sidecar |
| Transport/crypto | Noise IK via relay | libsodium crypto_box + Ed25519, Noise later | NATS+JetStream (2h spike) else custom relay; libsodium |
| Requester protection | Presidio + token vault + byte-exact preview + dual-LLM quarantine | regex/Presidio preview, schema-validate result as text | Presidio + token map + preview |
| Audit | hash-chained log + verify command | events only | hash-chained log |
| Payment | PayPal AUTHORIZE, capture, void, payout as MCP tools | same, plus separate PayPal cut | same |
| UI | console from munder-difflin parts, polish cut | web app, node graph, ToolWaterfall, cost header, phone PWA | same as Demo-first, OpenClaw Control UI page |
| Demo | 3:45 | 2:50 | 3:30 |

## 2. Judge scores and fatal flaws

Scores (judge 1 / 2 / 3, average): Security-first 8 / 3.5 / 6.5 = 6.0. Demo-first 5 / 5.5 / 7.5 = 6.0. Reuse-first 6 / 5 / 6 = 5.7.

Judge 1 judged security rigor, judge 2 feasibility for 1-2 people in 3 weeks, judge 3 hackathon-judging fit. The split is the point: Security-first has the best ideas and the worst schedule risk; Demo-first has the best delivery odds and the thinnest security.

Fatal flaws to design around:
- All: requester confidentiality against the owner is not delivered in Hosted mode (owner is root). Any line like "data stays safe" or "only the result returns" is false. Claim only owner-host and requester-agent protection.
- All: audit logs, quotes and receipts are signed by owner-controlled daemons, so they are self-attested. Do not say "we show the receipts" as proof of isolation.
- Demo-first and Reuse-first: worker holds private data, reads untrusted content and has web search, so the lethal trifecta is not broken. Search is a live exfil channel.
- Security-first: too much own code for 3 weeks (Noise, vault, dual-LLM quarantine, nested cell, WebAuthn, gVisor); polish is cut against a "very polished" bar.
- Reuse-first: critical path depends on unverified OpenClaw plugin SDK and headless OpenClaw in a cell; "90% reuse" hides ~3k LOC plus a UI rewrite. OpenClaw is alpha with hundreds of advisories next to owner credentials.
- Demo-first: only one attack scene is on the never-cut list, so the security story is cuttable; separate "malicious listing" is staged.
- All: shared-kernel container isolation on WSL2; scripted fixtures show known controls only; demos over a likely 3:00 cap (only Demo-first fits); PayPal extension work to 11-10 not budgeted; two videos needed.

## 3. Recommended architecture: "Demo-first spine, Security-first proofs, Reuse-first sidecar"

Principles: (1) Demo-first scope and schedule. (2) Take only the cheap, high-visibility security items from Security-first: the guarantee/non-guarantee list, no-search-after-data phase rule, tool-less result quarantine (schema + inert render, no second LLM), hash-chained audit with verify and a tampered-line demo. (3) One combined sidecar (proxy + broker + audit) on a Docker `--internal` network, no host firewall rules. (4) No OpenClaw plugin dependency. OpenClaw is used only as an MCP client on the requester side (mcp.json) and, optionally, as an owner chat UI. Worker runner is mini-swe-agent or deepagents (both MIT, per research 04). (5) libsodium + Ed25519, no Noise. No custom crypto.

### 3.1 Component diagram (text)

```
 REQUESTER MACHINE (B1)                 AWS (B2, honest-but-curious)             OWNER WORKER (B3)  Linux: Docker Engine in WSL2 or EC2
+---------------------------+          +--------------------------------+       +------------------------------------------------+
| OpenClaw / PersonalJarvis |  MCP     | bridge-hub (Fastify+SQLite)    |       | bridge-owner daemon (Node)                     |
|  or web chat (Nemotron)   |--------->|  - Registry: signed Agent Cards|  WSS  |  - outbound WSS, Ed25519 identity              |
+---------------------------+          |    + price/speciality/pack_hash|<----->|  - verifies envelope, quote, pack hash         |
| bridge-requester          |  WSS     |  - Relay: ciphertext queue     |       |  - approval UI (local web + phone PWA)         |
|  - folder picker, regex/  |<-------->|  - Escrow: PayPal AUTH/CAP/    |       |  - launches 1 cell/task, builds result preview |
|    Presidio, local token  |          |    VOID/PAYOUT (sandbox)       |       |                                                |
|    vault, "what leaves"   |          |  - Public MCP (Streamable HTTP)|       |  +-- per-task Docker --internal network ------+ |
|    preview                |          |  - Web app: marketplace, node  |       |  | CELL (B4, untrusted pack)                  | |
|  - result guard: schema + |          |    graph, console, phone PWA   |       |  |  ro rootfs, cap-drop ALL, non-root, tmpfs  | |
|    inert render + accept  |          |  - SSE event stream            |       |  |  /in ro (staged input), /out write-only    | |
+---------------------------+          +--------------------------------+       |  |  only peer: SIDECAR                        | |
                                              |            |                    |  +------------------|-------------------------+ |
                                              v            v                    |  SIDECAR (holds keys): model proxy -> Nebius   |
                                         PayPal sandbox   (events)              |  tool broker (read_file, allowlisted Tavily),  |
                                                                                |  budgets, SSRF block, hash-chained audit log   |
                                                                                +------------------------------------------------+
                                                                                       Nebius Token Factory (B5)   PayPal (B6)
```

Task phases inside one pack run (Rule of Two): planner (task spec only, no files) -> worker (files, no search; or only search terms pre-declared in the plan) -> returner (schema-validated output, no data access).

### 3.2 Trust-boundary table

| Boundary | Party | Trusted for | Not trusted for | Control | Residual / honest label |
|---|---|---|---|---|---|
| B1 | Requester machine | Own data, approval | - | Local vault, preview, human accept | Human may click through |
| B2 | Hub + relay | Availability, payments, registry | Content | E2E ciphertext, signed envelopes + counter; hub holds PayPal secrets only | Sees metadata; single financial authority (sandbox merchant) |
| B3 | Owner host + daemon | Running tasks honestly (reputation, escrow) | Nothing in software | Labelled "owner-visible" on every listing | Owner is root and can read plaintext in Hosted mode. Not solved. Roadmap: Pull mode, Nitro Enclave / TDX + NVIDIA CC |
| B4 | Cell (pack, agent, injected docs) | Nothing | Everything | No egress except sidecar, no creds, ro /in, broker-only tools, caps, timeout, fresh state per task | Container escape (Docker says isolation may be incomplete); covert channels via search queries and result text; roadmap microVM / gVisor / Nebius Sandboxes |
| B5 | Nebius | Inference | Prompts are visible to it | ZDR enabled at org level; key only in sidecar | Provider sees prompts |
| B6 | PayPal | Payments | - | Cap in signed quote, not model-enforced | Sandbox only; production needs partner features |
| B7 | Result path | Nothing | Result content | Size cap, JSON-schema, no links/markup, rendered as text, human accept before capture | Semantic poisoning inside allowed fields |

Guarantee list (shown in README and UI): a foreign pack cannot reach the owner's files, secrets or network beyond the manifest; a foreign result cannot act on the requester's agent. Non-guarantees: owner cannot read what you send (Hosted); logs and receipts are owner-attested, not proof of isolation (no TEE); Nebius sees prompts.

### 3.3 Form factor decision

CLI + daemon + web hybrid, no Electron. Owner: `bridge-owner` daemon on Linux (Docker Engine in WSL2 Ubuntu, or EC2 fallback) with a phone approval PWA from the hub. Requester: `bridge` CLI + localhost page + hub MCP endpoint usable from OpenClaw or any MCP client. Hosted web app on one small AWS EC2 (docker compose + Caddy): marketplace, console/node graph, approval PWA. Voice is a bonus clip only, never in the approval path.

### 3.4 Reuse list

| Reuse | License | Parts used |
|---|---|---|
| OpenClaw (pinned tag, not forked) | MIT | Requester-side MCP client via mcp.json; optional owner chat UI. Not the isolation boundary |
| mini-swe-agent / deepagents | MIT | Worker runner inside cell |
| wshobson/agents | MIT | Pack content for analyst/researcher (pinned SHA) |
| anthropics/skills | Apache-2.0 parts only | Skills; NOT docx/pdf/pptx/xlsx (source-available) |
| A2A Agent Card + task state names | Apache-2.0 (LF) | Listing schema and state machine; no A2A server |
| MCP SDK | MIT | Hub MCP server, broker, payment tools |
| libsodium-wrappers, @noble/curves | ISC / MIT | E2E boxes, Ed25519 |
| Microsoft Presidio | MIT | PII detection (spike), else regex |
| munder-difflin | MIT code (LimeZu art NOT redistributable) | Tokens, PixelPanel, ToolWaterfall, ThreadsPanel, BlockedBanner, AgentCard; procedural sprites; no PostHog; pin SHA, attribute in NOTICE |
| Docker Engine | Apache-2.0 | Cells and `--internal` network |
| PayPal REST (Orders v2, Payments v2, Payouts), optional @paypal/mcp | PayPal terms / Apache-2.0 (UNVERIFIED) | Wrap authorize/capture/void/payout as our MCP tools |
| Nebius Token Factory + NVIDIA Nemotron | API | nemotron-3-super-120b-a12b / Nemotron-3_5-Lightning / Nano-30B-A3B, ID configurable |
| Tavily | API | Allowlisted search via broker |
| PersonalJarvis | Apache-2.0 | Optional MCP-client proof only; sherpa-onnx voice recipe if time |

Repo license Apache-2.0 from commit 1; NOTICE lists vendored code, SHAs, licenses. Own code: hub, relay (~300 lines), escrow glue, owner daemon, cell launcher, sidecar, requester guard, console, three packs' manifests.

### 3.5 Demo script (target 2:50, split screen requester / owner+cell, PayPal ledger overlay)

- 0:00-0:15 Hook and honest claim on one line; marketplace with 6 listings (labelled seeded vs 2 live), stars, verified-task counts, price, pack-hash badge, "owner-visible" label.
- 0:15-0:35 In OpenClaw (or web chat) ask "find me a top-rated data analyst under $5"; Nemotron calls browse_agents over MCP; open listing (permissions, caps).
- 0:35-0:55 Hire: signed quote, "what leaves your machine" preview, PayPal sandbox AUTHORIZE hold in ledger (requester agent drives authorize via MCP under the signed cap).
- 0:55-1:10 Owner phone PWA approval showing price, scope, folder.
- 1:10-1:55 Live run: node graph, cell spawns on `--internal` net, planner/worker/returner, ToolWaterfall, cost header with Nemotron model IDs, tokens, USD. Caption "real time N min".
- 1:55-2:15 Attack theater (3 fixtures, BlockedBanner): malicious pack reads ~/.ssh and curls out (denied); injected document ignored; poisoned result stripped/rejected by schema. Then "verify audit": chain passes, one tampered line fails.
- 2:15-2:40 Owner preview and release, requester preview and Accept; capture, payout, balances change; star appears bound to capture id. Void path in 5 seconds.
- 2:40-2:50 Honest slide: guarantees vs non-guarantees; roadmap Pull mode, TEE, microVM. Closing: "We do not claim the owner cannot read your data; we make sure the owner's agent cannot misuse it and a foreign result cannot hijack yours."
- Nebius cut stresses model-ID panel and Nemotron loop; PayPal cut stresses hold/capture/payout/void and agent-driven settlement. Do not say "data never leaves the owner's machine" as a requester-safety claim. Keep pre-recorded fallback; warm up Nebius; pre-fund sandbox.

### 3.6 Week-by-week plan

To 2026-10-30 (submit Nebius by 10-28):
- 10-07 to 10-09 binary spikes: (S1) Nebius `/v1/models?verbose=true` + 3-tool Nemotron loop on 3 model IDs, ZDR on; (S2) Docker Engine in WSL2 on Home, else EC2 owner; (S3) cell + sidecar on `--internal` net, malicious script blocked, runner (mini-swe-agent/deepagents) against sidecar base URL; (S4) PayPal sandbox authorize/capture/void/payout, request Payouts access; request Nebius Sandboxes Beta. Create Apache-2.0 repo + NOTICE.
- 10-10 to 10-16 vertical slice: hub (registry, relay, escrow), owner daemon, cell + sidecar with hash-chained audit, one pack (analyst) end to end with CLI requester, event feed, stub UI. Gate 10-16: if no end-to-end run, drop Amazon/Alexa and all new scope.
- 10-17 to 10-23 polish: marketplace/listing pages, hire flow, phone PWA, regex/Presidio preview, ported console + node graph, receipt-bound stars, seeded listings, second pack (code patcher), result guard, MCP registered in OpenClaw. Two machines running by 10-19.
- 10-24 to 10-27 hardening: three attack fixtures reproducible, failure paths (reject/timeout/void), rate-limit warm-up, per-listing timeout (OpenClaw 48h default irrelevant as it is not used), README with guarantees/non-guarantees, license check, record and edit video under 3:00 plus fallback run.
- 10-28 submit Nebius, fill feedback form; buffer to 10-30.

2026-10-29 to 11-12 (submit PayPal about 11-10):
- 10-29 to 11-03 PayPal depth: reauthorize for long tasks, payout receipts, balances panel, optional third pack, Pull-mode thin proof (same cell on requester machine) if time.
- 11-04 to 11-08 PayPal video (device shown, under 3:00), README for PayPal judges, re-read Official Rules once Devpost is back.
- 11-09 to 11-10 submit; 11-11/12 buffer (deadline 11-12 12:00 PT, one source says 2pm PT).

### 3.7 Cut line (in order)

1. Amazon/Alexa/OAuth endpoint. 2. Voice. 3. Pull-mode demo and TEE (diagram only). 4. Third pack and second live owner (keep 2 packs; fallback 1). 5. Presidio (keep regex/manual folder choice with same preview). 6. Phone PWA (owner web confirm). 7. Node graph (keep ToolWaterfall + ledger). 8. Seeded listings to 4. 9. Void-path demo (keep in docs). 10. NATS (custom relay; or in-memory relay for demo).

Never cut: cell on `--internal` net with key-holding sidecar; Nemotron via Nebius with visible model ID; manifest/pack hash check; hash-chained audit with verify; at least 2 of 3 attack scenes (target all 3); PayPal hold, capture, void, payout; result preview and accept gate; honest owner-visible labelling; public Apache-2.0 repo; final video.

## 4. Decisions the owner must still make

1. Sandbox host: accept Docker Engine in WSL2 on Win11 Home, or commit to an EC2 Linux owner now? (Affects the "runs on my own machine" story.)
2. Team size and hours/day available: is this solo? The plan assumes about 1.5 people.
3. Is one demo product reused across Nebius, PayPal and Amazon allowed, and do you want one repo for all three? (Rules UNVERIFIED.)
4. Hosted-only for the hackathon, with Pull mode as roadmap plus thin proof, or must Pull mode be in the demo?
5. Which pricing for the demo: fixed cap per task only (recommended), or per-hour metering?
6. Is the OpenClaw story required (requester MCP client only, as recommended) or must the owner run OpenClaw as the agent runtime inside the cell?
7. Are seeded listings acceptable if clearly labelled, and how many live owner machines (1 or 2) can you provide?
8. Do you have, or can you obtain by 10-09, PayPal Payouts sandbox access and Nebius Sandboxes Beta access?
9. Visual tone: pixel-art munder-difflin look or a cleaner enterprise look for PayPal judges?
10. Language for demo and voice: English only (Parakeet v3 likely lacks Vietnamese, UNVERIFIED)?
11. AWS: OK to host hub on EC2 now (needed for any AWS Builder claim and a hosted-demo URL)?
12. Is the honest "owner can read your data in Hosted mode" framing acceptable as the headline, versus pivoting the headline to Pull mode?

## 5. Amazon track: go/no-go

Conditional NO-GO for now, with a hard re-evaluation on 2026-10-16. Reasons: mini challenges (AWS Builder, Open Source) layer on a primary track (Alexa+ here), deadline is 2026-10-23, and the minimal path (public Streamable-HTTP MCP with OAuth 2.1 PKCE, RFC 9728 metadata, <500 ms round trip, async design) costs 1-1.5 days that compete with the Nebius submit on 10-28. Rules are UNVERIFIED (Devpost 503). Hosting the hub on AWS EC2 is free signal either way and keeps the option. Go only if on 10-16 the end-to-end run works and Devpost rules confirm mini challenges accept the project; otherwise drop and spend the days on polish and the PayPal cut.

## Sources

Internal research digests 01-13 under `.scratch/agent-bridge/research/`; primary sources they cite (OpenClaw repo/docs, Nebius docs, PayPal developer docs, A2A/MCP specs, Docker/gVisor/Firecracker docs). No new web facts were fetched for this synthesis.
