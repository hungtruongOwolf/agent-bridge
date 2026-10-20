# 05 - Security and isolation for untrusted third-party agent+harness

Date: 2026-10-07. Scope: how to run a third-party agent+harness without it stealing requester data, and without harming the executing machine. Primary sources only; anything not read at a primary source is marked UNVERIFIED.

## Summary

1. There are two distinct trust problems, and they have different answers:
   - (P1) Owner machine vs. the harness/task: protect the host from the harness and from the requester's task content. Solved well by sandboxing (microVM or container) plus tool brokering plus egress allow-listing. Achievable in the demo.
   - (P2) Requester data vs. the owner/harness: on a normal consumer machine (Windows/Mac laptop, no TEE) the owner is root, so any plaintext sent to the owner's machine is readable by the owner. No software trick on that machine changes this. Real secrecy needs a TEE with remote attestation (Nitro Enclaves, TDX/SEV-SNP + NVIDIA CC), which is roadmap, not a 3-week item for two laptops.
2. Honest, defensible design for the demo: make P2 a data-minimization problem, not a secrecy claim. Three techniques stack: (a) send minimal context (no shared memory, per-task fresh session); (b) redact/tokenize sensitive fields before leaving the requester (reversible token map stays local); (c) invert the flow ("code to data"): the requester pulls the signed harness pack and runs it in the requester's own sandbox, so the requester data never leaves. Mode (c) is the strongest achievable answer to "third-party harness steals my info" and also avoids the P2 problem entirely, at the cost of losing the "saves my own resources" and "owner's private data" benefits. Offer both modes: REMOTE (owner's data/compute) and PULL (requester's data, owner's harness).
3. The injection/exfil problem is architectural. Use the "lethal trifecta" / "Rule of Two" framing: never give one agent session private data + untrusted content + external send. Enforce with a broker and egress allow-list, not with prompt guardrails.
4. Marketplace supply chain is a proven attack surface: a published audit of ClawHub (OpenClaw's skill marketplace) found 341 malicious skills out of 2,857 audited. Since we build on OpenClaw, signed packs, static scanning, and sandboxed execution of every pack are mandatory features, and a good demo story.

## Key facts (with sources)

Isolation technologies
- Firecracker: each microVM runs in its own process; "all vCPU threads are considered to be running malicious code" and are contained via KVM; seccomp filters per thread; a `jailer` sets cgroups/chroot then drops privileges. Linux hosts and guests only, requires KVM. https://github.com/firecracker-microvm/firecracker/blob/main/docs/design.md (implication: not runnable natively on Windows/macOS; on Windows only inside WSL2 if nested virtualization is available, UNVERIFIED.)
- gVisor: userspace "application kernel" (Sentry) plus Gofer for file access; `runsc` is an OCI runtime that plugs into Docker/Kubernetes; Linux amd64/arm64. https://gvisor.dev/docs/
- Kata Containers: containers each in a lightweight VM with a dedicated kernel; OCI/CRI compatible; supports QEMU, Cloud-Hypervisor, Firecracker. https://katacontainers.io/
- Docker (plain containers): Docker's own docs say default capabilities/mounts "may provide incomplete isolation, either independently, or when used in combination with kernel vulnerabilities"; recommends defense in depth. Containers share the host kernel. https://docs.docker.com/engine/security/
- Docker Sandboxes: Docker's product for coding agents uses "microVM isolation", configurable network and filesystem policies, local free, credentials handling documented. Platform specifics (Windows) not confirmed on the page I read: UNVERIFIED. https://docs.docker.com/ai/sandboxes/
- WSL2: runs a real Linux kernel in a lightweight utility VM; distros share the same VM kernel, network namespace, CPU/memory (separate PID/mount/user namespaces only). Therefore WSL2 is a convenient Linux host on Windows but separate distros are NOT strong mutual isolation. https://learn.microsoft.com/en-us/windows/wsl/about
- Windows Sandbox: hypervisor-based disposable VM, fresh instance each launch; networking ON by default (disable via .wsb config); can map a folder read-only; NOT supported on Windows Home; only one instance at a time. https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-overview (The owner's machine is Windows 11 Home per environment info, so Windows Sandbox is unavailable on it. Docker Desktop/WSL2 is the realistic path.)
- OpenClaw sandboxing: gateway stays on host, only tool execution moves into a sandbox; backends Docker (default), Podman, SSH, OpenShell, Crabbox; tool allow/deny wins over sandbox; docs say "This is not a perfect security boundary". OpenClaw security model: one trust boundary per gateway, designed for a single operator/mutually-trusting team, NOT adversarial multi-tenant; `openclaw security audit` command. https://docs.openclaw.ai/gateway/sandboxing , https://docs.openclaw.ai/gateway/security (Implication: stock OpenClaw is not built for running strangers' harnesses; we must wrap it, one container/VM per task.)

Confidential computing / attestation
- AWS Nitro Enclaves: isolated VM from an EC2 instance; no persistent storage, no interactive access, no external networking, only a local socket (vsock) to the parent; parent root cannot read enclave memory; signed attestation document with PCR0-2 (image, kernel, app), PCR8 (signing cert); KMS key policy can require matching PCRs; debug mode yields all-zero PCRs and is unusable for attestation; no extra charge beyond EC2; enclave must be Linux. https://docs.aws.amazon.com/enclaves/latest/user/nitro-enclave.html , https://docs.aws.amazon.com/enclaves/latest/user/set-up-attestation.html
- NVIDIA confidential computing: Hopper (H100) and Blackwell GPUs, combined with CPU TEEs (TDX, SEV-SNP); remote attestation; `nvtrust` repo has attestation SDK and CVM launch scripts (Python SDK deprecated for C++ SDK/CLI). https://docs.nvidia.com/confidential-computing/ , https://github.com/NVIDIA/nvtrust (Not applicable to the demo path because inference runs on Nebius Token Factory; whether Nebius offers confidential inference: UNVERIFIED.)
- Intel SGX/TDX specifics: not read at a primary source here; UNVERIFIED beyond the NVIDIA page naming TDX/SEV-SNP.
- Nebius Token Factory data handling: per search summary of its legal docs, default retains inputs/outputs for speculative decoding (EU, Finland), Zero Data Retention (ZDR) is an option, no training on content. Search snippet only, read the legal page before claiming: https://docs.tokenfactory.nebius.com/legal/privacy-policy (UNVERIFIED in detail). Implication: the LLM provider is a third party that sees the prompts in every design; mention in the threat model.

Injection and exfiltration design principles
- Lethal trifecta (private data + untrusted content + external communication) lets attackers steal data; "guardrails alone won't reliably protect you"; only reliable mitigation is to avoid the combination. https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- Meta "Agents Rule of Two": in one session an agent should satisfy at most two of [A] untrustworthy inputs, [B] sensitive systems/private data, [C] change state/communicate externally; if all three are needed, require human oversight. https://ai.meta.com/blog/practical-ai-agent-security/
- Design patterns paper (Beurer-Kellner et al., 2025): principled patterns for agents with "provable resistance to prompt injection". https://arxiv.org/abs/2506.08837
- CaMeL (Google et al.): separates control and data flow from the trusted query and uses capability-based policies to stop exfiltration; solved 77% of AgentDojo tasks with provable security vs 84% undefended. Code is public on GitHub under Google Research (exact repo URL not verified). https://arxiv.org/abs/2503.18813
- OWASP LLM01: direct vs indirect injection; mitigations: constrain behavior, validate output formats, filter I/O, least privilege, human approval for high-risk ops, segregate external content, adversarial testing. https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- MCP security best practices: confused deputy, token passthrough (forbidden; do not forward requester tokens), SSRF (block private/link-local ranges; use an egress proxy, Smokescreen named), local MCP server compromise (sandbox, show exact command before run, minimal privileges), scope minimization. https://modelcontextprotocol.io/specification/draft/basic/security_best_practices
- Presidio (MIT): PII detection and anonymization (masking/redacting/replacing); not reversible by itself; "no guarantee that Presidio will find all sensitive information". https://github.com/microsoft/presidio (Reversible tokenization must be our own thin layer: replace value with a token, keep map locally.)

Provenance
- Sigstore: cosign signing with ephemeral keys, Fulcio short-lived certs bound to OIDC identity, Rekor transparency log; no long-lived key management. https://docs.sigstore.dev/about/overview/ (Signing arbitrary blobs/pack tarballs with cosign is standard usage but I did not read the specific page: UNVERIFIED.)
- Marketplace evidence: security audit of 2,857 ClawHub skills found 341 malicious (335 using fake "prerequisites" to install the AMOS macOS stealer; others searched for private keys/API tokens and exfiltrated them). Secondary aggregators of the report (not the original researcher post): https://aviatrix.ai/threat-research-center/openclaw-2026-clawhub-malicious-skills/ , https://incidentdatabase.ai/entities/clawhub/ . Treat counts as reported, original report UNVERIFIED.

## Threat model for the marketplace (attack patterns)

Actors: Requester R, Owner O (machine host), Harness author H (may be O or a third party), Relay/marketplace M, LLM provider (Nebius).

| # | Attack | Who attacks whom | Mitigation (primary) | Demo? |
|---|---|---|---|---|
| 1 | Malicious harness pack (prompt/tools/MCP/skill) runs code on O's host, steals keys | H -> O | Run every pack in microVM/container, no host mounts except one granted read-only dir, no secrets in env, non-root, tool allow-list wins (as in OpenClaw) | Yes |
| 2 | Pack/skill supply chain (fake prerequisites, typosquat, update swap) | H -> O, R | Signed packs, hash-pinned versions, publish-time static scan (curl/base64/shell-out patterns), install requires owner approval and shows exact commands (MCP guidance) | Partial (sign + hash pin + scan) |
| 3 | Harness reads requester task and exfiltrates it (to H's server, via URL query, DNS, tool call) | H/O -> R | Egress deny-all; only allow-list: LLM endpoint via our model proxy, relay. Output-only return channel. DNS blocked inside sandbox. | Yes (the headline demo) |
| 4 | Owner is curious/malicious: reads R's plaintext task and results | O -> R | Cannot be prevented without TEE. Minimize + redact/tokenize; PULL mode; TEE in roadmap; be honest in the UI ("owner can see what you send") | Honest claim + redaction |
| 5 | Indirect prompt injection in R's files/web results hijacks the owner's agent to read owner's other data or send it out | R (content) -> O | Single granted folder, no shell, Rule of Two split: no session has private data + untrusted web content + send. Result goes through preview/approval before leaving | Yes |
| 6 | Injection in the returned result attacks R's own agent (result contains instructions: "now run X / send ~/.ssh") | O/H -> R | Treat returned result as untrusted data; requester-side agent gets it as a quoted data block with no tool access in that turn; structured output schema (e.g. JSON patch/answer), human approval for applying; CaMeL-style data/control split as roadmap | Yes (schema + approval) |
| 7 | Memory/context leakage across tasks (shared memory, cached files, KV transcripts) | R1 -> R2, H -> R | Fresh sandbox + fresh session per task, destroy after; no persistent agent memory; per-task workdir; logs scrubbed; no cross-task vector store | Yes |
| 8 | Credential theft: requester token forwarded to harness, or owner API keys visible in sandbox | both | Token passthrough forbidden (MCP spec); the sandbox sees only a per-task short-lived proxy token to the model proxy; real Nebius key never enters sandbox | Yes |
| 9 | Confused deputy via MCP tools in pack (tool descriptions poisoned, rug-pull updates) | H -> agent | Pin tool schema hashes; review diff on update; brokered tools only | Partial |
| 10 | Fake ratings/stars, sybil reviews, wash trading for PayPal credits | H -> M | Ratings only from paid, completed, accepted tasks (escrow-capture ties rating to payment); one rating per task id | Yes (cheap) |
| 11 | Resource abuse: crypto-mining, fork bomb, infinite loops, large outbound | H/R -> O | cgroup CPU/mem/pids limits, wall-clock and step limits, auto-expiry, disk quota | Yes |
| 12 | Relay compromise or impersonation | M -> all | E2E encryption (relay sees ciphertext), public-key identity of O and R, signed task envelopes | Yes (already decided) |
| 13 | Sandbox escape (kernel/hypervisor bug) | H -> O | microVM > container; keep patched; accept residual risk and say so | Residual |
| 14 | Model provider sees prompts | Nebius | ZDR option; disclose; don't send what is not needed | Disclose |

## Fit for agent-bridge

Layered architecture (each layer reuses existing OSS, nothing custom-crypto):
1. Identity and envelope: public-key identities, signed + encrypted task envelopes (libsodium/age style), relay sees ciphertext. Already in decisions.md.
2. Pack provenance: harness pack = folder + manifest (declared tools, declared egress hosts, declared filesystem needs, permissions) hashed and signed (cosign/sigstore or plain Ed25519 for demo). Listing shows "signed by X, scanned, permissions requested". Manifest is what the owner approves (like an Android permission screen).
3. Execution sandbox: one disposable container per task via OpenClaw's Docker backend (or Docker Sandboxes microVM if confirmed on Windows). Read-only rootfs, non-root, `--cap-drop=ALL`, pids/mem/CPU limits, one read-only bind mount of the granted folder, no host Docker socket, no env secrets. Windows-Home-friendly path = Docker Desktop (WSL2 backend), since Windows Sandbox is unavailable on Home. For Linux owner machines (and the AWS relay host), roadmap upgrade to gVisor (`runsc`) or Kata/Firecracker as a one-line runtime swap.
4. Network: sandbox on an internal-only Docker network (no default route); the only reachable endpoints are a sidecar "model proxy" (adds the Nebius key outside the sandbox, enforces model allow-list, token budget, logs every prompt) and a brokered tool gateway. Optional egress proxy with allow-list for web search (Tavily) so the search query is the only outbound channel and is logged. Block private/link-local ranges (169.254.169.254, RFC1918) per MCP guidance.
5. Tool broker (capability-based): the harness never holds real credentials or filesystem handles; it asks the broker for `read(path)` within the granted folder, `search(query)`, `python(code)` inside a nested no-network sandbox. Each capability is per-task, expiring, and logged. Mirrors CaMeL's capability idea at a coarse level without implementing CaMeL.
6. Rule-of-Two split for long multi-step tasks: planner stage (sees task, no private files, no network) emits a plan; worker stage (sees granted files, no network except model proxy) executes; returner stage (sees only the result, can send to relay). Result must pass a schema, then owner preview, then return. Requester side: result is data, never instructions.
7. Redaction/tokenization for requester context (REMOTE mode): Presidio plus regex/secret scanners (e.g. high-entropy/known key formats) detect fields; replace with stable tokens (`<EMAIL_1>`); map stays on requester; response de-tokenized locally. Present it as best-effort (Presidio itself disclaims completeness) and let the requester see exactly the outgoing payload before sending ("data manifest").
8. PULL mode (code to data): requester downloads the signed pack and runs it in its own layer-3 sandbox against its own folder; owner never sees the data; the owner's value is the harness/prompts, which are then exposed to the requester (conflicts with "harness stays local" decision, so decide per listing: harness author chooses REMOTE-only, PULL-allowed, or both).
9. Audit: append-only hash-chained log of every tool call, prompt, egress attempt, and approval, shown in the observability UI (munder-difflin-style) and exportable as proof. Blocked-egress events are great demo moments.
10. Reputation tied to payment: stars only after a PayPal-captured, accepted task.

Reuse candidates (verify before adopting): OpenClaw Docker sandbox + `openclaw security audit`, Presidio (MIT), cosign/sigstore, Smokescreen egress proxy (named in MCP spec), gVisor `runsc`, CaMeL repo for ideas, nvtrust/Nitro SDK for roadmap.

## Recommendation

Three-week demo scope (do):
- Week 1: per-task Docker sandbox wrapper around the runtime/OpenClaw (internal network, model proxy, single read-only mount, limits), manifest with declared permissions, owner approval screen.
- Week 2: signed pack + hash pin + publish-time scan; Presidio-based redaction with a "what leaves your machine" preview; split planner/worker/returner for the long task; result schema + owner preview.
- Week 3: live "attack theater" demo plus audit view: (a) a malicious marketplace pack tries `curl` to attacker URL and read `~/.ssh` -> blocked egress and missing mount, logged; (b) an injected document tells the agent to email data -> no capability, logged; (c) poisoned result tries to instruct the requester agent -> treated as data. Show the raw secret file never present on the requester machine and never in the relay (ciphertext). Add pay-gated ratings.
- State claims precisely: "protects the owner from the harness, protects the requester from exfiltration by the harness, and minimizes what the owner sees". Do not claim the owner cannot read what is sent.

Roadmap (state as such, do not build): TEE-hosted execution with remote attestation (Nitro Enclaves on the AWS relay/worker, or TDX/SEV-SNP + NVIDIA CC), where the requester verifies the pack hash in the attestation document before releasing a data key (KMS PCR-condition pattern); microVM runtime (Firecracker/Kata) for Linux hosts; CaMeL-style interpreter for provable data-flow; reproducible pack builds and Rekor transparency log; reviewed/curated "verified" tier.

Hackathon fit: AWS Builder (Nitro Enclave or AWS-hosted relay with attestation as a differentiator, if time allows a minimal hello-enclave), Nebius (model proxy gives a clean place to show the NVIDIA Nemotron calls and ZDR), PayPal (rating tied to captured payment; escrow capture only after accepted result).

## Risks

- Overclaiming P2 secrecy: judges with security backgrounds will ask "can the owner read my data?" Answer honestly with data minimization + PULL mode + TEE roadmap.
- Container escape is not impossible (Docker docs themselves say isolation can be incomplete); microVM is stronger but Linux-only; owner machine is Windows Home (no Windows Sandbox).
- Prompt-injection defenses are probabilistic; only architectural controls (no capability, no egress) are reliable.
- Presidio-style detection misses things; redaction can break task quality.
- OpenClaw is designed for a single trust boundary, so we must not rely on its defaults for hostile packs; its own docs say its sandbox is not a perfect boundary.
- Scope creep: building a custom broker/proxy is real work; keep it a thin proxy (HTTP allow-list + file read) rather than a framework.
- Nebius/Amazon/PayPal rules about "new or significantly updated" work and the one-prize limits are unrelated to this topic but remain constraints.
- Marketplace malicious-skill statistics come from secondary summaries.

## Open questions

- Does Docker Sandboxes (microVM) run on the owner's Windows 11 Home machine, and can it be driven programmatically per task? (UNVERIFIED)
- Does Nebius offer ZDR on a hackathon/trial account and is it a request-level flag or account setting? (read https://docs.tokenfactory.nebius.com/legal/privacy-policy)
- Is nested virtualization available on the AWS instance type chosen for the relay, to run Firecracker/Nitro? (Nitro Enclaves require a supported EC2 type; Linux enclaves only.)
- Should the harness author decide REMOTE-only vs PULL-allowed per listing (affects IP protection of the harness)?
- Which OpenClaw version/feature set gives per-task sandbox creation and a per-agent tool policy we can set from outside (`sandbox explain`, `sandbox recreate` exist per docs)?
- Exact CaMeL repo and license for reuse. (UNVERIFIED)
- Can cosign sign/verify a pack tarball offline for a demo without internet/OIDC, or use a local Ed25519 key? (Use the simpler option for the demo.)
