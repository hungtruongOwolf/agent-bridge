# 01 - Agent memory systems and how to update them (Round 2)

Researched 2026-10-07. Method: WebFetch of arXiv abstracts, GitHub READMEs, official docs. Pages were summarized by a fetch tool, so numbers are as reported by the sources (vendor benchmarks are vendor-reported, not independently reproduced). Nothing was installed or run. UNVERIFIED marks anything I did not see in a primary source.

## Summary

Memory in agent systems has converged on one taxonomy (CoALA: working, episodic, semantic, procedural) and three storage shapes: plain files (Claude Code, OpenClaw), vector stores with LLM-driven extraction (Mem0, LangMem), and temporal knowledge graphs (Zep/Graphiti, Cognee). The write path is the hard part: extract, dedupe, resolve conflicts, decay. The best-documented approaches do not delete on conflict; they invalidate with validity windows (Graphiti) or accumulate and rank at read time (Mem0's April 2026 ADD-only algorithm).

For agent-bridge the decisive point is not which library, but WHO MAY WRITE WHERE. Research on memory attacks (MINJA, AgentPoison) shows that any memory a foreign agent can write to and later retrieve from is an injection channel, and that a read tool that dumps the store is a theft channel. So the design is three planes with strict write ownership: (U) user-owned memory in a local vault that no foreign pack can write and can only read through a brokered, budgeted, scoped, canary-instrumented query; (H) harness-owned procedural memory that lives inside the pack, is versioned, and is changed only by the owner through an eval-gated improvement loop, never during a run; (T) per-task scratch that is destroyed at task end and returns only a typed "memory proposal" which the requester's side may accept or drop.

Recommendation in one line: files as canonical format (OpenClaw/Claude Code style, diffable, auditable) + Mem0 OSS (or Graphiti) as a derived index and extractor, wrapped by our own thin Memory Broker that enforces scoping, provenance, budgets and theft detection. Do not build an extraction/retrieval engine ourselves; do build the broker, because no surveyed system has a hostile-reader model.

## Key facts with sources

### Taxonomy and benchmarks
- CoALA names four memory kinds (working, episodic, semantic, procedural) plus an action space of internal memory ops and external ops. https://arxiv.org/abs/2309.02427
- MemGPT: OS-style tiers (main context, recall, archival); the model edits its own memory via function calls. https://arxiv.org/abs/2310.08560
- LongMemEval: 500 curated questions; tests information extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention; commercial assistants and long-context models showed about a 30% accuracy drop on sustained interactions. https://arxiv.org/abs/2410.10813
- LoCoMo: conversations averaging about 300 turns / 9K tokens over up to 35 sessions; QA, event summarization, multimodal dialogue; LLMs fall well short of humans. https://arxiv.org/abs/2402.17753
- MemoryAgentBench: four competencies (accurate retrieval, test-time learning, long-range understanding, selective forgetting); current methods master none fully together. https://arxiv.org/abs/2507.05257 Note: selective forgetting is the competency most relevant to us and the least covered by LongMemEval/LoCoMo.
- Caveat: all three benchmarks are single-user chat memory. None measures leak resistance, cross-tenant isolation or procedural-memory quality. UNVERIFIED that any public benchmark does; we must write our own tests.

### Systems
- Mem0: Apache-2.0; scoping ids `user_id`, `agent_id`, `run_id`; `memory.add()` / `memory.search()`. The paper describes ADD/UPDATE/DELETE/NOOP operations; the README states a new algorithm (April 2026) does "single-pass ADD-only extraction" (accumulate, no overwrite) and reports LoCoMo 92.5, LongMemEval 94.4 (vendor-reported). Paper: 26% relative gain over OpenAI memory on LLM-judge, 91% lower p95 latency and 90%+ token savings vs full context; graph variant about +2%. https://github.com/mem0ai/mem0 , https://arxiv.org/abs/2504.19413
- OpenMemory (Mem0): local-first MCP memory server; tools add_memories, search_memory, list_memories, delete_all_memories; Qdrant vector store; audit log of every read/write; "no cloud sync" (from vendor pages found via search; the docs URL I tried directly returned 404, so UNVERIFIED in primary docs). https://docs.mem0.ai/openmemory , https://mem0.ai/blog/introducing-openmemory-mcp
- Letta (MemGPT successor): Apache-2.0; memory organized into blocks pinned in the system prompt; blocks can be attached/detached and shared across multiple agents; agent edits blocks via tools and developers can edit via API; all state persisted in a DB. Repo now points active code to `letta-ai/letta-code`. https://docs.letta.com/guides/agents/memory , https://github.com/letta-ai/letta . Useful idea: block-level attach/detach and (UNVERIFIED in what I read) read-only blocks.
- Zep / Graphiti: bi-temporal knowledge graph; facts are edges with validity windows, and "old facts are invalidated rather than deleted"; every entity/edge traces to source "episodes" (provenance); hybrid retrieval (embeddings + BM25 + graph traversal); backends Neo4j, FalkorDB, Amazon Neptune (Kuzu listed as deprecated); has an MCP server and FastAPI service. Paper: DMR 94.8% vs MemGPT 93.4%; LongMemEval up to +18.5% accuracy and 90% lower latency vs baselines. https://github.com/getzep/graphiti , https://arxiv.org/abs/2501.13956 . License not seen in what I fetched (UNVERIFIED; check LICENSE before adopting).
- LangMem (LangChain): semantic memory as collections or profiles (profile = update-in-place schema), episodic memory (successful interactions as examples), procedural memory (rules that evolve through feedback, i.e. prompt optimization); two write modes: hot path (in conversation, adds latency) and background/"subconscious" (async); hierarchical namespaces (org -> user -> context). https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
- A-MEM: Zettelkasten-style notes with description, keywords, tags; links between related notes; new memories can rewrite attributes of old ones ("memory evolution"); NeurIPS 2025. https://arxiv.org/abs/2502.12110 . Risk for us: memory evolution lets new input mutate old notes, which is exactly the pivot a poisoning attacker wants.
- Cognee: Apache-2.0; local-first (small models on CPU, no API key); API remember / recall / improve / forget; `dataset_name` / `datasets` as the unit of recall; Claude Code plugin, MCP server, REST, Docker Compose, can run on PostgreSQL. https://github.com/topoteretes/cognee . The explicit `forget` and dataset scoping match our need for revocation.
- MCP reference memory server: knowledge graph of entities, relations, observations in a local JSONL file; 8 tools including `read_graph` (returns the entire graph), create/delete entities/relations/observations, search_nodes, open_nodes; MIT. https://github.com/modelcontextprotocol/servers/tree/main/src/memory . Useful as the simplest MCP shape; `read_graph` is precisely the bulk-dump tool we must NOT expose to a foreign pack.
- Claude Code: two memory systems loaded every session. CLAUDE.md (you write; instructions; project/user/org scope) and auto memory (Claude writes; learnings; per repository; first 200 lines or 25KB loaded). `.claude/rules/` supports path-scoped rules; subagents can have their own persistent memory. Docs state memory is context, not enforced configuration; blocking must use hooks (PreToolUse). Docs also warn that contradictory instructions get picked arbitrarily and should be pruned. https://code.claude.com/docs/en/memory
- OpenClaw (our base platform): memory is plain Markdown in the workspace: USER.md (stable preferences), MEMORY.md (durable facts/decisions), `memory/YYYY-MM-DD.md` (daily notes), DREAMS.md (consolidation review). "The model only remembers what gets saved to disk; there is no hidden state." Tools memory_search, memory_get; background "dreaming" promotes items from daily notes to MEMORY.md by thresholded scoring and, per docs, prevents low-quality or untrusted content from entering long-term storage; a pre-compaction memory flush is on by default. https://docs.openclaw.ai/concepts/memory . Whether plugins can swap this memory backend is UNVERIFIED.
- Voyager: skill library of executable, interpretable, composable code as procedural memory, with iterative prompting and self-verification; skills transferred to new worlds. https://arxiv.org/abs/2305.16291 . This is the model for harness-owned procedural memory (skills as files, verified before admission).

### Attacks on memory (why write ownership matters)
- MINJA: an attacker injects malicious records into an agent's memory bank using only normal queries and observing outputs (bridging steps, indication prompt, progressive shortening so the record is naturally retrieved later). https://arxiv.org/abs/2503.03704
- AgentPoison: poisoning the memory/knowledge base with optimized triggers; average attack success above 80%, under 0.1% poison rate, under 1% impact on benign performance, no model training needed. https://arxiv.org/abs/2407.12784
- Implication: two-way risk. A foreign pack that can write to the user's memory can plant instructions; a user's memory read by a foreign pack can be exfiltrated. Neither is covered by the benchmarks above.

### Gaps across all surveyed systems
- None offers per-reader access control against a hostile reader (Mem0 ids and Letta shared blocks are namespacing for cooperative agents; Claude Code docs say memory is not enforced config). UNVERIFIED for Letta/Cognee multi-user permission details; I did not read them.
- Conflict resolution differs: Graphiti invalidates with time windows, Mem0 (new algorithm) keeps all and ranks, LangMem profiles update in place, A-MEM mutates old notes. Only Graphiti keeps full history by design.

## Fit for agent-bridge

Three actors hold memory: the requester (user), the pack (owner's harness), and the task run. Map the taxonomy to ownership:

| Plane | Kind (CoALA) | Owner | Lives | Who may write | Who may read | Lifetime |
|---|---|---|---|---|---|---|
| U: User vault | semantic (profile, facts), episodic (past task outcomes the user kept) | requester | requester machine, always (also the case in Hosted: vault stays home, only a projection is sent) | the user's own local agent via the broker; foreign packs NEVER directly | local agent fully; foreign pack only through broker "lens" | until user forgets; decay and TTL per item |
| P: Pack-relationship memory | semantic+episodic about "what this pack did for me" | requester | requester vault, namespace `pack:<pack_id>@<hash>` | local agent, from accepted proposals | the local agent; the pack only via lens | tied to the pack; deleted on revoke/uninstall |
| H: Harness procedural memory | procedural (skills, playbooks, prompts, tool recipes) | pack owner | inside the pack (files, versioned) | owner only, via the improvement loop and eval gate; NOT mutable during a run | the pack at runtime, read-only | per pack version |
| T: Task scratch | working + short episodic | the run | cell tmpfs | the pack during the run | the pack during the run | destroyed at task end |

Why this split: user data and harness know-how have opposite protection needs. The owner's procedural memory is their IP (published, priced), so it is shipped as part of the pack and is public to the extent the pack is. The user's memory is private and must never be a pack's writable state.

Write path (user vault), based on the literature:
1. Capture: raw events appended to an immutable episode log (Graphiti "episodes", OpenClaw daily notes). Every record carries `source` (user, local-agent, tool-result, foreign-pack-output), `trust` level, timestamp, task id.
2. Extract: LLM extraction into candidate facts (Mem0 / Cognee do this; do not write our own).
3. Dedupe and conflict: bi-temporal fields (valid_at, invalid_at, recorded_at) as in Graphiti; contradicting facts invalidate rather than delete, so rollback and audit work. If Mem0 is the engine, its ADD-only mode gives the same non-destructive property.
4. Promotion gate (OpenClaw dreaming-style): only items from `user` or `local-agent` sources auto-promote to durable semantic memory. Anything derived from foreign-pack output or untrusted tool results stays in a quarantined `proposed` tier until the user accepts (matches MINJA/AgentPoison threat). Never let new input rewrite old notes silently (reject A-MEM-style in-place evolution for the vault; allow it only for the pack's own H plane if desired).
5. Decay: per-item TTL and last-used score; episodic decays fastest, profile facts slowest; explicit `forget` (Cognee-style) with tombstone in audit log. Forgetting must be testable (MemoryAgentBench competency 4).
6. Consolidation runs in the background (LangMem "subconscious" mode), never on the hot path of a foreign run.

Read path (what a foreign pack can see):
- Pull mode: the pack runs in a sandbox beside the data. It does NOT mount the vault. It gets a Memory Broker endpoint exposing only `memory.search(query, k)` returning snippets from a task-scoped allowlist ("lens" = the subset of U the user granted for this task, e.g. tags/datasets), with hard k and byte caps per call and per task, results labelled by provenance. No `read_graph`, `list_memories`, or dump tool. Embeddings never returned.
- Hosted mode: no vault access at all. The requester's local agent builds a minimal task package from the lens ("what leaves" preview) and sends only that; the owner is root there (round 1 finding), so only the package is exposed.
- Scope map onto existing libs: Mem0 `user_id` = requester, `agent_id` = pack id, `run_id` = task; Cognee `dataset` = lens unit; LangMem namespaces org/user/context.

Active defense hooks inside the Memory Broker (memory-theft signals; detection is our own work, no surveyed system does it):
- Volume budget per task and per pack (items, bytes, calls); exceeding it kills the cell.
- Enumeration patterns: many near-uniform queries, wildcard or empty queries, queries that sweep tag space, sequential id probing.
- Canary records: plant honey items in each lens (fake credential, fake note); any appearance in a pack's outbound byte stream (sidecar egress/result) or any query for them triggers kill, quarantine of the pack hash, revoke of broker tokens, and an audit record.
- Egress correlation: broker logs what was served; sidecar/result guard checks result and outbound payloads for long verbatim overlap with served snippets beyond the declared answer schema.
- Write attempts to U or P by a foreign pack are denied and count as a hostile signal.
These are heuristics; honest label: they reduce, not eliminate, covert-channel leakage (a pack can encode data in an allowed answer). Pull mode removes the network path but not the result path.

Harness (H plane) update loop, using existing ideas:
- Skills as versioned files (Voyager skill library, OpenClaw/Claude SKILL.md folders); prompt/instruction refinement via LangMem-style procedural optimization from feedback; episodic "good run" examples curated by the owner.
- Learning source for H must be the owner's own tasks and ratings, and sanitized/aggregated signals from requesters. Raw requester data must never flow into H (otherwise the pack's published version leaks user data to future buyers). Enforce: the run's T plane is destroyed; only owner-approved, de-identified lessons go to a candidate pack version; candidate version runs the eval suite and a regression/leak test before publish; the pack hash changes on every version (round 1 manifest/hash check).
- Claude Code docs point to the right principle: instructions pruned for contradictions and enforced by hooks, not by memory text. So security rules live in the broker/sandbox, never only in memory.

Evaluation plan: (a) quality: run a LongMemEval and LoCoMo subset on the chosen engine for sanity; (b) update: knowledge-update and selective-forgetting tests (LongMemEval knowledge-update category, MemoryAgentBench); (c) our own: red-team suite based on MINJA/AgentPoison style injections for the proposed tier, and an enumeration/canary suite for the broker; metric = leaked canaries, bytes served vs needed, time to kill.

## Recommendation

1. Canonical format: Markdown files + append-only JSONL event log in the user vault, structured like OpenClaw (USER.md, MEMORY.md, daily notes) so the base platform reads it natively and humans can audit/edit. Add front-matter fields: id, source, trust, valid_at, invalid_at, ttl, lens tags.
2. Engine: Mem0 OSS (Apache-2.0, `user_id/agent_id/run_id`, local, add/search) as the extractor and retrieval index over those files. Evaluate Graphiti as the alternative if temporal queries ("what did I decide before X") matter; Graphiti needs a graph DB (Neo4j/FalkorDB) so it is heavier for a local vault. Cognee is the third option if we want `forget` and datasets as first-class. Decide by a one-day bake-off on a LongMemEval subset plus our leak tests; the bake-off result is UNVERIFIED today.
3. Build one thing: the Memory Broker (scoped lens, budgets, provenance labels, canary, theft signals, kill/quarantine/revoke/record), exposed to packs as a narrow MCP tool (`memory.search`) only. No pack ever gets files or a DB handle.
4. Write rules: user-vault writes only from user and local agent; foreign output goes to the quarantined `proposed` tier; promotion needs explicit user accept or a high-trust rule; no in-place mutation of existing items; invalidate, do not delete; TTL and decay per type.
5. H plane: pack ships procedural memory as versioned skill/prompt files; improvement loop is offline, owner-controlled, eval-gated; no requester raw data enters it.
6. Pull and Hosted both use the same broker interface; in Hosted the lens is materialized as a minimal task package instead of a live endpoint.

## Risks

- Leakage via allowed channels: a pack can answer with memory contents or encode them in the result; the broker and result guard only bound this. Do not claim "cannot leak" in Pull mode, claim "cannot send" at the network level plus detection.
- Poisoning: AgentPoison reports above 80% success at under 0.1% poison rate, so any retrieval over mixed-trust content is risky; the quarantine tier must be strict and must also cover content ingested from the web or documents, not just pack output.
- Theft detection heuristics yield false positives that kill legitimate tasks (hurts marketplace ratings) and false negatives (slow exfil). Needs tuning data we do not yet have.
- LLM extraction cost/latency and extractor errors writing wrong facts; the extractor model itself sees user data, so it must be local or a user-approved endpoint (Nebius vs local choice UNVERIFIED).
- Vendor benchmark numbers (Mem0 92.5/94.4) are self-reported and not reproduced; the algorithm changed in April 2026, so older papers' behavior (UPDATE/DELETE) differs from the current README.
- Library maturity and licensing: Graphiti license not seen; Kuzu backend is deprecated; OpenMemory details only from vendor pages; OpenClaw memory plugin-swap not verified.
- Procedural memory quality is the least benchmarked area; "improvement" can overfit or regress, hence the eval gate.
- Pack-relationship memory (P plane) could itself be a tracking vector for a pack across sessions; keep it on the requester side only and expose via lens.

## Open questions

- Can OpenClaw's memory backend be replaced or wrapped by plugin (so Mem0/Broker sit behind `memory_search`)? Read the OpenClaw plugin SDK memory slot.
- Which model does extraction and consolidation: local small model, or Nebius Nemotron with user consent? Affects the "nothing sent" promise for the vault itself.
- Graphiti license and Letta read-only block / multi-user permissions: verify from LICENSE and docs.
- How to define the lens: tags chosen by user, query-time semantic filter, or both? Needs UX design.
- Which de-identification is acceptable for lessons flowing from requester tasks into H (and who approves)? Possibly never automatic.
- Does NVIDIA tooling (NeMo Guardrails, Nemotron safety models) offer something usable at the broker/result guard for theft detection? Out of this topic; hand to the security topic.
- Should the P plane be shared across packs from the same owner? Default no.
