# agent-bridge architecture v2: harness-platform angle

Date: 2026-10-07. Based on round 1 (architecture-options.md) and research-v2 files 01-10. Claims inherit their source file's status; items marked UNVERIFIED are unverified there. Numbers for ranking, thresholds and fees are design proposals, not sourced.

## Summary

The product is the **Harness Pack**: a signed, content-addressed, versioned, eval-certified directory (agent + harness + skills + memory policy + capability request + price). Everything else (sandbox, broker, ledger, detectors, leaderboard) exists to run, judge and pay for packs without trusting them.

Headline rules:
1. Manifest = request, grant = intersection (declared AND requester policy AND mode ceiling), enforced below the model.
2. Pull is the private-data default: pack runs in a no-NIC cell on the requester machine; its only exit is a requester-owned sidecar (model proxy + memory broker + egress/result guard). Nothing is sent to the author.
3. Hosted is a separate, honestly labelled tier (owner is root; sealed variant via TEE later).
4. Memory is four planes (U user vault, P pack-relationship, H harness procedural, T task scratch). A foreign pack never writes durable memory; its output is a proposal.
5. Leaderboard ranks per (pack version, model) by the lower confidence bound of Certifier-run private-suite scores plus verified paid completions, recomputable from signed attestations.
6. Active defense: deterministic detectors (egress, taint, scope, volume, tamper, drift) may kill; probabilistic guards only escalate; canary reads are strikes, not kills.

## Key facts with sources (carried from round 2 digests; primary sources are cited in those files)

- Pack formats: no existing format covers capability budget + memory policy + price + provenance + eval gate. Agent Skills (SKILL.md, allowed-tools advisory), Claude Code plugin.json/evals, subagent frontmatter, A2A Agent Card (JWS), MCP, DSPy (research-v2/03).
- Memory attacks: MINJA 2503.03704, AgentPoison 2407.12784, MEXTRA 2502.13172; screening rejected 0/360 poisoned memories (2608.21230, abstract-level). Structural controls over content screening (02).
- Benchmarks are gameable: Berkeley RDI broke 8 agent benchmarks; shared grader environment is the root cause (04). GEPA in DSPy (MIT) is the default optimizer; Meta-Harness 2603.28052 stretch.
- Pull isolation: Docker `--internal` leaves gateway reachable; use `--network none` plus unix-socket sidecar; OpenShell (v0.1.2) has the supervisor-as-only-egress, `inference.local` keyless pattern (05, 07). Win11 Home: WSL2 distro with Docker Engine/Podman; no Windows Sandbox/Hyper-V (07).
- Nebius: OpenAI-compatible; ZDR is an opt-in account setting, off by default; no per-key scopes or spend caps documented, so the proxy enforces budgets (10). Nemotron Safety Guard is a content classifier, not an exfil detector (02, 06).
- PayPal: Orders v2 AUTHORIZE/capture/void works in sandbox; 29-day hold, 3-day honor; Payouts need approval for live; Agent Toolkit lacks authorize/void/payout so we wrap (08).
- Auto-mode classifier FPR/FNR and 93% approval click-through argue for few, diff-based approvals (10).

## Fit for agent-bridge

### 1. Pack spec (`pack.yaml`, canonicalized to JSON for signing)

Layout (reuses existing formats):
```
pack/
  pack.yaml            # manifest (new)
  AGENTS.md            # persona/instructions (reuse)
  skills/<n>/SKILL.md  # Agent Skills format (reuse)
  agents/*.md          # subagent frontmatter (reuse)
  .mcp.json            # tool servers (reuse), resolved to broker tools at grant time
  memory/              # H-plane: seed notes, procedural skills, versioned files
  evals/               # cases + graders (plugin-eval shaped)
  code/                # optional tier-1 scripts, run only in cell
  LICENSE, NOTICE, SBOM.json
```
Manifest fields:
- `id, name, version (semver), parent (digest, lineage), speciality[], tier: 0|1` (0 = no code).
- `runner`: adapter (`builtin-loop` v1; `openclaw`, `mini-swe-agent`, `deepagents` later) + pinned upstream refs (commit SHA, lockfile).
- `model`: `requires` (tool-calling, ctx), `tested_on[{model, cert_id, score_lcb}]`, per-model overlay files (no forks).
- `capabilities` (phase-scoped: plan / work / return): `fs.read[lens tags]`, `tools[]`, `net.egress[]` (default none), `memory.read lens`, `memory.propose types`, `limits {steps, wall, tokens, usd}`.
- `memory`: `h_plane` files, `learns_from_requesters: none | consented-redacted`, `proposed_write_types`.
- `modes`: `pull: allowed|required|forbidden`, `hosted: allowed|sealed-only|forbidden`; `shell/brain split` optional (public pull shell, hosted-only brain).
- `commercial`: `license (SPDX)`, `price {per_task|per_hour|subscription}`, `ip_tier: open|licensed-watermarked|split|hosted-only`.
- `evals.gate`: required deltas vs no-pack baseline, pass^k, security suite id.
- `provenance`: builder id, source digests, signatures.
Validator: `bridge pack validate` (JSON Schema + lint: path containment, no pickles, SPDX gate, forbidden capability combos such as private fs.read + net.egress, i.e. Rule of Two).
Digest = SHA-256 over canonical tree; versions immutable; any permission widening is MAJOR (own rule).

