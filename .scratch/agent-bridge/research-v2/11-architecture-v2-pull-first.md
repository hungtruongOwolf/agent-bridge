# agent-bridge architecture v2: pull-first (synthesis of research-v2 01-10)

Date 2026-10-07. Design synthesis, no new web facts. Claims inherit status from files 01-10; anything marked UNVERIFIED there stays UNVERIFIED here.

## Summary
Pull is the headline: the foreign pack (a signed, content-addressed Harness Pack) is downloaded and runs in a no-NIC sandbox ("cell") on the requester's machine next to the data. Its only exits are a requester-owned sidecar (model proxy + memory broker + tool broker + egress proxy + result guard) and a size-capped result channel. Nothing is sent to the author. Active defense (D1-D14 detectors, 9-step ladder) is a visible runtime feature. Hosted is secondary: Unsealed Hosted (honestly owner-visible) and optional Sealed Hosted (Nitro enclave, host-operator-only protection). Memory is four planes (U, P, H, T) with a quarantined "proposed" tier. Packs have a first-class lifecycle with a Certifier, eval-gated improvement, and a verifiable leaderboard.

## Key facts with sources
See files 01-10 for URLs. Load-bearing: Docker --network none; OpenShell supervisor-only egress (05); MINJA/AgentPoison/MEXTRA (01,02); screening rejected 0/360 poisoned memories (02); Berkeley RDI benchmark breaks (04); Nebius ZDR opt-in (10); TEE.fail (09); Claude Code users approve 93% of prompts (10).

