# 06 - Threat model: requester vs owner direction

Date: 2026-10-07. Scope: who trusts whom in an agent+harness marketplace, and which execution model best prevents context theft.

## Summary

- Core asymmetry: **foreign code can be sandboxed on your own machine (deny-all egress); your data, once sent to a foreign machine, cannot be controlled.** Therefore "run your harness pack on my machine" (Model B) structurally solves requester context theft, while "run my task on your machine" (Model A) can only reduce it (minimize, label, trust, reputation).
- Model A is still the only model that serves the original use case: the *owner's* private data, hardware, accounts and private tools. The owner's data protection is solvable with a sandbox plus result preview (the code that runs there is a prompt, not a binary).
- Recommendation: a marketplace with two listing types sharing one sandbox/policy layer. **Pack (Model B) is the default and the headline security story** (requester data never leaves). **Hosted (Model A) is explicitly labeled "your task text and chosen files are visible to the owner"** and used when the value is the owner's data/compute. Demo both: B for context-theft proof, A for owner-data proof.
- No guardrail (prompt-injection filter, "safety prompt") is a boundary. Boundaries must be OS-level sandbox, egress allowlist, credential separation, and signed/pinned manifests.

## Key facts (with sources)

1. Lethal trifecta: private data + untrusted content + external communication = exfiltration; the advice is to avoid the combination by design, since detection guardrails at "95%" are a failing grade. https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ . Applied here: a third-party harness gets private data (requester's context) and can talk out; remove the "talk out" leg by sandbox egress control.
2. OWASP Top 10 for LLM Apps 2025 includes LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM03 Supply Chain, LLM06 Excessive Agency, LLM07 System Prompt Leakage. https://genai.owasp.org/llm-top-10/ . (LLM07 matters for harness IP in Model B; LLM03 for pack supply chain.) OWASP "Agentic AI Threats and Mitigations" (Feb 2025) exists, but its threat IDs were NOT readable via fetch: UNVERIFIED, read the PDF at https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/ before citing IDs.
3. MCP security best practices: confused deputy, token passthrough ("MUST NOT accept tokens not issued for the MCP server"), SSRF, session hijacking, local MCP server compromise (arbitrary code with client privileges; MUST show exact command and get consent; SHOULD run in sandbox with minimal privileges), scope minimization. https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices (page redirects to the 2025-11-25 spec text).
4. MCP tool poisoning, rug pull (server changes tool descriptions after approval), and shadowing (one server's descriptions alter use of another's tools). https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks . Direct implication: pack manifests must be content-hash pinned and a changed hash must re-trigger approval.
5. A2A enterprise guidance: HTTPS/TLS 1.2+, identity at transport layer (OAuth2/OIDC), authorization post-auth, "opaque execution" (agents don't share memory, tools or resources), data minimization, audit logging with correlation IDs. https://a2a-protocol.org/latest/topics/enterprise-ready/ . A2A gives a good vocabulary for Model A but does NOT protect data once the remote agent receives it; it assumes the remote party is trusted with the message.
6. OpenClaw: "one trust boundary per gateway", not designed for adversarial multi-tenant use; separate gateways for mixed trust; prompt-injection mitigation is not a cryptographic guarantee; treat third-party skills as untrusted code; credentials injected via config stay on host, not in sandboxes. https://docs.openclaw.ai/gateway/security , https://docs.openclaw.ai/tools/skills . Implication: OpenClaw as-is is not a safe multi-tenant host; every foreign job/pack needs its own sandbox/gateway.
7. NVIDIA NemoClaw/OpenShell controls: deny-by-default egress with binary-scoped and L7 (method/path) rules, operator approval for unlisted destinations, Landlock + container filesystem restrictions locked at creation, inference routed via `inference.local` so the sandbox never holds provider credentials, presets incl. tavily. https://docs.nvidia.com/nemoclaw/latest/security/best-practices.html . This is a directly reusable, NVIDIA-branded sandbox pattern (fits Nebius x NVIDIA story). Platform support (Windows) UNVERIFIED.
8. Anthropic sandbox-runtime (srt): OS-level fs/network restriction without container; Linux bubblewrap+seccomp, macOS Seatbelt, Windows alpha (dedicated local user, WFP egress filters, NTFS ACLs); network allow-only via proxy domain allowlist. https://github.com/anthropic-experimental/sandbox-runtime . Candidate for a cross-OS demo (two machines, any OS), Windows is alpha.
9. NVIDIA H100 confidential computing protects data in use from host operator/admin, but needs H100-class GPUs and a compatible stack. https://docs.nvidia.com/cc-deployment-guide-snp.pdf . Not available on a consumer owner's machine; a hosted-on-TEE variant is out of hackathon scope. Whether Nebius offers confidential inference: UNVERIFIED.

## Assets, adversaries, trust directions

Assets: R-ctx (requester task text, files, memory, credentials, API keys); O-data (owner files, local DBs, accounts, other harnesses, machine); O-harness-IP (prompt, tool config, skills); result integrity; money (PayPal pre-auth/capture); reputation (stars); relay metadata.

Adversaries: M-owner (owner/harness author acting maliciously), M-requester (task author), M-relay (marketplace/relay operator), M-pack (third-party code inside a pack, with or without author consent), M-web (attacker-controlled content the agent reads, i.e. indirect prompt injection), M-sybil (fake stars/reviews).

Direction (a): requester's R-ctx exposed to owner's machine/harness. Direction (b): owner's O-data exposed to the requester's task. In Model B the two directions collapse into one: the requester runs the owner's pack, so the only exposure is O-harness-IP (to requester) and requester machine (to pack code).

## Who-can-do-what

Legend: Y = can, N = cannot (if controls hold), P = partial/depends, (C) = control required.

| Actor / capability | Model A: run on owner machine | Model B: pack runs on requester machine |
|---|---|---|
| Owner reads requester task text/files | **Y (inevitable)**; P with minimization/redaction (C) | N (owner never receives it; only receives optional anonymous run counts if allowed) |
| Owner's harness exfiltrates R-ctx to third parties | **Y** (owner controls machine, egress, logs) | N if pack sandbox has deny-all egress except requester-chosen model endpoint (C) |
| Pack code reads requester files outside granted folder | n/a (pack on owner's machine, which is trusted by owner) | N with fs sandbox, one granted folder read-only (C) |
| Pack code reads requester secrets/API keys | n/a | N when credentials stay on host proxy (inference.local pattern) (C) |
| Pack encodes data into allowed outbound call (e.g. search query to Tavily) | n/a | P: leak goes to Tavily via requester's proxy and key, not to the pack author; pack author has no receiving endpoint (C: allowlist only requester-controlled/neutral endpoints, log queries) |
| Pack changes behavior after approval (rug pull) | P: owner can change harness any time | N with content-hash pinned signed manifest, re-approval on change (C) |
| Requester task reads owner files outside granted folder | N with fs sandbox on owner machine (C) | n/a (owner data not present) |
| Requester task makes owner agent run shell/exfiltrate owner data | N with fixed tool list, no shell, deny-all egress except model/Tavily proxy, step+time limits (C) | n/a |
| Prompt injection from web content steers agent | P: reduces to what the sandbox permits (the true boundary) | P: same; blast radius = the granted folder + allowed egress |
| Owner sees result before return | Y (preview, optional auto-return) (C) | n/a |
| Requester copies owner's harness IP | N (never leaves owner) | **Y** (prompts/config are on requester disk; only legal/licence/obfuscation deterrent) |
| Owner uses own private data/accounts/hardware for requester | **Y (main value)** | N (that is lost) |
| Relay reads task/result | N with E2E encryption (relay sees ciphertext + metadata) (C) | N (relay only distributes signed packs; no task traffic) |
| Relay tampers with pack | n/a | N with author signature + hash verification (C) |
| Metering/billing enforcement | P: owner-side meter, requester pre-auth, capture on accept; disputes possible | P: run is on requester machine, metering is honor/ runtime-reported; sell per pack/licence rather than per task |
| Requester refuses to pay after receiving result | P (capture-on-accept is gameable; mitigate with preview + short window + dispute) | P similar |
| Fake stars | Y unless ratings require a verified completed paid run, one per payer (C) | same |

## Attack paths (ordered by realism for the hackathon demo)

1. Model A: curious/malicious owner reads the task/context. Not preventable technically; reduce by sending only task text + explicitly selected files, redaction/pseudonymization step on requester side, per-task approval showing exactly what leaves, reputation/stars, owner accountability (identity, PayPal-linked). Honest labeling is itself a control.
2. Model B: malicious pack tries to read the home dir, `.env`, SSH keys, then POST to attacker. Defeated by fs allowlist (one folder, read-only) plus deny-all egress. MCP spec itself recommends sandboxed local servers (fact 3).
3. Model B: pack hides instructions in tool descriptions/skills (tool poisoning/shadowing, fact 4). Mitigation: manifest lists tools; descriptions are part of the hashed manifest; requester sees a diff; no third-party MCP servers outside the manifest.
4. Both: indirect prompt injection from web/file content causing agent to leak the granted data. Mitigation: do not combine the three trifecta legs: granted data + untrusted web content + free egress. Offer "offline mode" (no web) as default; if Tavily is on, outputs go through preview, and egress is only the search API.
5. Model A: requester task hijacks owner's agent (task text says "also read ~/.ssh"). Mitigation: read-only single granted folder via OS sandbox, fixed tools, no shell, step and time limits, preview of result, append-only audit.
6. Supply chain: pack depends on npm/pip at install. Mitigation: no install-time or run-time package fetch inside the sandbox; the pack ships vendored or declares allowed registries only at install (LLM03).
7. Covert channels (timing, result text steganography in Model A returning to requester? the other way: owner data in result): preview plus size limits; accept residual risk and say so.
8. Relay compromise: E2E (public-key identity) leaves metadata exposure (who talks to whom, sizes). Accept and document.

## Evaluation of the two models

| Criterion | A: run my task on your machine | B: run your harness on my machine |
|---|---|---|
| Solves requester context theft | No (only mitigates) | **Yes** (by construction, given sandbox) |
| Protects owner data | Yes, via sandbox (owner is the one executing foreign input, which is text) | Not applicable (owner's data not used) |
| Owner monetizes | Compute + harness + private data, per task/hour | Harness only (licence/per pack/per run), no hours |
| Harness IP protection | Strong | Weak |
| Requester saves own resources (original pitch) | Yes | No (runs on requester compute) |
| Build effort | Relay + approval + sandbox + E2E | Pack format + signing + sandbox + registry (simpler: no live relay) |
| Demo clarity | "raw file never appears on requester machine" (existing decision) | "pack runs with network cut; show blocked exfil attempt live" (very visual) |

Pure B drops the "saves my resources" and "owner's private data" value; pure A cannot honestly claim "context safe". Hence both listing types.

## Fit for agent-bridge

- Existing decisions already contain the Model A controls (E2E, public-key identity, approval, expiry, limits, audit log, tight read-only agent). Keep them.
- Add Model B as a "Pack" listing: a harness pack folder (prompt, tool list, MCP config) is exactly the planned unit; add manifest + hash + signature and run it under the same sandbox profile locally. The requester's own Nebius NVIDIA key is used via a host-side proxy so the pack never sees it. Nemotron via Nebius is the single inference path, satisfying the hackathon rule.
- Reuse (do not build): NemoClaw/OpenShell policy model or Anthropic srt for sandboxing; OpenClaw as the runtime but with one sandbox/gateway per foreign job or pack (its own docs say one gateway is one trust domain); MCP security checklist as the review rubric.
- Observability UI can show the threat model live: egress-denied events, granted-folder reads, "what left this machine" ledger. This is the demo's polish differentiator.

## Recommendation

1. Define two listing types: **Pack** (default, "your data never leaves") and **Hosted** ("owner machine runs it; owner can see what you send").
2. One policy layer for both: capability manifest (granted folder, tools, allowed egress hosts, step/time/token limits), enforced by OS sandbox, not by the model. Credentials never inside the sandbox.
3. Hash-pinned, signed manifests; any change re-triggers approval (kills rug pull).
4. Hosted mode: show the requester a "what will be sent" screen, send task text plus selected files only, E2E encrypt, result preview on owner side, append-only audit.
5. Ratings only from verified completed (paid) runs; show badge "Pack: sandboxed / Hosted: owner-visible" next to stars.
6. Document the table above in the submission as the threat model; state residual risks plainly.

## Risks

- Sandbox escape or misconfiguration (Windows support in srt is alpha; NemoClaw Windows support UNVERIFIED). Mitigation: demo on Linux/macOS machines or WSL/container, test with an adversarial pack.
- Model B weakens monetization and harness IP; judges may ask why a pack is worth paying for.
- Hosted mode still leaks context to the owner; overclaiming would damage credibility.
- Prompt injection can still misuse whatever the sandbox grants; keep grants minimal.
- Billing/metering in Model B is unenforceable on requester's machine.
- Scope creep: two modes plus payments plus UI by 30/10.

## Open questions

- Which OS will the two demo machines run, and does srt/OpenShell run there? (UNVERIFIED for Windows.)
- Does OpenClaw offer per-skill/per-session sandboxing sufficient for a pack, or do we wrap the whole runtime in the sandbox? Check docs/source (not read in depth).
- OWASP Agentic threat IDs: read the PDF and map them to the table.
- Do the hackathon rules for Nebius require inference from Nebius at runtime on the requester side only? Packs using requester key should satisfy; confirm.
- Is confidential inference offered on Nebius Token Factory? UNVERIFIED.
- How to pay for packs: per-run honor-system, one-time licence, or Hosted-only payments for the PayPal track?
