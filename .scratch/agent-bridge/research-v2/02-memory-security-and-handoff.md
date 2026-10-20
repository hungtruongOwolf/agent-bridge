# 02 Memory security and cross-agent context handoff (round 2)

Date: 2026-10-07. Scope: memory poisoning/extraction, defenses, minimal-disclosure handoff to a foreign agent, and a shared permissioned memory vault. Primary sources only; claims not read from a primary page are marked UNVERIFIED. Several arXiv IDs below are 2026 preprints (read via abstract pages only; not peer-reviewed as far as I could tell).

## Summary

1. Persistent memory is a second prompt-injection surface that survives sessions. Attacks need only normal queries (MINJA), a tiny poison rate (AgentPoison <0.1% poison, >80% ASR), or black-box prompts to dump other users' stored interactions (MEXTRA). Existing prompt-injection defenses do not cover it, and agents that write/retrieve memory more aggressively are more exploitable.
2. Content screening and trust-weighted ranking alone are weak (one 2026 study: a screening pipeline rejected 0 of 360 poisoned memories). What holds up is structural: write-time origin binding, scoped namespaces, bounded occupancy of untrusted entries at retrieval, snapshots/rollback, and human approval for durable writes.
3. For agent-bridge the strongest move is not to filter memory but to never let a foreign pack touch the durable vault: the pack gets a task-scoped, read-only, attenuated "context view" (capability) and writes only to its own ephemeral/pack-private scratch; anything it wants to keep goes through a proposal queue owned by the requester's own agent. This is the Rule-of-Two / CaMeL idea applied to memory.
4. Recommended design: a local-first User Memory Vault with typed, provenance-tagged, bi-temporal records; an append-only hash-chained (Merkle) journal as source of truth; per-namespace encryption; a Memory Broker (MCP resources + tools) that mints Biscuit/macaroon-style attenuated capabilities per task; a Disclosure Compiler that builds a Context Packet (minimal, tokenized/redacted, with canaries); and an Active Defense monitor (canaries, egress/volume accounting, kill + quarantine + revoke + record).
5. Guarantees stay honest: in Pull mode data never leaves the requester's machine, but the pack code is untrusted and shares the host, so sandbox strength matters; in Hosted mode anything in the Context Packet is visible to the host owner. Minimal disclosure reduces, not eliminates, that.

## Key facts with sources

