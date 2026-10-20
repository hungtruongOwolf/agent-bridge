# 05 - Pull mode isolation: foreign pack runs on the requester machine, nothing reaches the author

Date: 2026-10-07. Round 2. Topic: exact leak inventory, closing each channel, keyless model access, covert channels, author IP protection, active defense.

## Summary

- Pull mode can give a strong, structural guarantee: the pack author receives zero bytes derived from the requester data, provided the pack runs in a sandbox with no network device except one mediated channel to a requester-controlled supervisor/proxy, and that proxy only forwards model calls to Nebius under the REQUESTER's credentials. The guarantee comes from topology (no route), not from detection.
- What can still leave is enumerable: (1) model prompts to Nebius (the requester's own provider, not the author), (2) the result the requester chooses to share, (3) the requester's own later actions (ratings, receipts, bug reports), (4) pack update/license/registry calls made by the requester runtime (not the pack), (5) side channels visible only to observers on the allowed path (Nebius, network). None reach the author unless the author also controls the observer or the requester relays it.
- The hard problem is author IP, not requester data. A pack on someone else's machine can be read. Prompt secrecy is not achievable by obfuscation (prompt extraction works). Honest options: accept open packs, license plus watermark, split compute (reintroduces data flow), or TEE (heavy). Recommendation: Open/licensed packs in Pull; "Protected" packs are Hosted-only.
- Active defense is a second line: hard policy events (blocked egress, canary touch, out-of-scope read) kill the sandbox, quarantine the pack hash, revoke, record. It is heuristic and must not be sold as the guarantee.

## Key facts with sources

Isolation primitives (verified):
1. Docker `--internal` networks: containers talk to each other but not other networks; no default route, firewall drops traffic to/from other networks. CAVEAT: "communication with the gateway IP address (and thus appropriately configured host services) is possible". Source: Docker CLI docs, network create: https://git.coopcloud.tech/p4u1/docker-cli/src/branch/28.x/docs/reference/commandline/network_create.md
2. NVIDIA OpenShell (docs show v0.1.2; maturity not stated): Gateway / Supervisor / Sandbox / Compute Driver. "The mediated channel to the supervisor is the workload's only allowed egress path. The outer fence denies everything else." Docker/Podman disable container networking; Kubernetes uses NetworkPolicy; VMs have no NIC. Supervisor adds credentials only to requests bound for approved endpoints; the agent never sees real credentials. Landlock for filesystem, seccomp user notification for network ops. DNS queries are handed to the supervisor. Source: https://docs.nvidia.com/openshell/latest/about/architecture.html
3. OpenShell/NemoClaw inference routing: calls to `https://inference.local` are handled by the proxy, which strips sandbox-supplied credentials and injects backend credentials; unknown hosts blocked and surfaced for approval. This is the keyless model-call pattern and is NVIDIA-native. Source: https://docs.nvidia.com/nemoclaw/latest/about/how-it-works . Whether OpenShell runs on Windows 11 Home/WSL2 and can route to remote Nebius (not only a local GPU server): UNVERIFIED.
4. Anthropic sandbox-runtime (reference design): all egress via host HTTP and SOCKS proxies; Linux removes the network namespace so traffic goes only via Unix-socket proxies; allow-only domain list; resolved-address check. Its own caveats: domain fronting may bypass filtering; broad allowed domains (e.g. github.com) enable exfiltration; on Windows the system-resolver DNS (getaddrinfo) is not fenced. Source: https://github.com/anthropic-experimental/sandbox-runtime
5. gVisor: user-space kernel (Sentry) that does not pass app syscalls directly to the host; Netstack default is safer than host-network passthrough. Sources: https://gvisor.dev/blog/2020/04/02/gvisor-networking-security/ , https://gvisor.dev/blog/2019/11/18/gvisor-security-basics-part-1/
6. Firecracker: KVM boundary plus seccomp, cgroups, namespaces, jailer, minimal device model. Source: https://github.com/firecracker-microvm/firecracker/blob/4a3e9bd76d9fc57a3538c1aeb7e5687de43a0efa/docs/design.md

Model provider:
7. Nebius Token Factory: OpenAI-compatible, base URL `https://api.tokenfactory.nebius.com/v1/`, Bearer API key, key shown once at creation. Source: https://docs.tokenfactory.nebius.com/api-reference/introduction . Per-key scopes, spend caps, project keys: UNVERIFIED (only a search snippet mentioned RBAC/project keys).
8. Nebius privacy policy: processes request/response metadata (timestamps, status, error codes) to troubleshoot, bill, improve services; it does not explicitly state whether inference inputs/outputs are retained or used for training. A Token Factory privacy page snippet lists speculative-decoding inputs/outputs used to train smaller models per ToS (snippet only). So do NOT claim zero retention; present Nebius as a third party the requester already trusts. Sources: https://docs.nebius.com/legal/privacy ; https://docs.tokenfactory.nebius.com/legal/privacy-policy . ZDR toggle mentioned in round 1: UNVERIFIED here.

Side channels and prompt secrecy:
9. Whisper Leak: encrypted streaming LLM traffic leaks prompt topic through packet size/timing (>98% AUPRC for many of 28 models in the PoC); providers added random padding ("obfuscation" field) which Microsoft says reduces it to no practical risk. Relevant to observers on the model path (Nebius/network), not to the pack author. Source: https://microsoft.com/en-us/security/blog/2025/11/07/whisper-leak-a-novel-side-channel-cyberattack-on-remote-language-models/ . Whether Nebius pads: UNVERIFIED.
10. Prompt extraction: simple text attacks reveal prompts with high probability, even against deployed defenses. Prompts should not be treated as secrets when the executor controls the model call. Source: https://arxiv.org/abs/2307.06865
11. NVIDIA Hopper confidential computing: GPU TEE with hardware root of trust, signed attestation, SPDM link to a CPU CVM (SEV-SNP or TDX). Sources: https://docs.nvidia.com/nvtrust , https://arxiv.org/html/2409.03992v4 . Availability behind Nebius Token Factory: UNVERIFIED (assume no).
12. NeMo Guardrails with Nemotron safety models (content safety, topic control, jailbreak) exist as NIM microservices. They are content filters, not exfiltration barriers. Sources: https://docs.nvidia.com/nemo/guardrails/home , https://docs.nvidia.com/nim/llama-3-1-nemotron-safety-guard-8b/latest/integrate-guardrails.html

## Leak inventory and how to close each

Threat: author-written pack code, prompts, tool definitions, MCP configs, malicious dependencies. Goal: no byte derived from requester data reaches the author.

| # | Channel | Reaches author? | Closure |
|---|---|---|---|
| 1 | Direct network (TCP/UDP/ICMP/raw) | Yes if open | No NIC/route in the sandbox; only a Unix socket or internal link to the supervisor. Startup self-test proves the sandbox cannot connect anywhere. |
| 2 | DNS tunnelling | Yes if resolver reachable | No resolver in sandbox; supervisor resolves only allowlisted names; pack addresses `inference.local` only. Use Linux/WSL2/VM (Windows system-resolver caveat). |
| 3 | Telemetry/analytics SDKs in deps | Yes via 1/2 | Same closure; deps baked into an immutable image pinned by hash at build; no runtime pip/npm. |
| 4 | Model prompts to the provider | Not author; Nebius sees them | Requester's own Nebius account via sidecar. Disclose. Optional local Nemotron tier (hardware UNVERIFIED). |
| 5 | Pack picks its own endpoint/model | Yes if allowed | Destination and model IDs fixed by requester policy, not pack manifest; manifest declares only a model class. |
| 6 | API key theft | Yes if key in env/file | Key only in supervisor. Pack gets an ephemeral run token valid only against the sidecar, bound to run ID with call/byte budget. |
| 7 | Result returned | Not author | Goes to requester UI only; treat as untrusted text; no auto-loading remote images/links (markdown beacon exfil). |
| 8 | Requester follow-ups (rating text, receipt, share, bug report) | Yes, via the human | Ratings structured (stars/tags); free text previewed; receipts to hub carry hashes and counters only; no auto-attach. |
| 9 | Update/license/registry calls | Metadata only | Done by requester runtime, never during a run; via hub mirror; license is an offline-verifiable signature. |
| 10 | Timing/size of model calls | Only if observer is author | No author-controlled observer. Residual observers: Nebius, network (Whisper Leak class). Mitigate: provider padding (UNVERIFIED), non-streaming, per-run budgets. Accepted residual. |
| 11 | Persistent state between runs | Yes if author gets volume | Ephemeral FS per run; destroyed after; export only via result gate. |
| 12 | Shared memory/context store | Yes if pack reads broad memory | Pack sees only a requester-assembled, read-only slice for this task. Pack-proposed memory writes are quarantined data, applied after review with provenance and trust tag. |
| 13 | Tool exfil (web search, URL fetch, email, MCP) | Yes | Private-data runs: no web/fetch/email tools. Search only in a data-free phase (taint rule: once private data is in context, egress tools are disabled). Tavily queries would carry data to a third party. |
| 14 | Sandbox escape | Yes | Defense in depth: microVM (Firecracker) or gVisor over plain runc; seccomp; Landlock; read-only rootfs; read-only grant mount; drop caps. A kernel/hypervisor 0-day defeats it. |
| 15 | Host service on bridge gateway (Docker `--internal` caveat) | Maybe | Do not bind supervisor to the gateway IP; use sidecar container or Unix socket; firewall the gateway. |
| 16 | Steganography in the result | Only via 7/8 | Cannot be removed; preview and human decision on what is shared. |
| 17 | Hardware side channels | Theoretical | Out of scope; accepted. |

Bottom line: with 1, 2, 5, 6, 11, 13 closed and no author-controlled endpoint reachable, no technical channel to the author remains except steps the requester takes. That is the claim to make. Do not claim "nothing leaves Nebius" or "provider retains nothing".

## Running the pack with only a local model proxy

- Requester machine: Supervisor (trusted, holds Nebius key), Sandbox (untrusted pack, no NIC), Result Gate.
- Pack uses an OpenAI-compatible client with base URL `http://inference.local` or a Unix socket. Sidecar: authenticates run token; enforces Nemotron model-ID allowlist, max tokens, call count, total bytes; swaps in the requester key; forwards to `https://api.tokenfactory.nebius.com/v1/`; strips unknown fields/headers (pack cannot inject metadata or user IDs); writes hash-chained audit records (hashes of request/response; content only locally, optional).
- Implementation order: (1) NVIDIA OpenShell, if it fits (NVIDIA story; verify Nebius upstream and Windows path); (2) Docker `--internal` network plus key-holding sidecar container (round 1 spike S3); (3) Firecracker/gVisor for a stronger boundary.
- Pack tools and MCP servers run inside the sandbox without network. Tools needing network are declared in the manifest and refused in private-data runs.

## Protecting author IP on someone else's machine

Visible to requester inevitably: pack files, every prompt through the proxy they control, tool schemas, behaviour.
- Obfuscation/encryption on disk: weak; decrypted at run time; prompt extraction is easy (arXiv 2307.06865). Do not market it as protection.
- Signing plus licensing (feasible, honest): signed pack; license token bound to requester, version, expiry, run count, verified offline. Deters casual redistribution, not a determined copier. Add per-license watermarks (canary phrases in prompts/examples) for leak tracing, plus listing terms.
- Open packs (accept it): value is curation, eval scores, maintenance, updates, reputation, as in open source. Matches Open Source mini challenge (Apache-2.0) and star ranking. Recommended Pull default.
- Remote-held prompt via blinded calls: secret prompt runs on an author service; requester sends abstracted inputs. This breaks the Pull guarantee unless inputs are data-free (e.g. plan from the task text only, data steps run locally). Even then outputs let a requester distil behaviour. Research item; weak guarantees.
- TEE: attested confidential VM on the requester machine hides the author's secret from the requester, but the model call still reaches Nebius in clear (Nebius sees it) and needs hardware and attestation infrastructure. Roadmap diagram only.
- Practical conclusion: Pull = open or licensed packs. Authors needing secrecy publish Hosted-only, where code and prompts stay on their machine (and the requester accepts the host sees the data).

## Active defense (second line)

Signals, deterministic first:
- Any blocked connect, DNS lookup, raw socket, seccomp-denied network syscall.
- Canary access: honey files/records in the granted folder and in the context slice; reads not needed by the task, or canary text appearing in model requests/tool args.
- Reads outside the grant (env, /proc, key files, other packs); writes outside run scratch; unexpected processes.
- Model-request anomalies: unknown fields, large base64/high-entropy blobs, size out of proportion to input, call count over budget, unlisted model ID.
- Optional rail: Nemotron safety/topic control on tool args/results to flag injection. It detects content classes, not covert encoding.
Response ladder (automatic): freeze and kill sandbox; destroy scratch; revoke run token; quarantine pack hash locally; hash-chained incident record; notify requester (desktop + phone); optional hub report with pack hash, rule ID, counters only (no content), letting the hub suspend the listing pending appeal; author key goes onto a signed revocation list pulled by all runtimes.
Limits: cannot see steganography inside a legitimate prompt; false positives need an appeal flow; a pack may behave when watched, so rely on topology, not detection.

## Fit for agent-bridge

- Nebius x NVIDIA: runtime calls Nemotron on Nebius through the supervisor with the model ID visible; OpenShell as sandbox/policy engine and NeMo Guardrails/Nemotron safety as a rails layer is a real, citable fit. Be precise: rails are not the exfil barrier.
- PayPal: license token and per-run receipt bind to payment capture; receipts carry hashes only.
- Amazon mini: Apache-2.0 packs/spec (Open Source); hub on AWS (AWS Builder) unaffected.
- Demo (Pull proof): run a deliberately malicious pack that tries curl, DNS lookup, key read and canary exfil; show blocked events, kill, quarantine, hash-chained incident, untouched data folder, and a successful Nebius call with the pack holding no key.

## Recommendation

1. Pull is the private-data default with the topology guarantee: no NIC, supervisor holds key, fixed endpoint and model class, ephemeral scratch, read-only grant, no network tools in private-data runs. Spike OpenShell first; fallback Docker `--internal` plus sidecar (not on the bridge gateway); later Firecracker/gVisor.
2. Publish a precise guarantee table: guaranteed (author learns nothing from the run); not guaranteed (Nebius sees prompts, requester's own sharing, sandbox 0-days, provider-side side channels).
3. IP: open or signed-and-licensed packs with per-license watermarks; no prompt-secrecy claims; Protected tier = Hosted only; TEE and split-plan as roadmap.
4. Active defense as automatic kill/quarantine/revoke/record, with signed revocation list and canaries in data and memory slices.
5. Memory interface: pack sees a requester-assembled read-only slice; pack-proposed writes are untrusted data applied after review (align with the memory design topic).

## Risks

- Sandbox/hypervisor escape not eliminated; WSL2/Docker on Windows Home adds edge cases.
- OpenShell is young (v0.1.2); API churn; Nebius upstream routing UNVERIFIED.
- Nebius retention/training for inference inputs not clearly stated; do not promise privacy beyond the pack author.
- Whisper-Leak-class side channels at provider/network; Nebius padding UNVERIFIED.
- Open packs get copied; marketplace value must come from curation, evals, updates.
- Social engineering: a result persuading the requester to send data back to the author.
- False positives in active defense hurting honest authors.
- Supply chain: pack dependencies per version must be re-verified.

## Open questions

1. Does OpenShell run on Windows 11 Home via WSL2, and can its inference router target Nebius Token Factory rather than a local GPU?
2. Does Nebius offer per-key scopes, spend caps, ZDR, and padded streaming?
3. Require non-streaming model calls in private-data runs to narrow the timing residual?
4. Is an air-gapped local Nemotron tier in scope (hardware)?
5. Protected tier = Hosted only (recommended) or invest in split-plan research?
6. Which sharing flows (ratings, receipts) may carry free text, given the human relay channel?
7. Windows-native sandbox (WFP egress filter) vs WSL2-only for the "any OS" demo?
