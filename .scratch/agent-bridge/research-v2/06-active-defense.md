# 06 Active defense against context/memory theft (round 2)

Date: 2026-10-07. Scope: detect and block theft of context/memory/data by a foreign pack. Primary sources only; claims not seen in a primary source are marked UNVERIFIED.

## Summary

- No single technique is enough. Layered design: (1) PREVENT by construction (Pull mode, no-egress cell, taint/IFC at the broker), (2) DETECT with cheap deterministic detectors (canaries, scope, volume, egress, encoding), (3) JUDGE ambiguous cases with a guard model, (4) RESPOND on a fixed ladder, (5) RECORD tamper-evidently.
- Real-time block capability differs. Synchronous and deterministic: policy engine at the tool broker (OPA/Cedar), egress proxy deny, Tetragon override+SIGKILL, canary-triggered kill. Asynchronous or advisory: Falco (detection only), LLM guards (probabilistic), gVisor metrics (no workload introspection). seccomp user-notif must NOT be the policy decision point (man page).
- Deterministic detectors carry the kill decision. LLM guards only escalate (pause, ask human), never solely cause a kill or reputation slash, because of false positives.
- NVIDIA tooling that is genuinely usable: NeMo Guardrails (open source; execution rails validate tool calls, arguments and results; PII via Presidio/GLiNER; jailbreak detection; Nemotron/NemoGuard integrations). Nemotron safety models are open weights. Whether Nebius Token Factory HOSTS a Nemotron safety model is UNVERIFIED; a third-party price listing shows Llama-Guard-3-8B on Nebius. Fallback: self-host the guard or run it as an OpenAI-compatible model.
- Honesty point: content-safety guards (Nemotron Safety Guard, Llama Guard) classify harmful-content categories, NOT data exfiltration. Exfil detection must be flow/taint, egress-byte and canary based. Do not market a content-safety model as theft detection.

## Key facts with sources

### Information-flow control and taint
- CaMeL (Google + Carlini): extracts control and data flow from the trusted query so untrusted data cannot affect program flow; capability model enforces policy at tool calls to stop exfiltration through unauthorized channels. AgentDojo: 77% tasks solved with provable security vs 84% undefended. https://arxiv.org/abs/2503.18813
- FIDES (Microsoft): confidentiality and integrity labels, dynamic taint tracking, deterministic policy enforcement, primitives for selectively hiding information; authors characterize the class of properties dynamic taint tracking can enforce (so some are out of reach). https://arxiv.org/abs/2505.23643
- Design patterns for securing LLM agents against prompt injection (14 authors): principled patterns with utility/security trade-offs (exact pattern names UNVERIFIED from abstract alone). https://arxiv.org/abs/2506.08837
- AgentDojo: 97 tasks, 629 security cases, measures hijack via tool-returned data; exfiltration coverage not stated in abstract (UNVERIFIED). https://arxiv.org/abs/2406.13352
- Real-time: yes, deterministic, in-process at broker. Cost: utility loss and engineering. False positives: policy over-restriction, not statistical.

### Deception
- Canarytokens (Thinkst): "motion sensors"; 40+ token types incl. DNS, cloud credentials (AWS, Azure), documents, executables, Kubernetes config; alert when touched. https://docs.canarytokens.org/guide/ and https://thinkst.com/canarytokens
- Caveat: hosted Canarytokens phone home over DNS/HTTP, which is itself an outbound call. Our design checks canaries LOCALLY (file-access hooks, egress/proxy content match, memory-read log). That is our design choice, not a Thinkst feature.
- Real-time yes. False positives very low if canaries sit where legitimate packs never go; risk is `grep -r` style walkers touching in-scope canaries, so keep most canaries outside the granted scope.

### Egress control and DLP
- Repo fact: cell sits on a Docker `--internal` network with only the sidecar as peer (architecture-options.md 3.1), so the proxy sees every outbound byte and can do string/entropy/size/rate checks synchronously.
- NeMo Guardrails PII providers: GLiNER, Presidio, Private AI. https://docs.nvidia.com/nemo/guardrails/latest/index.html

