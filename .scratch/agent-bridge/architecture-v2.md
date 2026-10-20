# agent-bridge: architecture v2 (final synthesis)

Date: 2026-10-07. Inputs: round 1 (`architecture-options.md`), decisions.md ("Pivot", "Round 2 input"), research-v2 digests 01-10, three v2 designs (pull-first, harness-platform, memory-centric) and four judge reviews. Claims marked UNVERIFIED were not confirmed from primary sources. Devpost rules for all hackathons were unreadable (503), so prize-fit items are UNVERIFIED. Manifest fields, ranking weights, fee percentages and detector thresholds are our own proposals, not sourced.

One-sentence product (judge 3 said none of the designs had one): **agent-bridge lets you hire the best certified agent+harness pack for a job and run it next to your private data in a sandbox that has no way to phone home, and lets pack authors sell, improve and be ranked on evidence.** Requester incentive: a better harness than your own, without handing over your data. Owner incentive: revenue per run, a verified rank, and an improvement loop that makes the pack visibly better.

---

## 1. What changed vs round 1 and why

| Round 1 | Round 2 | Why |
|---|---|---|
| Remote execution on the owner's machine; harness and data stay with the owner | Marketplace of packs. Default is **Pull**: the foreign pack runs on the requester's machine beside the data. **Hosted** is the secondary mode | Owner requirement: the agent may read data but nothing is sent to a foreign pack. Pull makes that structural. |
| Cut line for a 3-week schedule; "keep core tiny" | No time constraint; build in dependency order | Owner input 2026-10-07. |
| Harness = "a folder with a prompt and tool list" | Harness+Agent pack is first class: manifest, digest, signing, certification, ranking, improvement loop, revocation | Round 1 under-covered it. |
| Memory = audit log and scratch | Memory is a designed subsystem: vault, brokered lens, quarantine tier, pack-relationship memory, harness procedural memory | Owner requirement: updatable, shareable, no leaks. |
| Security = isolation + approval + audit | Prevention by construction plus **active defense**: detect, kill, quarantine, revoke, record, roll back | Owner requirement. |
| Hosted mode was the main model, framed as "only the result returns" | Hosted is labelled honestly: the host owner is root and sees the packet. Three labels: Pull / Sealed Hosted / Unsealed Hosted | Round 1 fatal flaw: "only the result returns" is false when the host is root. |
| OpenClaw as base platform | OpenClaw only as an optional MCP client and front end; no plugin dependency | Round 1 judges: alpha, unverified SDK, advisories next to credentials. |

New principles carried from the judges:
1. "Nothing is sent to the foreign pack" is **structural only in Pull**. For the result channel it is detect-and-contain. In Hosted it becomes "only the packet you approved leaves". This text goes on every listing (judge 1, design 3 reframe).
2. Every outbound channel toward an author or the hub is a fixed schema, enum-only, size-capped, no free text (judge 1: receipts, ratings and feedback bundles were an unanalysed covert channel).
3. A driver whose conformance suite fails or is weak automatically downgrades the guarantee text shown (judge 1: no fallback claim downgrade).
4. Staged build of own code: minimal vault first, bi-temporal graph, multi-device sync and Merkle checkpoints behind interfaces (judge 2).

---

## 2. The three designs compressed, judge scores and fatal flaws

| Design | Headline | Scores (J1 / J2 / J3 / J4) | Best part | Main weakness |
|---|---|---|---|---|
| A. Pull-first | Cell with no NIC next to the data; active defense as visible feature; honest 3-label modes | 7 / 7.5 / 6 / 7 = 6.9 | Honest labelling, inert Result Guard, kill only on deterministic evidence, attack theater | Thin on harness-agent co-development; huge build; 9-scene demo |
| B. Harness-platform | The signed certified pack is the product | 6.5 / 8 / 6.5 / 6.5 = 6.9 | Pack lifecycle, digest lineage, attestation, Goodhart controls, v1.0 to v1.1 story | Receipts carry free-ish fields (covert channel); claims Hosted protects IP from requester (false); terse memory |
| C. Memory-centric | The user vault is the center | 7.5 / 8.5 / 5.5 / 6 = 6.9 | Typed per-record write policy, ordered read path, Reader/Scribe split, honest headline retraction, anti-framing rule | Marketplace becomes a guest; most own-code; memory is least demoable |

Fatal flaws shared by all three, and how v2 handles each:

| Flaw | v2 handling |
|---|---|
| Result channel is a bidirectional trust channel; guarantee is detect, not prevent | Say so on every listing. Result Guard, taint and overlap detectors, inert render. Never lead with "nothing leaves" without the qualifier. |
| Signed receipt / rating / feedback bundle is an unsanitised author-bound channel | Section 3.4 "author-bound channel schema": enum and integer fields only, supervisor-generated, packs cannot write any field; ratings are requester-written enum 1-5 plus fixed reason codes, no free text; feedback bundles opt-in, redacted, owner-visible to requester before send. |
| Pull depends on a shared-kernel container in WSL2 on Win11 Home; DrvFs, nested virt, Tetragon on WSL2 UNVERIFIED | Driver tiers with a conformance suite. Listing shows the driver tier. If a driver fails any fixture the UI downgrades to "weak isolation" and private-data Pull is refused for that driver. |
| Hosted claims about IP and kill verdicts are overstated | Hosted does not protect the pack from the host (host is root). Hosted protects the requester's local machine and the requester's agent, not the packet. Verdicts are labelled owner-attested. Protected-IP packs are Hosted-only only in the sense that the requester cannot copy them; the host can. |
| Memory auto-promotion on "2 corroborations" is gameable | Corroboration must come from independent **source classes** (local agent observation, user action, trusted tool output); anything derived from foreign pack output, web or documents never auto-promotes. |
| Nobody could say why a requester hires or an owner lists (judge 3) | One-sentence product above, cold-start plan in section 9 (our own reference packs seed supply), improvement lineage shown as visible delta. |
| No validation of memory poisoning defenses | Regression suite (MINJA/MEXTRA/canary-evasion style) is a build phase with measured results; claims stay "structural controls, measured on our suite". |
| Demo exceeds likely 3:00 cap and depends on a young stack | Section 9: 3:00 cut plus pre-recorded fallback clips for every live segment. |

---

## 3. Recommended architecture