### 2. Lifecycle (harness+agent development, first class)

1. **Author**: `bridge pack init` from template or import an upstream harness (OpenClaw skill, mini-swe-agent config, deepagents) with pinned SHA and license check. Local dev loop = `bridge pack run --mode pull` against synthetic fixtures in the same sandbox the requester will use.
2. **Validate**: schema, lint, license gate, SBOM, secret scan.
3. **Test**: owner-side evals (free graders: regex, tool_used, file_exists; judge graders mostly hidden-slice). 3+ runs; pass@k and pass^k.
4. **Certify** (separate Certifier sandbox, distinct from pack cell and grader cell): runs platform-private rotating suites per speciality, no-pack baseline per model, security suite (exfil, memory-theft, MINJA/MEXTRA-style fixtures, canary evasion, garak/PyRIT red-team), honeypot tasks, a cheater-pack acceptance test (platform self-test that a known cheating pack fails). Emits in-toto-style attestation bound to pack digest + model + suite version.
5. **Sign**: Ed25519 owner key; hub countersigns the certification; append-only hash-chained transparency log (Sigstore/Rekor as upgrade path; do not claim it until integrated).
6. **Publish**: registry stores immutable digest + generated `card.json` (A2A-card-shaped: skills, price, tested_on, modes, tier). Account-age gate and automated vetting (ClawHub had 341 malicious skills).
7. **Run**: requester approval card per (digest, mode, lens, budget); diff-based re-approval on new versions.
8. **Feedback**: only signed receipts (result accepted/rejected, cost, violations, rating bound to a captured payment). No raw requester data. Optional consented redacted bundles (default off) for improvement.
9. **Improve** (offline owner loop): DSPy+GEPA proposes instruction/demo/skill-file candidates (data-only, no pickles) from synthetic + consented traces; private held-out regression gate with CI-aware promotion; permission-widening or memory-promotion needs owner review; child gets `parent` lineage; never auto-publish. Meta-Harness-style code proposer is stretch. Limit private-suite queries per pack to curb Goodhart.
10. **Deprecate/revoke**: signed revocation list consumed by all supervisors; hash denylist on quarantine.

### 3. Leaderboard and ranking

- Unit: (pack version, model). Columns separate, not blended: quality LCB (Certifier private suite), pass^k reliability, verified paid completions (escrow captured after acceptance, distinct payers, wash-trading rules, minimum price/non-refundable fee), cost per task, safety incidents, tier badge (0 vs 1), driver tier, mode.
- Ranking = LCB of Certifier score, then verified-volume as tiebreak/booster; stars secondary and bound to captured payments. Cold start: certified-but-unrated packs listed with "new" label and CI width shown. Free/open library packs: ranked by Certifier score only (weighting open question).
- Anyone can recompute from the signed attestation log. Hosted receipts are owner-attested and weighted lower or labelled.

### 4. Memory system (packs plug in via the broker)

Planes:
- **U User Vault** (local, requester). Canonical form: Markdown + append-only JSONL hash-chained journal (OpenClaw-compatible) with typed records (profile, episodic, semantic bi-temporal, procedural, artifact, secret); front-matter: source, trust tier, sensitivity, valid_at/invalid_at, ttl, lens tags, namespace (`user/core`, `projects/*`, `agent/own`, `pack/<hash>/scratch`, `task/<id>`). Index/extractor: Mem0 OSS or Graphiti/Cognee after a one-day bake-off with LongMemEval subset plus own leak tests (UNVERIFIED which wins). Extractor LLM runs locally or on user-approved endpoint. Writers: the user and the user's own local agent only.
- **P Pack-relationship memory** (requester side): what this pack did, ratings, accepted proposals, strike history; never shared across packs or to the owner.
- **H Harness procedural memory** (inside the pack, owner-owned): skills/prompts/demos as versioned files; changed only through the improve loop above; no raw requester data enters it.
- **T Task scratch**: tmpfs in the cell, destroyed at task end; proposals leave only via the result channel.
- **Proposed tier**: pack outputs, web and document content land here with provenance; never auto-promoted. Promotion gate: schema check, corroboration rule, mandatory human approval for profile/procedural/secret writes. Reader and scribe sessions separated (Rule of Two).