### Syscall / eBPF
- Tetragon: in-kernel filtering; can alert or "kill the process before it has a chance to complete the syscall". Enforcement: Override return value (synchronous; only syscalls and security-check functions) and Signal/SIGKILL. Docs warn SIGKILL in `write()` does not guarantee data is not written, so combine Signal with Override. https://tetragon.io/docs/overview/ and https://tetragon.io/docs/concepts/enforcement/
- Falco: monitoring and detection agent producing alerts; response via ecosystem (Falcosidekick). Modern eBPF is default driver. Falco Talon not covered in fetched page (UNVERIFIED). https://falco.org/docs/
- seccomp user notification: supervisor can allow/deny/emulate, but man page says it "must not be used to make security policy decisions" (TOCTOU, PID reuse, bypass by stacking filters). Use static seccomp allow-lists for policy; unotify only for logging. https://man7.org/linux/man-pages/man2/seccomp_unotify.2.html
- gVisor metrics "do not provide introspection capabilities into the workload"; its separate trace-point (seccheck) facility was NOT verified (UNVERIFIED). https://gvisor.dev/docs/user_guide/observability/
- eBPF needs a Linux kernel; Windows/Mac requesters need a Linux VM, and eBPF in WSL2 on Win11 Home is UNVERIFIED.

### Policy engines
- OPA: CNCF graduated, Rego, decouples decision from enforcement, Go library / WASM / server, decision logs. https://www.openpolicyagent.org/docs/latest/
- Cedar: principal/action/resource/context requests, explicit permit/forbid, optional schema, designed for analyzability and performance. https://docs.cedarpolicy.com/overview/terminology.html (default-deny and forbid-wins semantics not confirmed on that page, UNVERIFIED there).
- Real-time yes; no latency benchmark fetched (numbers UNVERIFIED).

### LLM guards and classifiers
- NeMo Guardrails: input, retrieval, dialog, EXECUTION (validates tool and function calls, arguments, results) and output rails. Integrates Llama 3.1 NemoGuard 8B Content Safety, NemoGuard Jailbreak Detection NIM, Topic Control NIM, PII masking; third parties (ActiveFence, Cisco AI Defense, etc.). No latency figures in docs fetched. https://docs.nvidia.com/nemo/guardrails/latest/index.html and https://docs.nvidia.com/nemo/guardrails/latest/about/rail-types.html
- Llama-3.1-Nemotron-Safety-Guard-8B-v3: classifies prompt and response safe/unsafe, 23 categories, JSON output, 9 languages (20+ zero-shot), NVIDIA Open Model License plus Llama 3.1 license, released 2025-10-28. Content safety only. https://huggingface.co/nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3
- Llama Guard 3, Prompt Guard (injection/jailbreak), CodeShield: https://github.com/meta-llama/PurpleLlama . LlamaFirewall = PromptGuard 2 + Agent Alignment Checks (chain-of-thought auditor, experimental) + CodeShield + regex/LLM custom scanners. https://arxiv.org/abs/2505.03574
- Nebius Token Factory: OpenAI-compatible at https://api.tokenfactory.nebius.com/v1/ ; model list via `/v1/models` (verbose); docs index https://docs.tokenfactory.nebius.com/llms.txt . Primary docs fetched list no guard/Nemotron-safety IDs. Secondary listing shows meta-llama/Llama-Guard-3-8B and Nemotron Super 49B / Ultra 253B (UNVERIFIED): https://futureagi.com/llm-cost-calculator/nebius
- Red-teaming: garak (NVIDIA, Apache-2.0; probes promptinject, leakreplay, encoding, dan, malwaregen; targets OpenAI-compatible endpoints) https://github.com/NVIDIA/garak ; PyRIT (Microsoft, MIT) https://github.com/microsoft/PyRIT . They test model behavior pre-release; they are not runtime defenses.
- Real-time: hundreds of ms per call (UNVERIFIED), so only gate events (tool results entering context, final output), not syscalls. False positives: material.