## 1. Components (named)
Requester machine (all trusted, B1):
- bridge CLI + local web UI + MCP endpoint (any MCP client, incl. OpenClaw, as requester front end).
- Vault (plane U): Markdown + append-only hash-chained JSONL journal, Merkle checkpoints.
- Disclosure Compiler: derives minimum need, builds the Context Packet / lens, byte-exact preview, canaries.
- Cell Runtime with SandboxDriver interface (tiers: T1 hardened OCI in Linux VM [WSL2 distro on Win11 Home / Docker VM macOS / rootless Linux], T2 gVisor, T3 microVM microsandbox/Firecracker). Conformance suite of attack fixtures per driver; tier shown on listing.
- Sidecar (one process, separate container or host UDS, never reachable by the cell except via socket at /run/bridge): Model Proxy (holds requester Nebius key, fixed endpoint https://api.tokenfactory.nebius.com/v1/, model class fixed, token/USD/rpm caps, non-streaming optional), Memory Broker (memory.search MCP tool only, Biscuit capability), Tool Broker (OPA/Cedar policy, allowlisted tools, no network tools in private-data runs), Egress Proxy (default deny; normalized outbound comparison), Result Guard (schema, size cap, inert render, no links/markup), Sensor Hub (detectors), Audit Log (hash-chained, signed).
- Supervisor: owns kill/quarantine/revoke; the cell cannot touch it.
Hub (B2, honest-but-curious, sees metadata): Registry (signed cards, digests, versions), Certifier (separate sandboxes for pack and grader, private rotating suites, honeypots), Transparency Log (Ed25519 + hash chain; Sigstore/Rekor upgrade), Escrow (PayPal Orders v2 AUTHORIZE/CAPTURE/VOID + Payouts as MCP tools), Revocation List (signed), Ranking service, Run Token issuer, Hosted relay (E2E ciphertext).
Owner side: Pack Studio (bridge pack init/validate/eval/sign/publish), improvement loop (DSPy+GEPA), owner dashboard.
Hosted host (B3): bridge-host daemon running cells on owner/pool machine, or Sealed Hosted on Nitro Enclave (attestation verified client-side, KMS gated).
External: Nebius Token Factory (Nemotron; ZDR enabled as account setting), PayPal sandbox.

Trust boundaries: B1 requester (trusted); B4 cell (untrusted code, prompts, injected docs); B2 hub (metadata only; not content); B3 hosted host (root over plaintext unless Sealed); B5 Nebius (sees prompts, ZDR opt-in); B6 PayPal; B7 result path (untrusted text).

## 2. Pull mode, one task end to end
1. Discover: requester agent calls hub MCP browse_agents; listing shows digest, tier-0/1 (data-only vs code-bearing), cert per (version, model), cost, incident count, license, driver tier required.
2. Download pack by digest; verify Ed25519 signature, transparency log inclusion, revocation list, license gate (SPDX), recompute digest. Pack is data plus optional code; never executes outside a cell.
3. Approval card (one per digest+mode+lens+budget): requested capabilities vs grant (declared AND requester policy AND mode ceiling), lens, caps, byte-exact preview of the context slice. Diff-only re-approval on pack updates. Human gates only for irreversible/durable actions.
4. Hub run token + PayPal AUTHORIZE hold at the capped price (hold is the metering anchor for Pull, since the author cannot meter).
5. Disclosure Compiler builds read-only staged snapshot at /in (copy inside VM, not host mount), forms: full / locally derived / tokenized / handle-only. Canaries placed OUTSIDE the granted lens as tripwires and inside planted decoy records at lens edge for the strike budget (see 10).
6. Cell starts: --network none, --read-only, cap-drop ALL, no-new-privileges, non-root, pids/mem caps, tmpfs scratch (plane T). Mounts: /in ro, /run/bridge (socket only). Phases (Rule of Two): planner (task spec, no files) -> worker (files, no network tools, no search) -> returner (schema output, no data access).
7. Model calls go to sidecar Model Proxy: key injected there; fixed endpoint; counts bytes; Result and tool args normalized and compared to the lens for overlap.
8. Memory reads only via memory.search through the broker: lens-scoped, k and byte budgets, provenance labels; no dump tool.
9. Detectors run continuously (section 5). On deterministic hit: ladder fires.
10. Returner emits result to /run/bridge; Result Guard: schema, size cap, inert render; requester reads preview; objective acceptance checks + Accept.
11. Capture (partial/final) to author; compute fee per policy; payout with holdback. Receipt signed by hub run token + requester; feeds verified runs.
12. Proposed memory writes from pack land in the "proposed" tier; user accepts/rejects. Cell destroyed, plane T wiped, vault checkpoint recorded; rollback available.
Guarantee: author receives nothing during the run (no NIC, no key). Residual: Nebius sees prompts; allowed-channel semantic leakage into result text/tool args; requester's own sharing; provider timing side channels; sandbox 0-day.

## 3. Hosted mode, one task end to end
Unsealed Hosted (default, honestly labelled "host can read your task package"): requester agent derives minimal task package (no vault access), E2E encrypt to host key, escrow AUTHORIZE per signed quote (cap), host daemon launches the same cell + sidecar on host with host-metered hours under cap, signed result + owner-attested log, requester guard + Accept, capture + payout to author and host. Verdicts and receipts are owner-attested; ranking does not treat them as proof of isolation.
Sealed Hosted (optional, roadmap/spike 2-4 days): pack runs in AWS Nitro enclave; attestation document (PCRs, nonce, public_key) verified client-side against the pack's published reproducible measurement; TLS to Nebius terminates inside enclave; per-task hub-issued Nebius key. Protects against host operator only; pack still sees plaintext; Nebius sees prompts; inside-enclave active defense. Label: three tiers Pull / Sealed Hosted / Unsealed Hosted. Never claim nobody can see data. Hosted exists for saving own compute and stronger setups, and for Protected packs whose owner will not ship code.

## 4. Memory design (four planes plus proposed tier)
- U user vault (local, source of truth). Files: Markdown notes with front-matter (source, trust tier, sensitivity, valid_at/invalid_at, ttl, lens tags, namespace) + append-only hash-chained JSONL event log with Merkle checkpoints; typed records profile, episodic, semantic (bi-temporal), procedural, artifact, secret. Namespaces: user/core, projects/*, agent/own, pack/<hash>/scratch, task/<id>. Index/extractor: Mem0 OSS (local or user-approved endpoint) after a one-day bake-off vs Graphiti/Cognee on a LongMemEval subset + our leak/poison tests. Write path: only the user and the local agent through a write gate (schema check, compare-and-swap versioning, CAS). Update rules: invalidate not delete; TTL and decay per item; crypto-shred for real deletion; rollback to checkpoint. Read path: namespace + sensitivity filter first, then slot cap per trust tier (bounded occupancy), then budgets.
- Lens: the unit of exposure per task, defined as user-chosen tags AND query-time semantic filter, compiled to a Biscuit capability (task id, pack hash, namespaces, field mask, quota, expiry), attenuable. Foreign pack never touches U directly.
- P pack-relationship memory: requester side only, per (pack digest); rating history, incident history, approved lens preferences. Not shared across packs of the same owner by default, never sent to the owner or hub except as optional opt-in aggregates.
- H harness procedural memory: ships inside the pack as versioned skill/prompt/few-shot files; changed only by the owner through the eval-gated improvement loop; raw requester data never enters H; requester lessons flow only as opt-in scrubbed feedback bundles with owner approval. Voyager-style skill library idea.
- T task scratch: tmpfs inside the cell, destroyed at end.
- Proposed tier: any output from foreign packs, web or document content. Never auto-promoted. Promotion needs schema check, provenance/corroboration rule, human approval for profile, procedural, secret writes. Split reader and scribe sessions (Rule of Two). Mixed-trust retrieval is capped, since screening alone failed (0/360).
- Multi-device: one logical vault per user, journal replicated over the E2E relay, per-device keys; permissioned views (query + field mask as caveats); root-key recovery is open.
- Hosted: packet only, no vault access; Pull-only items are marked excluded.
- Memory is context, not enforcement: enforcement is the broker and sandbox.

## 5. Active defense
Principle: prevent by construction (no NIC, broker-only I/O), deterministic detectors may kill, probabilistic guards only escalate. Content-safety models (Nemotron Safety Guard, Llama Guard) are NOT theft detectors; NeMo Guardrails execution rails/PII masks used as advisory score only.
Deterministic (kill-authorized unless noted):
D1 canary file/memory read outside lens (design: deny-and-continue with strike budget; kills at strike limit or when combined), D2 scope violation (path/namespace), D3 volume/enumeration (read accounting vs budget, query patterns), D4 egress attempt (any non-socket connect, DNS), D5 egress content overlap (outbound normalized vs lens: n-gram, encodings, canary strings), D6 taint-to-sink (lens-labelled data into tool args/results beyond schema, CaMeL/FIDES style), D7 tool-sequence violation (phase rule: read then network tool), D8 pack drift (manifest/digest/file hash change at runtime), D9 kernel rules (Tetragon where Linux VM; Signal + Override), D10 result-path anomalies (size, encoding, hidden fields), D11 model-proxy anomalies (endpoint/model/params change, budget), D12 sidecar tamper/socket abuse.
Probabilistic (pause/flag only): D13 guard model + NeMo Guardrails, D14 behavior baseline.
Kill authority attaches to egress/taint/boundary/tamper evidence, not canary reads alone.
Ladder: 1 log, 2 deny the call, 3 pause cell, 4 kill (destroy container/VM), 5 quarantine (pause-and-keep diff/logs, denylist pack digest locally), 6 revoke (sidecar drops keys, Biscuit revoked, PayPal VOID, payout freeze), 7 slash (only after second detector or human confirmation, with appeal), 8 notify user, 9 tamper-evident signed incident record + signed revocation list entry to hub; memory rolled back to pre-task checkpoint. CRITICAL deterministic hit fires 4-6, 8, 9 at once. False positives: measure FPR on honest reference packs before demo; deny-and-continue first; appeal with evidence bundle; canary framing by malicious requester handled by requiring attached evidence + requester-side-only canaries verified by log.
Hosted: sensors run under owner root; verdicts labelled owner-attested.
Regression: MINJA/MEXTRA/AgentPoison-style suite + red-team malicious reference pack + garak/PyRIT in publish CI; shown as attack theater.

## 6. Pack spec and harness lifecycle
Pack = directory: pack.yaml (author YAML, canonicalized to JSON for signing) + SKILL.md skills, AGENTS.md, subagent md, .mcp.json, evals/ (plugin-eval-shaped), optional code/. pack.yaml fields: name, version (SemVer; permission widening = MAJOR), tier (0 data-only, 1 code-bearing), runtime (adapter: builtin loop / mini-swe-agent / deepagents / OpenClaw / Claude Code), model {requires, tested_on (from real Nemotron eval runs), overlays per model}, capabilities (phase-scoped: planner/worker/returner; fs, tools, mcp, network: none by default), memory {reads lens tags, proposed_writes schema, procedural files}, evals {suite, gate thresholds, baseline: no-pack}, commercial {price, modes allowed [pull,hosted], license, ip_tier: open | licensed+watermark | split shell/brain | hosted-only}, provenance {sources pinned SHAs, builder id, SPDX}. Rule: manifest = request, grant = declared AND requester policy AND mode ceiling, enforced below the model.
Lifecycle: author (Pack Studio, templates, reuse upstream harnesses pinned) -> validate (JSON Schema, license gate, lint) -> capability eval vs no-pack baseline per model (pass@k and pass^k, 3+ runs, free graders first) + platform security suite (exfil/memory-theft fixtures, malicious pack acceptance test) in Certifier -> sign (Ed25519; in-toto/SLSA-shaped attestations; Sigstore later) -> publish immutable digest to registry + transparency log -> run (Pull/Hosted) -> verified feedback (receipt-bound ratings, incidents, opt-in scrubbed traces; A/B only on synthetic/consented tasks) -> improve: optimizer (DSPy + GEPA; Meta-Harness proposer stretch; data-only, no pickles) proposes candidate with parent lineage; private held-out regression with CI-aware promotion gates; owner reviews; never auto-publish -> deprecate/revoke (signed). Ranking: per (pack version, model) lower confidence bound of Certifier private-suite score; separate columns: quality CI, pass^k reliability, verified paid completions (captured+accepted, distinct payers, wash-trading rules), cost, safety incidents; stars secondary and bound to captures; anyone can recompute from signed attestations. Cold start: certified newcomer badge.

## 7. Protocols and libraries
MCP (Streamable HTTP hub, stdio/UDS sidecar), OpenAI-compatible Nebius API with Nemotron model IDs; Biscuit (or macaroons if JS binding fails); libsodium/@noble Ed25519, crypto_box E2E; RFC 9162-style Merkle; OPA/Cedar; Presidio/GLiNER; Mem0 OSS; DSPy+GEPA; NeMo Guardrails (advisory), NeMo Evaluator (spike); Docker Engine/Podman in WSL2, gVisor runsc, microsandbox/Firecracker; Tetragon; NVIDIA OpenShell (spike first); PayPal REST Orders v2/Payments v2/Payouts wrapped as MCP tools; Tavily optional (never in private-data runs).

## 8. Hackathon fit
Nebius x NVIDIA: Nemotron via Nebius as sole model, model-ID panel, Guardrails/Nemotron safety as advisory guards (only if verified available), before/after pack improvement on Nemotron. PayPal: signed quote, AUTHORIZE, objective checks + accept, partial capture, payout, quarantine causing auto-VOID + payout freeze. Amazon: AWS-hosted hub/Nitro sealed tier as AWS Builder angle; Open Source: Apache-2.0 repo with NOTICE.

## 9. Build order (dependency-ordered)
1 pack.yaml schema + digest + validator + license gate. 2 Reference packs: prompt-only, code-bearing, malicious. 3 SandboxDriver + conformance attack suite; T1 driver on WSL2; OpenShell spike. 4 Sidecar: model proxy, tool broker, egress proxy, audit log. 5 Vault + write gate + journal; Memory Broker + Biscuit lens. 6 Disclosure Compiler + preview + approval card. 7 Detector set + ladder + supervisor + incident record. 8 Result guard + proposed tier + promotion. 9 Pull end-to-end with CLI. 10 Eval runner + baseline, Certifier, sign/verify, transparency log, registry/card. 11 Hub, escrow, run tokens, receipts, ranking. 12 Improvement loop v1.0 to v1.1. 13 Hosted unsealed host daemon + relay. 14 Sealed Hosted spike. 15 UI: marketplace, console, node graph. 16 microVM tier, Sigstore, multi-device sync.

## Fit for agent-bridge / Recommendation
Adopt the above; Pull default for private data; Hosted labelled; IP tiers honest (Pull exposes pack content).

## Risks
See weaknesses list: shared-kernel escape, allowed-channel leakage, heuristic detection FPR/FNR, owner-attested Hosted, IP exposure in Pull, own-code volume, unverified deps.

## Open questions
Docker-in-WSL2 attack suite pass; OpenShell on Win11 Home and Nebius routing; Nebius per-key ZDR, Nemotron safety availability; Biscuit JS; lens definition tuning; promotion policy fatigue; eval private suite ownership; Pull-mode proof-of-use; sealed host operator.
