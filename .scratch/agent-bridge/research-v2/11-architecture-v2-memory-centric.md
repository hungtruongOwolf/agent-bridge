# Architecture v2, memory-centric (Vault at the center)

Synthesis of research-v2 files 01-10 plus round 1. No new primary research; all facts inherit the source tagging in those files (UNVERIFIED items stay UNVERIFIED).

## Summary
The user-owned Memory Vault is the center. Every agent and machine touches memory only through vaultd (the vault daemon) and its Memory Broker, via attenuated, task-scoped, read-only lenses. Packs are guests: they get a lens, return a result, and may propose writes into a quarantined tier. Pull mode runs the pack in a no-NIC sandbox beside the vault; Hosted mode sends only a compiled Context Packet and never touches the vault. Active defense (Sentinel) guards the vault boundary and the egress boundary.

## Key facts with sources
See files 01-10 (MINJA 2503.03704, AgentPoison 2407.12784, MEXTRA 2502.13172, 2608.21230 screening 0/360, CaMeL 2503.18813, Biscuit, OpenShell, Nebius ZDR docs, PayPal Orders v2, Nitro Enclaves, TEE.fail, Berkeley RDI).

## Fit for agent-bridge
Nebius Token Factory (Nemotron) is the model path via a requester-owned key-holding proxy; NeMo Guardrails/Nemotron safety as advisory scorers only; PayPal Orders v2 authorize/capture/void/Payouts; AWS Nitro as optional Sealed Hosted tier.

## Recommendation
1. Vault: Markdown records + append-only hash-chained journal (JSONL, Merkle checkpoints) as truth; SQLite index (FTS + vectors) as derived, rebuildable. Layers: U (user), P (pack-relationship, requester side), H (harness procedural, in pack, owner-only), T (task scratch), Q (quarantined proposed). Update rules per layer in the structured answer.
2. Broker: only memory.search/memory.get over MCP, lens + budgets + provenance labels + canaries; no dump tool; Biscuit (or macaroon fallback) capability.
3. Pack = pack.yaml (request) + SKILL.md/AGENTS.md/.mcp.json/evals; grant = declared AND policy AND mode ceiling.
4. Lifecycle: author, validate, Certifier eval (private suites, no-pack baseline, security suite), sign Ed25519, publish immutable digest, run, feedback (consented, scrubbed), GEPA-style data-only improvement gated by held-out regression, rank by LCB + verified paid completions.
5. Defense: deterministic detectors kill; guard models only escalate; canary reads outside lens are strikes, not kills (file 10).

## Risks
Result-channel leakage, shared-kernel escape (WSL2), heuristic detector FP/FN, owner-attested Hosted verdicts, own-code complexity, open-pack copyability, eval gaming.

## Open questions
Biscuit JS support; OpenShell on Win11 Home; Nebius Nemotron safety model availability; promotion policy vs approval fatigue; private-suite authorship; Pull receipts trust.