## Ranked techniques (for blocking context/memory theft)

| Rank | Technique | Real-time block | Catches | FP risk | Notes |
|---|---|---|---|---|---|
| 1 | Prevention: Pull mode + no-egress cell + broker-only I/O | structural | all but broker channel | none | Defense handles the remainder |
| 2 | Egress proxy with canary/taint/DLP matching | yes, sync | direct and encoded leaks | low | Covers search queries and result text |
| 3 | Canaries (files, memory entries, fake creds) | yes | scanning/greedy packs, out-of-scope reads | very low | Local detection only |
| 4 | Broker policy (OPA/Cedar): scope, rate, sequence | yes, sync | out-of-scope reads, volume, bad tool sequences | low-med | Every tool call passes here |
| 5 | Taint/IFC (CaMeL/FIDES style) | yes | data-derived args reaching sinks | med utility cost | Start coarse |
| 6 | Tetragon override + SIGKILL | yes, sync | forbidden syscalls, exec, connect | low | Linux only, depth layer |
| 7 | Guard LLM on gated events (NeMo rails, Nemotron/Llama Guard, Prompt Guard) | near real-time | injection, jailbreak, harmful content; weak on exfil | high | Escalate only |
| 8 | Falco | no (alerts) | like 6, detect only | low-med | Telemetry |
| 9 | garak / PyRIT | no | pre-publish pack testing | n/a | Publish pipeline gate |
| x | seccomp unotify as policy | not recommended | | | man page forbids |

## Fit for agent-bridge

- Sensors sit on three choke points we already own: tool broker, egress/model-proxy sidecar, result path. Kernel layer optional depth.
- Pull mode: sensors run on the requester machine under the requester's supervisor, not the pack owner's, so verdicts are trustworthy to the requester. Hosted mode: sensors run on the owner machine, so kills and verdicts are owner-attested only; label this (consistent with architecture-options.md fatal flaw 2). In Hosted mode also send minimized/tokenized context and plant honeytokens in the sent payload; their reuse is detectable only if the leak surfaces (weak).
- NVIDIA/Nebius story: Nemotron as agent model via Nebius; NeMo Guardrails wrapping the broker (execution rails) and the result (output rail) with Presidio/GLiNER PII; a Nemotron or Llama guard as judge via Nebius if hosted (verify with `/v1/models`) else self-hosted; garak in the pack publish pipeline.
- Memory linkage: memory entries carry labels (owner, sensitivity, scope, grant). Canary memory records live in the store with per-run values; taint labels propagate from memory reads to sinks. A pack gets read access via the broker and a per-run scratch overlay for writes, merged only after review, never write access to the global store. The memory design needs a canary-injection hook.

## Recommendation: concrete detector set

Deterministic (can kill):
- D1 Canary file touch: decoys outside granted scope (fake .ssh key, .env, passwords.txt, wallet) and a few inside; any read = CRITICAL.
- D2 Canary memory entry: decoy memory records with unique per-run tokens; the token appearing in any outbound byte (proxy, search query, tool arg, result, model request to unapproved endpoint) = CRITICAL.
- D3 Scope violation: path outside granted root, symlink or `..` escape, proc/device access, memory-store path probing = HIGH; repeated = CRITICAL.
- D4 Volume: files or bytes read above task budget, whole-tree enumeration, /out above cap = HIGH.
- D5 Egress attempt: any connect not to sidecar, DNS lookups, raw sockets = CRITICAL (cell has no route, so it is intent evidence).
- D6 Egress content: high-entropy blob, base64/hex/gzip over threshold in query, tool args or result; path strings in URLs; overlong queries; markdown image/link carrying data = HIGH.
- D7 Taint-to-sink: arguments to search/web/payment/result tools derived from sensitive-labelled reads without declared declassification = HIGH, deny call.
- D8 Tool-sequence: sensitive read followed by network-capable tool in the same phase (Rule-of-Two break), or tool not in manifest = HIGH, deny.
- D9 Probing: 3 or more denied calls, rapid retry loops = escalate.
- D10 Pack drift: pack hash differs from signed listing, new tool or file at runtime = CRITICAL.
- D11 Kernel (Tetragon, Linux): exec of shell/curl/nc, ptrace, mount, unshare, setns, bpf, keyctl, writes to rootfs = CRITICAL, override + SIGKILL.
- D12 Result path: result contains canaries, secret patterns, paths, oversize or non-schema fields = reject; canary = CRITICAL.
Probabilistic (escalate only):
- D13 Guard model on tool results entering context and on final output: injection/jailbreak (Prompt Guard, NemoGuard jailbreak), content safety. Over threshold = PAUSE and ask human.
- D14 Behavioral baseline vs the pack's history (files per task, tool mix, tokens): anomaly = flag, lower ranking, review; never kill alone.