### A. Attacks on agent memory
- MINJA: attacker injects malicious records through query-only interaction (no direct memory access), using "bridging steps" and a progressively-removed indication prompt so records get retrieved for victims' queries. Any user can do it. https://arxiv.org/abs/2503.03704 (abstract read; success percentages not in what I read, UNVERIFIED numbers).
- AgentPoison: poisons long-term memory or RAG knowledge base with an optimized trigger; avg ASR >80%, benign impact <1%, poison rate <0.1%; tested on driving, QA and EHR agents. https://arxiv.org/abs/2407.12784
- MEXTRA (Unveiling Privacy Risks in LLM Agent Memory, ACL 2025): black-box prompts extract private user-agent interactions stored in memory used as demonstrations. https://arxiv.org/abs/2502.13172 . This is the direct analogue of "foreign pack steals the requester's memory".
- Systematic study: four memory write channels, nine structural vulnerabilities, six attack classes, benchmark MPBench; existing prompt-injection defenses fail to cover memory poisoning; more aggressive memory writers are more exploitable. https://arxiv.org/abs/2606.04329
- Utility Under Attack: poisoning 1.2% of a LongMemEval corpus drops accuracy 0.850 to 0.300; a multi-stage content screen rejected 0/360 poisoned memories; provenance-weighted ranking showed no meaningful defense (p=0.80) and stronger weights suppress legitimate untrusted evidence; authors propose bounded occupancy at retrieval instead of weights. https://arxiv.org/abs/2608.21230
- OWASP ASI06 Memory and Context Poisoning (OWASP Top 10 for Agentic Applications): persists across sessions, patterns include RAG/embedding poisoning, shared-context poisoning, long-term drift, cross-agent propagation; listed mitigations: validate writes, segment memory by user/task/domain, provenance + trust decay/expiry, do not auto re-ingest agent outputs into trusted memory, snapshots and rollback. I read only a secondary summary (https://vectorize.io/articles/owasp-asi06); the primary OWASP document was not fetched, so treat the list as UNVERIFIED against the original.
- Lethal trifecta (private data + untrusted content + external communication): no reliable 100% detection; only avoid combining all three. https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- Agents Rule of Two (Meta): at most two of {untrusted inputs, sensitive data/systems, state change/external comms} per session; all three requires a fresh context or human-in-the-loop. https://ai.meta.com/blog/practical-ai-agent-security/
- CaMeL (Google): separates control and data flow, capabilities on values, policy enforced at tool calls; 77% AgentDojo tasks with provable security vs 84% undefended. https://arxiv.org/abs/2503.18813

### B. Defenses and their evidence
- Write-time origin binding plus corroboration-gated trust elevation, and provenance-capped belief (trust bounded by source, not by text confidence) resist volumetric poisoning: https://arxiv.org/abs/2606.22030 (abstract-level only). Caveat from 2608.21230: provenance as a ranking weight is not enough; use caps/quotas.
- Mem0 scopes every memory by user_id / agent_id / run_id / app_id + metadata and tells integrators to always filter by them; add/update/delete are explicit; stores facts in SQL + vector + entity store. https://docs.mem0.ai/core-concepts/memory-types
- Letta memory blocks: label, description, value, character limit; `read_only` flag; a block can be shared by multiple agents with instant propagation; direct update replaces whole value so concurrent writes can lose data. https://docs.letta.com/guides/agents/memory-blocks . Lesson: read_only + sharing exist; versioning/CAS does not (our vault must add it).
- Zep/Graphiti: temporally aware knowledge graph retaining history (supports "update without destroying"); LongMemEval up to +18.5%, 90% lower latency. https://arxiv.org/abs/2501.13956 (paper CC BY-NC-SA; we copy the idea, not code).
- Append-only verifiable logs: Merkle trees with inclusion and consistency proofs (RFC 9162). https://datatracker.ietf.org/doc/html/rfc9162 . Directly usable for the memory journal.
- Detection: canary tool definitions with no legitimate call path = confirmed injection event with ~zero false positives; canaries are detect-only, not blockers (secondary sources: https://mcpservers.org/servers/dorianchn/agent-canary , search result summaries). Credential-exfil paper combines activation probes (needs open-weight model access), calibrated honeytokens and multi-turn cumulative information-flow accounting; authors say estimates have no formal guarantees. https://arxiv.org/abs/2606.04141

### C. Minimal-disclosure and scoped-view building blocks
- MCP Resources: URI-addressed, templates (RFC 6570), subscriptions, annotations (`audience`, `priority`, `lastModified`); spec only says servers MUST validate URIs and SHOULD implement access controls, so enforcement is ours. https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- MCP Roots: client exposes file:// roots, clients MUST only expose roots with appropriate permissions and validate paths; servers SHOULD respect them. Advisory to the server, so real enforcement must be the sandbox mount. https://modelcontextprotocol.io/specification/2025-06-18/client/roots
- MCP security best practices: no token passthrough, scope minimization with progressive elevation, per-client consent, sandbox local servers, egress proxy (Smokescreen) against SSRF. https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices
- Biscuit tokens: decentralized, public-key verified, offline attenuation, Datalog policies, Apache-2.0, libs in Rust/Python/Go/Java/C# (JS support UNVERIFIED). https://github.com/biscuit-auth/biscuit
- Macaroons: chained-HMAC bearer credentials with caveats (attenuation) and third-party caveats. https://research.google/pubs/macaroons-cookies-with-contextual-caveats-for-decentralized-authorization-in-the-cloud/
- SD-JWT (RFC 9901): salted-hash selective disclosure, holder reveals chosen claims, optional key binding (aud, nonce, sd_hash) against replay. https://www.rfc-editor.org/rfc/rfc9901 . Useful pattern for "signed vault record, reveal only these fields".
- Presidio anonymizer: operators replace/redact/mask/hash/encrypt, reversible via decrypt, custom operators. https://data-privacy-stack.github.io/presidio/anonymizer/ (redirected page; summary level).
- NVIDIA NeMo Guardrails (open source): input, retrieval, dialog, execution, output rails; Nemotron/NemoGuard safety model integration; jailbreak detection; PII detection through Presidio/GLiNER etc. with masking. https://docs.nvidia.com/nemo/guardrails/latest/index.html
- Llama-3.1-Nemotron-Safety-Guard-8B-v3: content-safety classifier for prompts and responses, 23 categories, 9 languages, supported in NeMo Guardrails, commercial use. https://build.nvidia.com/nvidia/llama-3_1-nemotron-safety-guard-8b-v3.md . It is a content-safety model, NOT an exfiltration or memory-theft detector. Whether it is hosted on Nebius Token Factory: UNVERIFIED.

## Fit for agent-bridge

Mapping to the round-1 trust boundaries: B4 (cell) is where a foreign pack lives; round 1 treated the cell as holding staged input only. Round 2 adds a durable memory the cell must never reach. The same cell + key-holding sidecar architecture extends to memory: the sidecar is the Memory Broker's enforcement point.

What NeMo Guardrails honestly gives us: execution rails on tool calls, PII masking via Presidio, Nemotron safety on inputs/outputs, jailbreak heuristics. What it does not give: egress control, memory provenance, theft detection. Use it as one layer inside the sidecar and label it probabilistic (Willison: a 95% detector is a failure in a security context). Good Nebius/NVIDIA story if it really runs; if Nemotron safety is not served on Nebius, run Guardrails with Nemotron generation model as self-check (UNVERIFIED, spike needed).

## Recommendation: concrete design

### 1. Memory model (the "Vault")
Local-first on the user's machine (encrypted at rest; key in OS keystore). Storage layers:
- Journal (source of truth): append-only, hash-chained, with periodic Merkle checkpoints (RFC 9162 style inclusion/consistency proofs) signed by the vault key. Every write is an event: `{id, ts, actor, pack_hash?, task_id?, op, record_id, content_hash, parent}`. Nothing is edited in place; update = new version + supersede link; delete = tombstone + crypto-shred of the payload key. Gives rollback to any checkpoint (OWASP-style snapshot/rollback) and tamper evidence.
- Record store (derived, rebuildable from journal): typed records, not free text blobs.
  - Types: `profile` (stable facts/preferences), `episodic` (task summaries), `semantic` (facts, graph edges with bi-temporal `valid_from/valid_to` and `recorded_at`, Graphiti-style), `procedural` (learned workflows/skills), `artifact` (files by hash), `secret` (never injected into any context; broker-only).
  - Every record carries: `namespace`, `sensitivity` (public/internal/private/secret), `provenance` (`user_authored | user_agent_observed | tool_output | foreign_pack_proposal | web`), `trust_tier` derived from provenance (NOT from content), `source_refs`, `confidence`, `ttl/decay`, `consent_basis`.
- Indexes: vector + keyword + entity, always filtered by namespace/sensitivity before ranking (Mem0 lesson), and with a bounded-occupancy rule: lower-trust tiers may fill at most k of the n retrieved slots and cannot override higher-tier records on the same key (2608.21230 lesson).
- Namespaces: `user/core`, `user/projects/<p>`, `agent/<own agent id>`, `pack/<pack_hash>/<scratch>` (foreign pack private scratch, deleted or archived per policy), `task/<task_id>` (ephemeral). Foreign packs can only ever have the last two.

### 2. Write path (anti-poisoning)
- Pack output never auto-enters trusted memory. A foreign pack (or any tool-derived content) produces `proposals` (`foreign_pack_proposal`, trust tier lowest). Promotion to `user/*` requires: (a) deterministic schema/type check, (b) provenance rule (at least one corroborating higher-tier source, or explicit human approval), (c) human review queue for durable `profile`/`procedural`/`secret` writes, shown as a diff with provenance. Procedural memory (instructions-like) is the highest-risk class: human approval always.
- Own agent writes in separate sessions from reading untrusted content (Rule of Two): the "reader" session that ingests web/pack results has no write tool for trusted namespaces; a "scribe" step extracts structured fields only (no raw instruction-like text), then the promotion gate applies.
- Quotas and rate limits per actor/namespace; anomaly alerts on bulk writes; never auto re-ingest agent outputs as trusted (OWASP mitigation, secondary source).
- Content screening (Guardrails/Nemotron safety) is run but treated as advisory signal only, given the 0/360 result.

### 3. Read path and handoff (the core of "no leak")
Pipeline for a task delegated to a foreign pack:
1. Task analysis (requester's own agent, trusted): derive the minimum need (fields, files, time window) from the task. Human can edit.
2. Disclosure Compiler builds a Context Packet, a signed, versioned, size-capped JSON document: `{packet_id, task_id, purpose, items:[{ref, kind, form, content, sensitivity, source}], redactions:[...], canaries:[...], expires, audience: pack_hash, hash}`. Each item is shown in one of four forms, picked per sensitivity: (i) full value, (ii) derived/summarized value computed locally, (iii) tokenized (stable pseudonyms `PERSON_1`, Presidio-style replace/encrypt operators; the token map stays in the requester vault and is reversed only on the returned result), (iv) handle only (opaque `ref://` the pack can ask the broker to dereference under policy, never the raw bytes). SD-JWT-style: items are individually salted and hashed in the signed packet so the pack can prove it received exactly these, and so later disclosures are by explicit reveal, not by default.
3. "What leaves/what the pack can see" preview shown to the human (byte-exact, from round 1) with sensitivity labels.
4. Capability minting: the Memory Broker issues an attenuated capability (Biscuit preferred for offline attenuation and Datalog caveats; macaroon fallback) bound to `{task_id, pack_hash, audience, namespaces, record_ids/queries, max_reads, max_bytes, expiry, mode}`. Caveats can only narrow. Revocation list checked by broker per call.
5. Pack access paths, by mode:
   - Pull mode: pack runs in the requester's sandbox. Context arrives as MCP resources served by the sidecar broker (`bridge://task/<id>/context/<ref>`), with `audience`/`priority` annotations, plus read-only mounted files. The broker is the only reader of the vault; the sandbox has no network except broker and model proxy. MCP Roots are advisory, so enforcement is the mount plus broker capability, not the root list.
   - Hosted mode: only the compiled packet crosses the wire (E2E to the owner daemon); the pack never gets a vault handle. Guarantee: everything in the packet is visible to the host owner. So packet minimization is the only protection; mark sensitive items "Pull only" and refuse to include them in Hosted packets.
6. Return path: result = schema-validated structured output + optional proposals; rendered inert; token map reversal done locally; proposals go to the promotion gate.

### 4. Shared memory across the whole system (many agents/machines)
- One logical Vault per user, replicated across the user's machines (journal sync, E2E encrypted, relay sees ciphertext), with per-device keys and a user root key (recovery via user-held backup). Merge by journal event ordering (per-record version vector); conflicts on the same record produce a conflict event for human/agent resolution (Letta whole-value-overwrite lesson).
- Principals: user, user's own agents (trusted, broad but namespaced capabilities), foreign packs (untrusted, task-scoped), other users (never direct vault access; only signed shared bundles). Every principal reads through the Broker with a capability; there is no raw DB access.
- Views, not copies: permissioned "views" are named queries plus field masks (e.g. `coding-style-view`: procedural records tagged `style`, sensitivity <= internal). A view is just the caveat set in a Biscuit; the same vault serves many agents without duplicating data.
- Owner-side memory (pack improvement) is separate: a pack's own learnings live in the pack's repo/namespace owned by the owner. Requester data never trains or seeds the owner's memory unless the requester opts in to a signed, redacted "feedback bundle" (also minimal disclosure). Hosted runs get fresh state per task.
- Cross-user memory in a marketplace (e.g. public reputation facts) is a separate public namespace with signed records, never mixed with private vaults.

### 5. Active defense (detect, kill, quarantine, revoke, record)
Signals (cheap and deterministic first):
- Canaries: per-packet honeytoken values and decoy resources/tools (a decoy `read_secret` or fake `.env`/`~/.ssh` file) with no legitimate access path; any touch or any appearance of a canary string in outbound traffic, tool args, or result = confirmed theft attempt (near-zero false positives, detect only, so pair with action below).
- Broker accounting: reads outside capability, repeated denials, enumerate-style queries, bytes read vs task need, high read-to-use ratio, cumulative information-flow budget per task (idea from 2606.04141, no formal guarantee).
- Egress: only broker/model proxy reachable; any other connect attempt, DNS lookup, or write to non-whitelisted sink = violation. Encoded exfil (base64/hex/chunked) caught by comparing outbound text against packet contents with normalization (fuzzy; label as heuristic).
- Model-side: NeMo Guardrails execution/output rails + Nemotron safety as advisory scoring (probabilistic).
Response, automatic and ordered: (1) freeze the cell (cgroup freeze) and cut broker access, (2) kill, (3) quarantine the transcript, workspace diff and any proposals under `quarantine/<task_id>` (never promoted), (4) revoke the capability and add pack_hash (and publisher key) to the local denylist, with a signed "theft report" sent to the hub for publisher suspension and listing flag, (5) record a signed journal event, (6) notify user with evidence, (7) escrow void/refund (ties to PayPal flow), (8) post-incident: check whether any memory write happened and roll back to the last pre-task checkpoint.
Honest limit: detection is best-effort; the hard guarantee comes from capability scoping + sandbox + not placing secrets in the packet. Do not claim "theft impossible".

### 6. Hackathon-facing slice
Demo-able pieces: tokenized packet with preview, Biscuit-scoped read of one record, canary trip kills a malicious pack with quarantine banner, journal verify + rollback of a poisoned proposal (MINJA-style poison blocked at the promotion gate). Nemotron on Nebius as the reader/scribe model; NeMo Guardrails execution/output rails as the NVIDIA fit if the spike confirms it runs.

## Risks
- Semantic leakage through allowed channels: the result text, tool args, or search queries can encode packet data; tokenization and diffs reduce but cannot prove absence. Pull mode shrinks the receiver set but the pack code is still untrusted code on the requester host (container escape, shared kernel on WSL2; round 1 risk).
- Detection is heuristic: Guardrails/safety models and canaries miss novel encodings; MPBench and 2608.21230 show screening alone fails.
- Tokenization breaks utility when the task needs the real value; the "handle only" and Pull-only classes shift the burden to the sandbox.
- Memory poisoning of the owner's pack (owner side) and of the requester's agent via results remain possible; the promotion gate relies on human attention (click-through fatigue).
- Complexity: bi-temporal records, Merkle journal, capabilities, multi-device sync is a lot of own code; Biscuit JS bindings and sync CRDT choices are UNVERIFIED; use existing libs (Biscuit, a Merkle log library, SQLite) rather than custom crypto.
- Several cited papers are 2026 preprints I only read at abstract level; numbers may not replicate.
- Hosted mode: the owner can read the packet; do not market it as private.
- Nemotron safety models are content-safety classifiers, not theft detectors; claiming otherwise would be inaccurate.

## Open questions
1. Is Llama-3.1-Nemotron-Safety-Guard / NemoGuard available on Nebius Token Factory, or must it be self-hosted (and then does it still satisfy the Nebius rule)? UNVERIFIED.
2. Biscuit JS/TS support level for our stack (Node daemon): official Rust/Python/Go/Java/C# listed; JS not confirmed. Fallback: macaroons via a vetted lib or Rust/WASM biscuit.
3. Which vault engine: build on SQLite + sqlite-vec with our journal, or adopt Mem0 (Apache-2.0 per repo, UNVERIFIED here) / Letta as the memory layer and wrap with our broker? Needs a spike comparing write-gate hook points.
4. Default policy for promotion: human review for every durable write is safe but tiring; what corroboration rule (k sources, trust tiers) is acceptable?
5. Multi-device sync: journal replication over the existing relay vs a CRDT library; recovery story for the root key.
6. How to evaluate the defense: build a small poisoning/extraction benchmark (MINJA-style, MEXTRA-style, canary-evasion encodings) as a regression suite; reuse MPBench if released and licensed (not verified).
7. Does the owner (publisher) side also need protection from requesters (reverse theft of pack prompts/skills)? Out of scope here, but pack obfuscation vs transparency interacts with the evaluation/ranking design (topic for the pack-lifecycle research).