Update rules: invalidate rather than delete (bi-temporal); TTL and decay per item; crypto-shred for hard delete; compare-and-swap on writes; rollback to pre-task checkpoint (Merkle checkpoints); bounded occupancy at retrieval (cap slots lower-trust tiers can fill) instead of relying on content screening.

Read path: pack calls `memory.search` (MCP) at the Memory Broker; no dump tool (`read_graph` never exposed). Broker enforces lens (namespaces + tags + sensitivity), k and byte budgets, provenance labels, canary placement outside the granted lens, per-task read accounting. Capability = Biscuit/macaroon token bound to task, pack digest, namespaces, quota, expiry (Biscuit JS support UNVERIFIED; fallback macaroons or Rust/WASM binding).
Cross-device: one logical vault per user, journal replicated over the E2E relay with per-device keys; agents see permissioned views (named query + field mask), never raw DB.
Pull: memory served through the broker lens, pack has no writable persistent store. Hosted: only the Disclosure Compiler's packet (full / locally derived / tokenized / handle-only items), E2E encrypted, no vault access.

### 5. Architecture (components)

Requester machine:
- `bridge-requester` (UI, approvals, Disclosure Compiler with byte-exact preview, Presidio tokenization, result guard).
- `bridge-supervisor`: SandboxDriver (hardened OCI in WSL2/VM/native; microVM tier later), launches one cell per task, holds kill/quarantine.
- **Sidecar** (single trust boundary container, unix socket into the cell): Model Proxy (holds the requester's Nebius key, fixed endpoint and model class, call/byte/USD budgets, rpm/tpm limits, non-streaming option), Memory Broker, Tool Broker (OPA/Cedar-style sync policy), Egress/Result Guard, Detector Engine, hash-chained audit log.
- Vault + Memory Broker (above).
Cell: `--network none --read-only --cap-drop ALL no-new-privileges`, non-root, pid/mem caps; `/in` staged read-only snapshot, `/run/bridge` socket dir, tmpfs scratch, result returned over the socket.
Hub (AWS): Registry + transparency log, Relay (ciphertext), Escrow (PayPal AUTHORIZE/capture/void/payout wrapped as MCP tools), Certifier fleet, revocation list, web marketplace/observability UI (munder-difflin parts), public MCP.
Host machine (Hosted mode): `bridge-host` daemon + the same cell/sidecar stack under the owner's control; Sealed Hosted (Nitro Enclave, attestation, KMS gating) as later tier behind the same interface.
Libraries: libsodium + Ed25519, DSPy/GEPA, Mem0 OSS (candidate), Biscuit, Presidio, NeMo Guardrails (advisory guard), garak/PyRIT (CI), Fastify+SQLite hub, NATS or custom relay, OpenShell spike for sandbox.

Trust boundaries: (1) pack code to sidecar (untrusted to trusted); (2) requester machine to hub/relay (hub honest-but-curious, sees ciphertext and metadata); (3) requester to host in Hosted (host is root: whole packet exposed); (4) Certifier vs pack vs grader sandboxes; (5) vault to broker (write path closed to packs).

### 6. Data flow, one task end to end

**Pull** (private data):
1. Requester browses leaderboard, selects pack digest D, task, folder + lens. 2. Requester agent derives minimum need; Pull needs no packet. 3. Approval card (digest, mode=pull, lens, budget, capability intersection, diff vs last approved). 4. Hub issues one-time run token tied to a PayPal AUTHORIZE hold (signed quote, cap). 5. Supervisor fetches pack D (verifies signature, certification attestation, revocation list, license). 6. Stage read-only snapshot, start sidecar then cell. 7. Plan phase: pack calls model proxy and `memory.search`; work phase: tools via broker; return phase: result over socket. 8. Detectors run throughout. 9. Result guard (schema + inert render + egress-content match against taint/canary set); requester previews, runs objective acceptance checks, Accepts. 10. Proposed memory writes shown for review. 11. Capture partial/final, payout to author; signed receipt (no content) to hub; destroy cell, keep diff/logs only if quarantined. 12. Rating and feedback bound to the capture.
Author learns: only the signed receipt (digest, cost, outcome). No prompts, data, or memory.

**Hosted**:
1. Same selection; requester sees "Hosted: host sees the packet" label. 2. Disclosure Compiler builds signed Context Packet (minimum need; Pull-only items excluded; tokenization where possible; canaries) with byte-exact preview. 3. Quote from host (cap), AUTHORIZE. 4. Packet E2E encrypted through relay to host daemon. 5. Host runs the pack in the same cell stack (host's own Nebius key or hub per-task key with ZDR). 6. Result returns encrypted; host metering signed (owner-attested). 7. Requester result guard and acceptance, capture split author/host, payouts. 8. No vault access, no memory write beyond proposals. Verdicts and kill claims labelled owner-attested.

### 7. Modes and guarantees

| | Pull | Hosted | Sealed Hosted (later) |
|---|---|---|---|
| Data leaves requester | No (topology) | Yes, packet to host | Yes, to enclave only |
| Author sees data | No | Host owner = maybe author; sees all | Host operator cannot; pack code sees plaintext in enclave |
| Pack IP | Exposed to requester | Protected from requester | Protected |
| Metering | Hub run token + receipt (not DRM) | Host metered, capped | Host metered |
| Detection trust | Requester-run | Owner-attested | Attested enclave (partial) |
| Residual | Sandbox 0-day, result-channel leakage, provider side channels, Nebius sees prompts | Host is root | TEE.fail-class physical attacks, Nitro has no GPU so inference goes to Nebius |
Payment: both modes use platform as merchant of record, AUTHORIZE then partial/final capture or void, Payouts; production path PayPal multiparty (needs approval).

### 8. Active defense

Detectors (D1-D14 from file 06, adapted): D1 egress attempt (any connect outside socket), D2 egress content match (tainted/canary strings in outbound model prompts and tool args), D3 taint-to-sink, D4 scope violation (path outside lens), D5 volume/enumeration (broker read accounting), D6 tool-sequence policy, D7 pack drift (runtime hash vs manifest), D8 kernel rules (Tetragon where Linux, Signal+Override), D9 result-path anomaly, D10 sandbox tamper, D11 budget abuse, D12 memory-write attempts outside proposals, D13 guard model score (NeMo Guardrails/Llama or Nemotron safety, advisory), D14 behaviour baseline (advisory). Canary reads are strikes outside the lens (deny-and-continue, budgeted) not kills.
Ladder: log, deny, pause, kill, quarantine (keep diff+logs), revoke (sidecar drops keys, broker token invalid), notify requester, signed hash-chained incident record, denylist pack digest on hub (signed revocation list), void escrow and freeze payout; slash only after second detector or human confirmation; roll back memory to checkpoint. CRITICAL deterministic hit (D1-D4, D7, D10, D12) triggers kill+quarantine+revoke at once. False positives: measure on honest reference packs before demo; appeal path with evidence; authors may rerun in Certifier to contest.

### 9. Hackathon fit

Nebius x NVIDIA: runtime on Nemotron via Nebius, certified `tested_on` runs, before/after pack improvement demo; NeMo Guardrails as advisory detector and optional pack guard (state honestly it is not an exfil barrier). PayPal Agentic Commerce: signed quote, authorize/capture/void/payout as MCP tools, quarantine ending in auto-void. Amazon: AWS-hosted hub/relay, Nitro Enclave sealed tier proof, open-source license.

## Recommendation

Build in this order of dependency: manifest + digest + validator; SandboxDriver with attack-fixture conformance suite; sidecar (proxy, broker, guard, audit); vault + broker; detectors + ladder; Certifier + eval runner with baseline; signing + registry + transparency log; escrow; Hosted daemon; improvement loop; leaderboard; sealed tier. Publish a precise guarantee table and never claim "data stays safe" in Hosted.

## Risks

- Pull exposes pack IP; protection is licensing/watermarks/Hosted-only, not secrecy.
- Result-channel and prompt-channel leakage cannot be fully closed; claim block + detection.
- Manifest can lie; only enforcement counts.
- Eval gaming, Goodhart on private suites, judge variance, model drift.
- Heuristic detector FPs hurt honest authors; FNs on slow exfil.
- Large own-code surface (journal, capabilities, certifier); mitigated by phased build and reuse.
- Hosted receipts and verdicts are self-attested; hub is a trusted party (mitigate via log).
- Shared-kernel escape on WSL2; OpenShell young; Nebius ZDR per-account only.
- Wash trading and Sybils with sandbox PayPal identity.

## Open questions

- Which sandbox driver passes the attack suite on Win11 Home WSL2 (spike)? OpenShell on Windows and Nebius routing UNVERIFIED.
- Vault engine: own SQLite + journal vs wrap Mem0/Graphiti; Graphiti license UNVERIFIED.
- Biscuit JS support; fallback macaroons.
- Who holds and rotates private eval suites; who pays Certifier token cost.
- Does Nebius expose seed/determinism, Nemotron safety model, per-key ZDR? UNVERIFIED.
- Default promotion policy and approval fatigue thresholds.
- Split shell/brain expression and Pull code-bearing pack review policy.
- Lens definition: tags, semantic filter, or both.
- Devpost rules unreadable; prize criteria UNVERIFIED.