Response ladder:
0. LOG every event in a hash-chained audit log.
1. DENY the single call with a generic error (no oracle for the attacker).
2. PAUSE the cell and ask the data owner (desktop or phone); timeout means kill.
3. KILL the cell: container kill, tear down network, wipe scratch, invalidate per-run credentials and session keys.
4. QUARANTINE: freeze logs and cell filesystem into a read-only forensic bundle; discard the result (never delivered); mark memory overlay unmerged.
5. REVOKE: block the pack hash in the requester allowlist and hub registry; VOID PayPal escrow; refuse future runs.
6. SLASH reputation, only on deterministic CRITICAL evidence (D1, D2, D5, D10, D11) and after confirmation by a second independent detector or human review; guard-only evidence never slashes; appeal path.
7. NOTIFY requester, pack owner (minimal evidence, no leaked content), hub.
8. RECORD a signed incident entry with evidence hashes, not contents.
Policy: CRITICAL = levels 3, 4, 5, 7, 8 immediately, 6 after confirmation. HIGH = 1, then 2 if repeated. Guard-only = 2. Fail closed: a sensor heartbeat lapse pauses or kills the cell.

Build order: D1-D5, D10 and ladder 0-4 first; D6-D9, D12 next; guard models and NeMo Guardrails; Tetragon; baselines; publish-time garak/PyRIT gate; a "red-team pack" regression suite that must always be blocked.

## Risks

- Covert channels remain (timing, natural-language steganography in queries or results). Detectors reduce bandwidth, not to zero; say so.
- Hosted mode: owner is root and controls the sensors, so detection is self-attested and does not protect requester from the owner.
- Kernel enforcement: SIGKILL may not stop an in-flight write (Tetragon docs); the no-egress structure is the real barrier.
- Guard false positives and adaptive evasion (general knowledge, no primary source fetched, UNVERIFIED); guards target content safety, not exfil.
- Canary framing: a malicious requester could plant canaries to frame a pack. Mitigation: supervisor-only placement with per-run secrets and a signed placement record.
- Taint/IFC utility cost (CaMeL 77% vs 84%); over-blocking hurts the marketplace.
- Windows/Mac requesters lack eBPF; need a Linux VM; WSL2 eBPF UNVERIFIED.
- Abuse of the incident system by false reports; needs evidence requirements and appeal.

## Open questions

- Does Nebius host any Nemotron safety/guard model, or only Llama-Guard-3-8B? Check `/v1/models?verbose=true` with a key.
- Latency and cost of NeMo Guardrails execution rails with a remote Nebius judge: measure.
- How canary placement stays invisible to the pack while memory remains queryable (needs memory-design hook).
- Who adjudicates appeals and how slashing and PayPal VOID tie to evidence.
- Is gVisor seccheck usable for Pull-mode monitoring (UNVERIFIED), or rely on proxy + broker + Tetragon?
- Can a requester ever verify a Hosted-mode kill/no-kill claim without TEE attestation (likely no).