Thesis: **Design B's product, Design A's security spine, Design C's memory model.** The pack is the product; the vault and broker are the infrastructure under it; active defense is the proof.

### 3.1 Component diagram (text)

```
 REQUESTER MACHINE (trusted, B1)                                HUB on AWS (honest-but-curious, B2)
+----------------------------------------------------+         +--------------------------------------------+
| bridge CLI / localhost web UI / MCP endpoint        |  HTTPS  | Registry (signed cards, immutable digests) |
|  (usable from OpenClaw or any MCP client)           |<------->| Certifier fleet (separate pack/grader      |
|                                                     |         |   sandboxes, private rotating suites)      |
| Local requester agent (Nemotron via Nebius)         |         | Transparency log (Ed25519 + hash chain)    |
|   Mode selector, Disclosure Compiler (byte-exact    |         | Escrow: PayPal Orders v2 AUTHORIZE/CAPTURE/|
|   preview, lens, canaries, Presidio tokenization)   |         |   VOID + Payouts, as MCP tools             |
|                                                     |         | Run-token issuer, Ranking, signed          |
| User Vault (vaultd): Markdown + hash-chained        |         |   Revocation List, E2E relay (ciphertext)  |
|   JSONL journal; derived SQLite index; Quarantine Q |         +--------------------------------------------+
|                                                     |                         ^
| Supervisor (kill / quarantine / revoke authority)   |                         | ciphertext + metadata only
|   SandboxDriver interface + conformance suite       |                         v
|                                                     |         HOST (Hosted mode, B3)
|   +---------------- Cell (untrusted pack, B4) ----+ |        +--------------------------------------------+
|   | --network none, ro rootfs, cap-drop ALL,      | |        | bridge-host daemon: same Cell + Sidecar    |
|   | no-new-privileges, non-root, pids/mem caps,   | |        | stack under the host owner's root.         |
|   | tmpfs scratch, /in = ro staged snapshot       | |        | Sealed Hosted = Nitro Enclave (optional).  |
|   | phases planner -> worker -> returner          | |        +--------------------------------------------+
|   +--------------------|--------------------------+ |
|                        | unix socket /run/bridge    |         NEBIUS Token Factory (B5, sees prompts)
|   Sidecar (requester-owned; the ONLY exit)          |-------->  https://api.tokenfactory.nebius.com/v1/
|    Model Proxy (holds key, fixed endpoint+model     |         PAYPAL (B6) via hub escrow only
|      class, token/USD/rpm caps, strips credentials) |
|    Memory Broker (memory.search only, Biscuit lens, |
|      read accounting, canaries, no dump tool)       |
|    Tool Broker (OPA/Cedar; no network tools in      |
|      private-data runs)                             |
|    Egress Proxy (default deny, normalized compare)  |
|    Result Guard (schema, size cap, inert render)    |
|    Sensor Hub + Detector Engine D1-D14              |
|    hash-chained signed Audit Log                    |
+----------------------------------------------------+
 OWNER SIDE: Pack Studio CLI (init, validate, eval, sign, publish, improve), dashboard, Hosted host daemon
```

Key split: the **Supervisor** (kill, quarantine, revoke) is a separate process from the Sidecar, so tampering with sensors cannot also disable the kill switch.

### 3.2 Trust-boundary table

| ID | Boundary | Trusted side | Untrusted side | What crosses | Enforced by |
|---|---|---|---|---|---|
| B1 | Requester machine | Vault, local agent, supervisor, sidecar | Everything else | Vault is written only by user and local agent | OS accounts, vaultd write gate |
| B2 | Requester to hub | Requester | Hub (honest-but-curious) | Pack cards, signed quotes, run tokens, content-free receipts (fixed schema) | TLS, schema validation on both sides; hub never gets vault content |
| B3 | Requester to Hosted host | Requester's local machine | Host operator (root) | Approved Context Packet only, E2E encrypted | Disclosure Compiler, byte-exact preview, Pull-only items excluded |
| B4 | Cell | Sidecar | Pack code and prompts | memory.search, model calls, result via one unix socket | No NIC, ro rootfs, caps dropped, driver conformance suite |
| B5 | Sidecar to Nebius | Sidecar | Nebius | Prompts and completions (Nebius sees them) | Fixed endpoint, ZDR account setting enabled by hub (opt-in at account level; per-key ZDR not documented), budgets in proxy |
| B6 | Hub to PayPal | Hub | PayPal | Order, capture, void, payout | Orders v2 sandbox; hub as merchant of record |
| B7 | Result path | Requester after Result Guard | Pack output | Text/files treated as untrusted data, never as instructions | Schema, size cap, inert render, Reader/Scribe split, proposed tier |
| B8 | Author-bound channels | Requester | Pack author | Nothing during run; later only fixed-schema receipts and opt-in feedback | Section 3.4 |
| B9 | Certifier | Hub | Pack and grader | Pack under test, scores | Separate sandboxes for pack and grader, private rotating ground truth |

### 3.3 Honest guarantee statement (printed on every listing)

- **Pull:** the pack has no network interface. Its only exit is a requester-owned sidecar. The author receives nothing during the run. Not guaranteed: leakage through the allowed result text, tool arguments or search queries (detected, not prevented); the requester's own later sharing; Nebius seeing prompts; provider timing/size side channels; sandbox 0-day. The pack's contents are visible to you.
- **Unsealed Hosted:** only the approved packet leaves your machine, and the host operator can read it. Do not use for private data.
- **Sealed Hosted:** the host operator cannot read the packet and you can verify the pack build by attestation. The pack code still sees plaintext, Nebius still sees prompts, and physical-attack classes (TEE.fail) mean only cloud hosts qualify.

### 3.4 Author-bound channel schema (new)

| Channel | Allowed content | Forbidden |
|---|---|---|
| Receipt (supervisor-generated, signed) | run id, pack digest, mode, duration bucket, token-count bucket, cost, detector verdict enum, acceptance result enum | Any string chosen by the pack, any counts finer than buckets that vary with data |
| Rating | integer 1-5 bound to a captured payment, reason code from a fixed list | Free text |
| Feedback bundle | Off by default. Opt-in per run, redacted by the Disclosure Compiler, shown byte-exact to the requester before send, stored by owner in the H plane only after owner approval | Raw vault content, pack-derived text not reviewed |
| Update check | Pack id and version query only | Any run identifiers |
| Hub metadata | Counts and digests | Content |

### 3.5 Library reuse vs build (details in section 8)

Reuse: SKILL.md, AGENTS.md, subagent frontmatter, `.mcp.json`, plugin-eval-shaped evals; Mem0 OSS (candidate, after bake-off); Biscuit (macaroons fallback); libsodium or @noble; OPA or Cedar; Presidio; DSPy+GEPA; NeMo Guardrails (advisory); Tetragon (Linux VM only); OpenShell (spike); mini-swe-agent and deepagents as runner adapters; garak and PyRIT in publish CI.
Build ourselves: Memory Broker, Disclosure Compiler, sidecar glue, detector set and ladder, Certifier, registry and log, escrow glue, vaultd write gate, Pack Studio.

---

## 4. Memory design (full)

Goal: context memory that is well structured, updates over time, is usable across the whole system (several agents, several machines) and never leaks to a foreign pack.

### 4.1 Planes and layers

| Plane | Name | Where | Owner / writer | Lifetime | Foreign pack access |
|---|---|---|---|---|---|
| **U** | User Vault | Requester machine (one logical vault per user, replicated to the user's own devices) | User and the local agent only, through vaultd | Long-lived | Only `memory.search` through the Broker lens; never the store |
| **Q** | Proposed / quarantine tier | Requester machine, separate namespace | Anything foreign: pack output, web, documents | Until accepted or expired | Never readable by packs; excluded from retrieval or capped to a few slots for the local agent |
| **P** | Pack-relationship memory | Requester machine only | Local agent | Per pack digest | None. Never shared across packs of one owner, never sent to owner or hub except opt-in aggregates (enum fields) |
| **H** | Harness procedural memory | Inside the pack (versioned files: skills, prompts, few-shot demos) | Pack owner only, through the eval-gated improvement loop | Per pack version | Read by the pack itself; no raw requester data may enter |
| **T** | Task scratch | tmpfs inside the Cell | The pack | Destroyed at task end | Own only |

U sub-layers (typed records):

| Type | Content | Write policy | Sensitivity default |
|---|---|---|---|
| profile | Stable facts, preferences | Human approval, batched in a daily digest | medium |
| episodic | Events, tasks, outcomes | Auto-written by the local agent only | low-medium |
| semantic | Facts, bi-temporal (`valid_at`, `invalid_at`), provenance to source episodes | Auto-promote only when source class is trusted-local; otherwise gate | per record |
| procedural | The user's own routines and skills | Human approval | low |
| artifact | Files and notes | Local agent or user | per file |
| secret | Credentials and the like | Human only; **never served to any pack**, handle-only | high |

Namespaces: `user/core`, `projects/<id>`, `agent/own`, `pack/<digest>/scratch`, `task/<id>`.

### 4.2 Record schema (vault schema version 1)

```yaml
# Markdown file with front-matter; canonical form. Journal holds the event that created it.
id: rec_01J...            # ULID
schema_version: 1         # vault schema, see 4.9
type: semantic            # profile|episodic|semantic|procedural|artifact|secret
ns: projects/atlas
source: {class: local-agent-observation, ref: journal:evt_881, tool: null}
trust_tier: 2             # 0 foreign/untrusted ... 3 user-authored
sensitivity: medium       # low|medium|high|secret
lens_tags: [project-atlas, finance]
valid_at: 2026-10-01T09:00:00Z
invalid_at: null          # set to invalidate; never delete
ttl: 2027-04-01           # decay / expiry
version: 7                # compare-and-swap
key_id: k_rec_...         # per-record key for crypto-shred
```
Journal line: `{seq, ts, actor, op, record_id, base_version, content_hash, prev_hash, sig}`. Merkle checkpoint (RFC 9162 style) every N events and before every task.

### 4.3 Write path

`capture event -> journal append -> extractor -> typed proposal -> schema check -> promotion gate -> record (CAS)`

- Only the user and the local agent (via the Scribe session) write to U. Compare-and-swap on `version`; version-vector for multi-device conflicts.
- Extractor LLM sees user data, so it runs locally (small model) or on an endpoint the user explicitly approved. Fallback plan: if local quality is poor, the user can approve Nebius Nemotron for extraction, with the UI stating that Nebius sees that text.
- **Promotion gate by type:**
  - episodic and low-sensitivity semantic: auto-promote only if the source class is trusted-local, or corroborated by **2+ independent source classes** (local observation, user action, trusted tool output). Content derived from the same foreign document counts as one source (fixes the judge 1 flaw).
  - profile, procedural, secret: always human approval, batched in a daily digest, with a "what changed" diff. Anything from Q needs per-item or per-diff acceptance.
  - Foreign pack output, web and document content: always Q, never auto-promoted.
- **Reader/Scribe split (Rule of Two):** the Reader session sees foreign content and has no vault write rights. The Scribe has write rights and sees only schema-validated proposals, never raw foreign text.
- No A-MEM-style note rewriting of U without the gate.

### 4.4 Read path (strict order)

1. Capability check (Biscuit: task, pack digest, namespaces, field mask, quota, expiry, mode).
2. Namespace and sensitivity filter (secret never; sensitivity ceiling from the lens).
3. Lens tag filter.
4. Rank.
5. Slot caps by trust tier (bounded occupancy: lower tiers fill at most a few slots; this is the structural defense because screening failed in the cited 2026 study, 0 of 360).
6. k and byte budgets.
7. Provenance label on every item.
8. Canary injection (canaries sit **outside** the granted lens).
9. Read accounting for the detectors.

Retrieval returns snippets or derived forms, not raw files, unless the capability allows. The local agent reads U in full, but every read is journalled. There is no dump, no enumeration, no `read_graph` tool for foreign packs (the MCP reference memory server has one; we must not expose it).

Lens = user-chosen tags AND a query-time semantic filter, intersected. The Disclosure Compiler shows the lens as a byte-exact preview before approval.

### 4.5 Update and forget rules

| Need | Rule |
|---|---|
| Fact changed | Set `invalid_at` on the old record, add a new one with provenance. Never edit in place. |
| Stale items | TTL and decay per record; consolidation ("dreaming") only from trusted sources with thresholded scoring. |
| True deletion | Crypto-shred: drop the per-record key; the journal keeps a tombstone hash. |
| After an incident | Roll back U to the pre-task Merkle checkpoint and discard Q items from that run. |
| Concurrent edit | CAS on `version`; conflicts surface to the user, not silently merged. |
| Bad extraction | Journal is the source of truth; the derived SQLite and vector index are rebuildable. |

### 4.6 Sharing across machines and agents

- One logical vault per user. The journal replicates between the user's devices over the E2E relay with per-device keys. Open: CRDT vs plain journal replication, root-key recovery (section 11).
- Agents see **permissioned views**: a named query plus a field mask, expressed as Biscuit caveats. No raw DB access for any agent but the local one.
- Visible user benefit (judge 3): the same lens-scoped context follows the user across their devices and across different hired packs without re-explaining, shown in the demo as "pack B already knows the project goal pack A produced, accepted into U by me".
- Cross-user sharing is out of scope for v2; two users share only through a Pull/Hosted task packet.
- Hosted: no vault capability; the Context Packet only, Pull-only items excluded.

### 4.7 P and H plane rules

- P: keyed by pack digest; holds ratings, accepted outputs, quirks, strike counts, lens preferences. Requester-side only. It exists to choose packs and tune lenses. This closes the author tracking vector.
- H: only the owner changes it, via the improvement loop (section 5.5). Requester lessons enter H only via opt-in, redacted feedback bundles that the owner approves.
- Pull packs get no writable persistent store; their only durable effect is proposals to Q.

### 4.8 Poisoning and leak defenses (summary)

| Threat | Defense | Honest status |
|---|---|---|
| Pack writes poison into U (MINJA) | Pack cannot write U; output lands in Q; human gate for durable types | Structural; tested on our regression suite |
| Poisoned retrieved web/doc content | Q tier covers web and documents too; bounded occupancy | Weak in literature for screening; we rely on structure |
| Dump/enumeration (MEXTRA) | No dump tool; k and byte budgets; enumeration detector D4 | Measured by suite |
| Semantic leakage via query text | Taint-to-sink, egress overlap | Detect, not prevent |
| Approval fatigue (93% approvals in Claude Code) | Human gates only for durable and irreversible writes; daily digest | Open UX risk |
| Tracking via pack relationship | P plane requester-only | Structural |
| Extractor sees data | Local or approved endpoint | Cost in quality |

### 4.9 Schema versioning and migration (added, judges 2)

Every record and journal line carries `schema_version`. Migrations are append-only: a migration is a journal event that writes a new-version record and invalidates the old one. The index is rebuilt after migration. Packs declare which `memory.search` response schema version they support; the Broker serves the highest mutually supported one.

### 4.10 Vault engine choice

Canonical store is ours (Markdown + journal). Mem0 OSS (Apache-2.0) is the candidate extractor/index, decided by a bake-off against Graphiti (Apache-2.0 per file 10) and Cognee (Apache-2.0) on a LongMemEval subset plus our own leak and poison tests. Vendor benchmark numbers (Mem0 LoCoMo 92.5, LongMemEval 94.4) are unreproduced. Staged cut: phase 1 ships Markdown + journal + CAS + Q + `memory.search`; bi-temporal graph, Merkle checkpoints, multi-device sync come behind interfaces later.

---

## 5. Harness + Agent pack design (full)

Definition: **the harness is the improvable artifact** (prompts, skills, planner/worker/returner policies, tool config, few-shot demos, optional code). **The agent is the model plus a runner executing that harness.** A pack is a content-addressed, signed, semver-versioned directory carrying the harness and a declaration of which model and runner it was tested with.

### 5.1 Layout

```
my-pack/
  pack.yaml            # manifest (author YAML; canonicalized to JSON for signing)
  AGENTS.md            # instructions (reused format)
  skills/<name>/SKILL.md   # Agent Skills spec (reused)
  agents/*.md          # subagent frontmatter (reused)
  .mcp.json            # tool servers requested (reused)
  memory/              # H plane seed files (procedural memory, demos)
  evals/               # plugin-eval-shaped cases and graders (regex, tool_used, tool_order, file_exists, llm); no custom-code graders
  code/                # tier 1 only; runs only inside a Cell
  LICENSE  NOTICE  SBOM.json
```
Digest = SHA-256 over a canonical tree (sorted paths, normalized line endings, JSON-canonicalized manifest). Published versions are immutable. `parent` holds the digest of the version it was derived from.

### 5.2 Manifest example

```yaml
id: acme/finance-analyst
version: 1.1.0
parent: sha256:9f3c...e1          # lineage
speciality: [finance, spreadsheets]
tier: 0                            # 0 data-only (no code), 1 code-bearing; ranked separately
runner: {adapter: builtin-plan-work-return, pinned: null}   # or mini-swe-agent / deepagents / openclaw / claude-code with pinned SHA
model:
  requires: {family: nemotron, min_context: 32000}
  tested_on:                       # filled by Certifier from real runs, not by author
    - {model: <nebius nemotron id>, certified_digest: sha256:..., score_lcb: 0.71}
  overlays: {<nebius nemotron id>: overlays/nemotron.md}
phases:
  plan:    {memory: {read: false},                       tools: [],                  network: none}
  work:    {memory: {read: [project-atlas, finance], max_sensitivity: medium}, tools: [read_file, py_sandbox], network: none}
  return:  {memory: {read: false}, tools: [], network: none, result_schema: schemas/result.json}
memory:
  proposes: {schema: schemas/proposal.json, max_items: 5}   # proposals only, land in Q
  learns_from_requesters: none     # none | consented-redacted
evals:
  suite: evals/
  gate: {baseline_delta_min: 0.10, pass_k: 3, security_suite: required}
modes: [pull, hosted]              # sealed added only after reproducible build
commercial:
  price: {per_run_usd: 4.00, hosted_per_hour_usd: 6.00}
  license: Apache-2.0              # SPDX
  ip_tier: open                    # open | licensed-watermarked | split-shell-brain | hosted-only
  refund: {acceptance_checks: [schema_valid, citations_present]}
provenance: {builder: bridge-studio@1.x, upstream: [{repo: ..., sha: ..., license: MIT}]}
```

**Core rule:** the manifest is a **request, never a grant**. Effective permission = declared AND requester policy AND mode ceiling, enforced by sandbox and broker below the model. `allowed-tools` style fields are advisory only. Any permission widening is a MAJOR version (our own rule; SemVer itself is silent). Minor = prompt/skill/demo changes inside the same permissions; patch = fixes.

### 5.3 Lifecycle

1. **Author.** `bridge pack init` from a template, or import an upstream harness with pinned SHA and license gate.
2. **Validate.** `bridge pack validate`: JSON Schema, path containment, SPDX gate (allow/warn/block), SBOM and secret scan, no pickles, pinned upstream refs.
3. **Test locally.** Free graders first, 3+ runs, no-pack baseline delta, pass@k and pass^k.
4. **Certify.** Hub Certifier runs in sandboxes separate from the grader (Berkeley RDI lesson, 8 benchmarks broken by shared environments, exposed answers and undefended judges): private rotating suites, per (pack version, model) no-pack baseline, platform-owned security suite (exfiltration and memory-theft fixtures, MINJA/MEXTRA, garak/PyRIT), honeypots, and a cheater-pack acceptance test (a deliberately gaming pack must be caught or the Certifier is broken).
5. **Sign.** Owner Ed25519 signature plus hub countersignature on the certification, in-toto/SLSA-shaped attestation bound to (digest, model, suite version), appended to our hash-chained transparency log. Sigstore/Rekor is an upgrade path and is not claimed until integrated.
6. **Publish.** Immutable digest plus generated `card.json`; account-age gate and automated vetting (ClawHub had 341 malicious skills, so vetting is mandatory).
7. **Run.** Pull or Hosted; one approval card per (digest, mode, lens, budget); diff-based re-approval on version change.
8. **Feedback.** Receipt-bound ratings, violations, refunds, acceptance results. Traces only from synthetic or consented tasks, never from Pull private data by default.
9. **Improve** (5.5).
10. **Deprecate / revoke.** Signed revocation list; supervisors check before every start and on each broker call.

### 5.4 Evaluation and ranking

- Only Certifier-run private suites count; never public benchmarks or owner-reported scores.
- Rank per **(pack version, model)** because harness portability across models is measured as poor (PromptBridge, arXiv 2605.26731; both read at abstract level).
- Primary score: **lower confidence bound** of private-suite results. Separate columns: quality CI, pass^k reliability, cost, safety incidents, verified paid completions, tier (0/1), driver tier, license tier.
- Verified paid completion = escrow captured **after** requester acceptance, from distinct payers, with wash-trading rules (minimum non-refundable fee, payer-diversity weighting). Stars secondary and bound to captures.
- Anyone can recompute the ranking from the signed attestation log. Hosted results are labelled owner-attested and cannot count as proof of isolation.
- New packs show "certified, unrated" with their CI; cold-start handled by our seeded reference packs.
- Suite authorship conflict of interest: suites are written by the platform, not by pack owners; suite versions rotate; query budget per owner against Goodhart (open: who authors per speciality, section 11).

### 5.5 Harness + agent co-development loop (the missing explicit piece)

```
          +--------------------------- owner approves, never auto-publish ---------------------------+
          v                                                                                          |
 pack vN (H files: prompts, skills, demos, phase policies)                                           |
   -> run on synthetic + consented tasks, and Certifier public-dev slice                             |
   -> traces -> optimizer (DSPy + GEPA; Meta-Harness-style code proposer is a stretch)               |
   -> candidate vN+1 (data-only edits to instructions, demos, skill files; JSON state, no pickles;   |
      parent = vN digest, lineage recorded)                                                          |
   -> private held-out regression, CI-aware promotion, security suite, leak test                     |
   -> Certifier re-run per model -> signed attestation -> publish -> ranking moves -----------------+
```
- The optimizer may edit only H-plane files and prompts, never permissions (permission widening is a separate human MAJOR bump).
- Improvement signal: Certifier suites and consented traces. The requester-side agent keeps P memory to choose packs and tune lenses; that never flows to the owner.
- Anti-Goodhart: private-suite query budget, suite rotation, a hidden slice, human review of the diff.
- Model side: when a new Nemotron version appears, the pack is re-certified; overlays (not forks) carry model-specific prompt changes.
- Open: GEPA/DSPy applied to a multi-phase planner/worker/returner harness needs a spike.

### 5.6 IP and revenue honesty

Pull exposes the full pack to the requester. Prompt secrecy is not achievable (extraction attacks succeed widely). IP tiers: `open` (value is curation, evals and updates), `licensed-watermarked` (per-licensee watermark, legal deterrent not DRM), `split-shell-brain` (public Pull-eligible shell, private Hosted-only brain; UNVERIFIED how to express and enforce), `hosted-only` (requester cannot copy, but the host can). No DRM claim anywhere in the product.

---

## 6. Modes (Pull and Hosted)

### 6.1 Mode selector
The local agent picks Pull when the lens includes sensitivity above a threshold or the pack is Pull-eligible. It picks Hosted only when the task needs stronger compute and the packet contains low-sensitivity or tokenized items. Pull-only items are automatically excluded from any Hosted packet. The user can always override toward the safer mode.

### 6.2 Pull flow (private data default)
1. Requester agent browses the hub MCP and picks a pack; verifies signature, log inclusion, revocation status, license, tested_on and driver tier.
2. Approval card once per (digest, mode, lens, budget) with byte-exact lens preview; phone approval via relay.
3. Hub issues a one-time run token and a PayPal AUTHORIZE hold at the capped price (the metering anchor, because the author cannot meter).
4. vaultd stages a read-only snapshot of the lens slice to `/in` inside the VM, with canaries and decoys outside the lens; the Broker mints the Biscuit.
5. Driver starts the Cell with no NIC; `/run/bridge` holds only the sidecar socket.
6. Phases planner -> worker -> returner; model calls and `memory.search` only via the sidecar; detectors run throughout.
7. Result Guard (schema, size, inert render, overlap/canary scan) then objective acceptance checks and Accept.
8. Pack proposals go to Q for review.
9. Partial/final capture, payout after holdback, signed content-free receipt (3.4). Cell destroyed, T wiped; quarantined runs keep diff and logs.

Guarantee: author receives nothing during the run. See 3.3 for non-guarantees. **Payment:** hub run token plus AUTHORIZE hold, partial capture on acceptance, Payouts to the author after holdback against the 180-day dispute window; optional subscription or licensed watermarked pack. Sandbox: Orders v2 and Payouts work; multiparty `platform_fees` and DELAYED disbursement need partner approval and are the production path (UNVERIFIED whether a hackathon account can get them).

### 6.3 Hosted flow (stronger machine)
1. Mode selector or user chooses Hosted; label "host sees the packet" shown first.
2. Disclosure Compiler builds the Context Packet (full / locally derived / tokenized / handle-only items, canaries) with byte-exact preview; Pull-only items excluded.
3. Host signs a quote with a cap; hub AUTHORIZE at the cap.
4. Packet E2E-encrypted through the relay to the host key (or to an enclave attestation key in Sealed).
5. Host runs the same Cell + Sidecar stack under its own root, host-metered under the cap; the model uses a hub-issued per-task Nebius key with budget.
6. Encrypted result plus host-signed receipt return; same Result Guard and promotion rules run on arrival. The requester treats the host as untrusted for everything but the declared packet.
7. Capture split between author and host, Payouts to both; void path when defense fires.

Guarantees: only the approved packet leaves; the host operator can read it; verdicts and meters are owner-attested; the host can copy the pack (so Hosted does not protect IP from the host). **Unsealed** has no privacy claim.

**Sealed Hosted (optional, later):** AWS Nitro Enclave, client-side attestation verification of a reproducible pack measurement, KMS key release gated by PCRs, TLS to Nebius terminated inside the enclave, in-enclave defense that wipes keys and signs an incident. Protects against the host operator only. Pack still sees plaintext; Nebius still sees prompts (no documented GPU path from Nitro, UNVERIFIED in primary docs); TEE.fail-class physical attacks mean cloud hosts only. A GPU confidential VM running local Nemotron (Azure NCCadsH100v5 or GCP A3 High) would keep prompts inside the TEE but costs, quotas and the hackathon rules on where Nemotron must run are UNVERIFIED.

Remaining Hosted gap (judge 1): a host can suppress incidents or falsify receipts and the requester cannot detect it without Sealed. Mitigation: hub spot-checks with canary tasks (known-answer and canary-tripwire tasks sent to hosts), and a host reputation column; this reduces but does not remove the gap.

---

## 7. Active defense spec

Principle: **prevent by construction, then deterministic detectors may kill, probabilistic guards only escalate.** Content-safety models (Nemotron Safety Guard, Llama Guard) are not theft detectors.

### 7.1 Detectors

| ID | Detector | Evidence type | Authority |
|---|---|---|---|
| D1 | Canary file/record read outside lens | boundary | Strike, deny-and-continue (an exploring LLM touches canaries) |
| D2 | Canary value in any outbound artifact (proxy request, result, proposal, tool arg) | egress/taint | **KILL** |
| D3 | Scope violation: path/namespace outside lens, expired or forged capability | boundary | Deny; repeated = strike |
| D4 | Volume / enumeration (budget breach, near-duplicate or wildcard searches, sequential id probing) | broker accounting | Deny, then pause |
| D5 | Egress attempt: any non-sidecar connect, DNS, non-allowlisted endpoint, pack-supplied credential | egress | **KILL** |
| D6 | Egress content overlap with lens (normalized, encodings, canary strings) | egress | Pause, KILL on confirmation (confirmation = second detector or user click, with a default timeout that defaults to kill for high-sensitivity) |
| D7 | Taint-to-sink: lens-labelled data into tool args/results beyond schema (CaMeL/FIDES style) | taint | Deny; kill if sink is external |
| D8 | Phase/tool-sequence violation (read sensitive then encode/compress then output; forbidden order) | policy | Pause |
| D9 | Pack drift: runtime file hashes differ from signed digest | tamper | **KILL** |
| D10 | Kernel rules (Tetragon with Signal + Override; mount, ptrace, raw socket, DrvFs remount) | kernel | **KILL**; Linux/eBPF only, WSL2 feasibility UNVERIFIED so on WSL2 rely on seccomp and driver flags until proven |
| D11 | Persistence/model-proxy anomaly: writes outside T, wrong endpoint/model/params, budget abuse | boundary | **KILL** for persistence or endpoint change; deny for budget |
| D12 | Sidecar tamper or socket abuse | tamper | **KILL** |
| D13 | Guard-model score (NeMo Guardrails rails, Nemotron Safety Guard or Llama Guard, Prompt Guard) | probabilistic | Advisory: pause or flag only |
| D14 | Behaviour baseline vs the pack's certified profile | probabilistic | Advisory: flag only |

Strike budget: 3 consecutive or 20 total denials escalate to pause (mirrors the documented auto-mode escalation pattern). Honeypot decoy tools count as strikes.

### 7.2 Response ladder

1 log; 2 deny and continue; 3 pause (freeze, keep state); 4 **kill** (destroy container/VM, drop sidecar keys, stop proxy); 5 **quarantine** (keep diff, logs, memory snapshot; local denylist of pack digest); 6 **revoke** (invalidate Biscuit and run token, sidecar drops keys, signed revocation proposal to hub); 7 roll back U to pre-task checkpoint and discard Q items from the run; 8 notify requester (and hub, content-free); 9 signed hash-chained incident record. Money: PayPal VOID of the open authorization and payout freeze on a deterministic CRITICAL; **slash** only after a second detector or human confirmation, with appeal.

CRITICAL deterministic hit (D2, D5, D9, D10 confirmed, D11, D12) executes 4 through 9 immediately.

### 7.3 False positives and anti-framing

- Measure FPR on honest reference packs (prompt-only, code-bearing) before any demo; target is reported, not assumed (no tuning data exists yet).
- A canary hit alone **never** affects author reputation. It must be corroborated by an egress or taint detector; canary placement and hit evidence are signed by the supervisor and log-verifiable (judge 1 and design 3 rule).
- Evidence bundle visible to the requester; appeal path for the author with re-run in the Certifier.
- Deny-and-continue before kill wherever evidence is only boundary-type.

### 7.4 Hosted
Sensors run under the host's supervisor, so verdicts are owner-attested and labelled so. Sealed adds in-enclave defense with measurement revocation.

### 7.5 What NVIDIA tooling is real

| Item | Status | Role |
|---|---|---|
| Nemotron via Nebius Token Factory (OpenAI-compatible) | Real, required by the hackathon | Agent model, extraction (with consent), judge |
| NeMo Guardrails | Real, Apache-2.0 (file 10); has input/retrieval/execution/output rails, Presidio/GLiNER PII masking, jailbreak and NemoGuard integrations | **Advisory scoring lane (D13) and PII masking in the Disclosure Compiler**; not an exfiltration barrier |
| Nemotron Safety Guard 8B v3 | Real open model; content-safety classifier (23 categories) | Advisory only; availability on Nebius Token Factory UNVERIFIED (docs list none; secondary listing shows Llama-Guard-3-8B, unverified); otherwise self-host (hardware cost) or skip |
| NVIDIA OpenShell v0.1.2 | Real, young; supervisor-only egress, inference.local credential pattern | First sandbox spike; Windows 11 Home and Nebius routing UNVERIFIED |
| NeMo Evaluator (Apache-2.0) | Real; agent-eval fit only README-verified | Spike as an eval runner option |
| NVIDIA confidential computing (H100 GPU TEE) | Real hardware feature; availability behind Nebius UNVERIFIED | Roadmap only |

Do not claim detection of memory theft by NeMo Guardrails or Nemotron safety. Hackathon honesty point: NVIDIA depth is modest; show Nemotron model IDs in the cost header and the visible guard lane only if verified.

### 7.6 Regression and theater
MINJA/MEXTRA/AgentPoison-style suite plus canary-evasion fixtures run in publish CI and double as the attack theater. garak and PyRIT in publish CI. Known limits to state: covert timing and natural-language steganography cannot be fully closed; slow exfiltration may evade.

---

## 8. Reuse list with licenses

Licenses are from file 10 (`gh api`) unless marked.

| Item | Use | License |
|---|---|---|
| OpenClaw | Optional MCP client front end only | MIT |
| mini-swe-agent | Runner adapter | MIT |
| deepagents | Runner adapter | MIT |
| OpenHands | Reference / possible adapter | MIT |
| munder-difflin | Observability UI parts (node graph, tool waterfall) | MIT |
| PersonalJarvis | Voice reference (voice not used for approvals) | Apache-2.0 |
| Mem0 | Extractor/index candidate | Apache-2.0 |
| Graphiti | Bake-off candidate | Apache-2.0 |
| Cognee | Bake-off candidate | Apache-2.0 (file 01) |
| Letta | Reference for memory blocks | Apache-2.0 |
| NeMo Guardrails | Advisory rails, PII masking | Apache-2.0 |
| NeMo Evaluator | Eval runner option | Apache-2.0 (file 04) |
| NVIDIA OpenShell | Sandbox spike | UNVERIFIED (check repo LICENSE) |
| Biscuit | Capabilities | Apache-2.0 (JS support UNVERIFIED; fallback Rust/WASM or macaroons) |
| DSPy (incl. GEPA) | Improvement loop | MIT |
| Presidio | Tokenization/PII | MIT (UNVERIFIED in this run; confirm) |
| Tetragon | Kernel rules | Apache-2.0 (UNVERIFIED in this run; confirm) |
| gVisor, Firecracker | Hardened tiers | Apache-2.0 (UNVERIFIED in this run; confirm) |
| microsandbox | microVM candidate | Apache-2.0 (beta) |
| Anthropic srt | First-party packs only | Apache-2.0 |
| garak | Publish CI | Apache-2.0 |
| PyRIT | Publish CI | MIT |
| PayPal Agent Toolkit | Base only; no authorize/void/payout, wrap ourselves | Apache-2.0 |
| libsodium / @noble | Crypto | ISC / MIT (UNVERIFIED in this run) |
| OPA / Cedar | Tool Broker policy | Apache-2.0 (UNVERIFIED in this run) |
| claude-code | Not redistributable; dev-time only | Proprietary |
| anthropics/skills docx/pdf/pptx/xlsx | Do not bundle | Source-available, not redistributable |
| Nemotron models | Allowed with notices and attribution | Nemotron Open Model License |
| AGPL components | Avoid in Hosted (s.13 network clause) | n/a |

Anthropic Commercial Terms forbid reselling the Services. The product is open source (Open Source mini challenge) under an OSI license; marketplace hub code stays open.

---

## 9. Demo script (3:00 cap plus pre-recorded fallbacks)

Every live segment has a pre-recorded fallback clip recorded on the same machine; the live run is the default, the clip is a hot swap (judge 4: young stack, live failure likely). PayPal sandbox tokens expire in 3-8 hours, so mint tokens right before. Hosted and Sealed go in the long video, not the 3:00 cut.

| Time | Scene | What shows | Hackathon hook |
|---|---|---|---|
| 0:00-0:15 | Hook | One-sentence product; guarantee line "no network interface for the foreign pack" with the Pull qualifier | |
| 0:15-0:45 | Discover and hire | Nemotron agent calls `browse_agents` over MCP, picks the best certified pack under budget; listing shows (version, model) LCB, tier and driver badges, guarantee table; approval card with byte-exact lens preview; PayPal AUTHORIZE | Nebius x NVIDIA, PayPal |
| 0:45-1:15 | Run (Pull) | Cell with no NIC next to seeded private data; node graph and tool waterfall; cost header with Nemotron IDs; Result Guard, acceptance, Accept; partial capture and payout; accept one proposed memory item into U; next hire already uses that context (shared-context benefit) | Memory, PayPal |
| 1:15-2:00 | Attack theater | Malicious pack tries enumeration, DNS exfil, base64 canary in result. Canary strike, egress block, KILL, quarantine, revoke, memory rollback, signed incident, PayPal VOID, payout freeze; then `bridge audit verify` passes, a tampered line fails | PayPal agentic commerce, security |
| 2:00-2:35 | Pack lifecycle | v1.0 to v1.1 via GEPA on Nemotron via Nebius; held-out gate and leak test pass; new digest signed; leaderboard LCB moves | Nebius x NVIDIA |
| 2:35-3:00 | Close | Guarantees vs non-guarantees table (Pull, Unsealed, Sealed); open source; AWS-hosted hub | Amazon mini challenges |

Long video adds: Hosted with "host sees the packet" label, split capture, optional Sealed with tamper-changes-PCR scene, memory vault tour.

Cold start: seeded supply is our three reference packs (prompt-only, code-bearing, malicious) plus 2-3 imported open harnesses with pinned SHAs and clean licenses, certified on our suites so the leaderboard is not empty.

---

## 10. Dependency-ordered build phases (no calendar)

Each phase lists its prerequisite and exit test.

| # | Phase | Needs | Exit test |
|---|---|---|---|
| 0 | Foundations: glossary/ADRs, threat model, guarantee table, author-bound channel schema, canonical digest spec, Ed25519 sign/verify | none | Spec reviewed; sign/verify round trip |
| 1 | `pack.yaml` JSON Schema, `bridge pack validate`, license gate, SBOM/secret scan | 0 | Rejects bad fixtures |
| 2 | Three reference packs (prompt-only, code-bearing, malicious) | 1 | Fixtures usable in all later suites |
| 3 | SandboxDriver interface and attack-fixture conformance suite; T1 driver on a dedicated WSL2 distro; spikes: Docker Engine in WSL2 on Win11 Home, connect() to unix socket on ro bind mount, DrvFs/automount, OpenShell, microsandbox | 0 | Driver passes or is downgraded; results recorded as ADRs |
| 4 | Sidecar: model proxy (fixed endpoint, budgets), tool broker, egress proxy, Result Guard, hash-chained audit log, supervisor | 3 | Cell can only reach model through proxy; verify command detects tamper |
| 5 | Vault: record schema, journal, CAS write gate, namespaces, Q tier, rollback, schema versioning; vault engine bake-off (Mem0/Graphiti/Cognee) with leak/poison tests | 0 | Bake-off decision ADR |
| 6 | Memory Broker: Biscuit lens (or macaroons), `memory.search`, budgets, provenance, canaries, accounting | 4, 5 | MEXTRA/enumeration fixtures blocked or flagged |
| 7 | Disclosure Compiler, byte-exact preview, approval card, mode selector | 6 | Preview matches bytes staged |
| 8 | Detector set D1-D14, response ladder, revocation list, incident records; FPR measurement on honest packs | 4, 6 | Malicious pack killed; FPR reported |
| 9 | Pull end to end through CLI; proposal review and promotion gate; Reader/Scribe split | 2, 7, 8 | Honest pack completes; malicious pack ends in ladder |
| 10 | Eval runner with no-pack baseline; Certifier (separate pack/grader sandboxes, private suites, honeypots, cheater-pack test) | 1, 2, 4 | Cheater pack caught |
| 11 | Registry, signing, transparency log, `card.json`, ranking from attestations | 10 | Ranking recomputable by a third party |
| 12 | Hub escrow: PayPal authorize/capture/void/payout as MCP tools, run tokens, receipts, holdback, auto-void on quarantine | 9, 11 | Void and freeze fire on a malicious run |
| 13 | Improvement loop: DSPy+GEPA, held-out gate, lineage; spike for multi-phase harness | 10 | v1.0 to v1.1 passes gate and leak test |
| 14 | Requester UI: marketplace, console, node graph, live detector panel, phone approval PWA | 9, 11 | Demo path runs |
| 15 | Unsealed Hosted: host daemon, E2E relay, packet flow, owner-attested labels, canary spot checks | 7, 12 | Hosted run with cap and split capture |
| 16 | Sealed Hosted spike (Nitro), microVM driver tier, Sigstore, multi-device vault sync, Merkle checkpoint hardening, Meta-Harness proposer | 15 | Attestation verified client side; tamper changes PCR |
| 17 | Red-team CI (garak/PyRIT), honest-claims review of all copy, demo rehearsal with fallback clips | all | Claims table matches measured results |

Parallelizable: 3/4 with 5; 10 with 6-9; 14 with 12.

---

## 11. Decisions the owner must still make

1. **Primary headline:** marketplace-first (recommended), or security-first. Affects demo order.
2. **Vault engine:** accept the bake-off result, or fix SQLite + our own journal now.
3. **Capabilities library:** Biscuit (need JS/WASM confirmation) vs macaroons.
4. **Extractor model:** local small model, or Nebius Nemotron with consent (quality vs exposure).
5. **Promotion policy default:** how many independent source classes; daily digest vs per-item (approval fatigue).
6. **First runner adapters:** builtin loop first (recommended), then which of mini-swe-agent, deepagents, OpenClaw, Claude Code.
7. **Who authors private eval suites per speciality** without conflict of interest, and who pays Nemotron tokens for certification.
8. **Protected IP:** is a Hosted-only tier acceptable given it gives up the privacy selling point; invest in split shell/brain or not.
9. **Windows demo target:** WSL2-only, or also a Windows-native WFP path.
10. **Streaming:** require non-streaming model calls for private-data runs (side-channel mitigation) or accept streaming.
11. **Sealed Hosted:** build at all, and who operates sealed hosts (owner's AWS account vs marketplace pool).
12. **Multi-device sync:** journal replication vs CRDT; root-key recovery.
13. **Payments production path:** apply for PayPal partner/multiparty; fee percentages (10-15% harness, 5-10% compute are proposals only).
14. **Free and open packs in ranking:** how they weigh against verified-paid.
15. **Private-data Hosted-only items:** which sensitivity levels are Pull-only by default.

---

## 12. Amazon go/no-go

Amazon deadline is 23/10 per HACKATHONS.md; mini-challenge rules are UNVERIFIED (Devpost 503). Time is not a constraint for design quality, but the date still bounds which items can be shown for that submission.

| Item | Call | Reason |
|---|---|---|
| Open Source mini challenge | **GO** | Product is open source anyway; needs OSI license, README, NOTICE, clean upstream licenses (section 8). Cheap. |
| AWS Builder mini challenge | **GO** | Hub (registry, log, escrow, relay, Certifier) hosted on AWS; low marginal effort and honest fit. |
| Sealed Hosted on Nitro Enclaves as an Amazon showpiece | **CONDITIONAL** | Strong story (attestation, tamper changes PCR) and fits AWS, but no GPU path (UNVERIFIED), Nebius still sees prompts, 2-4 day estimate is ours. Do it only after phase 15; show as long-video clip, not core claim. |
| Alexa+ | **NO-GO (stay on hold)** | Owner has no Echo device; voice approvals rejected as a security action; simulated app adds no credibility. |

Overall hackathon fit: Nebius x NVIDIA is satisfied by Nemotron via Nebius as the real agent model plus the visible v1.0 to v1.1 improvement; NVIDIA tooling depth is modest and must be described honestly (7.5). PayPal fit is strongest in the AUTHORIZE-hold, capture, VOID-on-attack story. Prize-category text is UNVERIFIED.
