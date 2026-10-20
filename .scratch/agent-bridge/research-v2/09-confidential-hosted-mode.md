# 09 - Can Hosted mode get a real confidentiality guarantee? (TEE + remote attestation)

Date: 2026-10-07. Round 2. Sources are primary docs fetched this session; claims not read in a primary source are marked UNVERIFIED. "My estimate" marks my own engineering judgement, not a sourced fact.

## Summary

- Yes, but only conditionally. A TEE with remote attestation can make Hosted mode "the host operator cannot read your data, and you verified which code was running". It cannot make it "nobody can see your data".
- Two adversaries must be separated. (1) The host operator (the pack owner or cloud admin): a TEE addresses this one. (2) The pack code itself: it runs inside the TEE and sees plaintext by design. A TEE does not stop a malicious pack from copying data into its result or to an allowed endpoint. Pull mode, egress deny and active defense are still required on top.
- Inference is the weak link. Nitro Enclaves have no GPU path (UNVERIFIED in primary docs; enclaves only get a vsock to the parent). So an enclave must call an inference API, and Nebius Token Factory then sees the prompts in plaintext. I found no documented Nebius confidential-computing product. Only a Nebius blog describing a partner PoC (attested TLS, private LLM inference) on Nebius infrastructure. To keep prompts inside a TEE you need a GPU confidential VM (Azure NCCadsH100v5, GCP A3 High with TDX) running an open Nemotron model locally.
- Hardware caveat: TEE.fail (Oct 2025) shows a sub-$1000 DDR5 interposer can extract attestation keys on Intel TDX/SGX and AMD SEV-SNP and "borrow" NVIDIA GPU attestations. Intel and AMD call physical interposer attacks out of scope. So a TEE on a machine the owner physically controls (an owner's home box) gives weak assurance. It is meaningful when a cloud provider with physical security runs the host.
- Realistic hackathon proof: a Nitro Enclave on one EC2 instance, a client that verifies the attestation document and then encrypts the task to the enclave key, TLS to Nebius terminated inside the enclave, plus a "tamper changes the measurement, client refuses" scene. Fits the AWS Builder challenge. My estimate is 2-4 days.
- Recommendation: Pull stays the default for private data. Add "Sealed Hosted" as a third, clearly labelled tier built on Nitro (proof) with a documented path to GPU CVMs. Ship an honest label that lists what is and is not protected.

## Key facts with sources

### AWS Nitro Enclaves
- Enclaves are isolated VMs with "no persistent storage, interactive access, or external networking", only a local socket to the parent. Root/admin on the parent cannot access enclave data. Source: https://docs.aws.amazon.com/enclaves/latest/user/nitro-enclave.html
- CPU/memory isolation comes from the Nitro Hypervisor. Works on most Intel, AMD, Graviton instance types, up to 4 enclaves per parent, no extra charge beyond EC2. Same page. Parent instance type list there includes GPU families (G5, P5 etc.), but the enclave itself only has vsock; GPU access from inside an enclave is not documented (UNVERIFIED, secondary sources say none).
- Attestation document: CBOR/COSE_Sign1, signed by the Nitro PKI (root fingerprint published), contains PCRs, nonce, optional public_key and user_data. Source: https://docs.aws.amazon.com/enclaves/latest/user/verify-root.html
- Challenge-response: the verifier sends a nonce, the enclave requests a document including its generated public key, the verifier encrypts data to that key so only the enclave can decrypt. Source: https://github.com/aws/aws-nitro-enclaves-nsm-api/blob/main/docs/attestation_process.md
- AWS KMS key policies can require enclave measurements, so a data key is released only to a matching enclave. Source: nitro-enclave.html above (KMS section).
- Known gap: Nitro trust is "trust AWS" (closed hypervisor, AWS PKI). No independent hardware vendor and no open firmware. Inference from the docs, not stated by AWS.

### Intel TDX, AMD SEV-SNP, Azure, GCP
- Azure confidential VMs: AMD SEV-SNP or Intel TDX, attestation inside the guest, boot refused if the platform is not attested, vTPM, sizes include NVIDIA H100 NCCadsH100v5. Source: https://learn.microsoft.com/en-us/azure/confidential-computing/confidential-vm-overview. Doc warns "protection levels differ based on your configuration", for example Microsoft-managed keys.
- GCP: A3 High (a3-highgpu-1g) Intel TDX + NVIDIA H100 confidential VM. GPU workloads need spot or flex-start provisioning, GPU CC mode enabled after creation, driver 580+, no multi-node clusters, no reservations. Source: https://docs.cloud.google.com/confidential-computing/confidential-vm/docs/create-a-confidential-vm-instance-with-gpu
- Open-source stacks: dstack (Apache-2.0; Docker in TDX/SEV CVMs with NVIDIA CC GPUs, reproducible OS images, per-app keys, audited, used by OpenRouter and NEAR AI per its README) https://github.com/Dstack-TEE/dstack ; Confidential Containers (Kata + Trustee attestation/key broker; TDX/SNP mature, some clouds under development) https://confidentialcontainers.org/docs/overview/
- Prior art for "verified private inference": Tinfoil (SDKs verify attestation on each connection, open-source code) https://docs.tinfoil.sh/ ; Apple Private Cloud Compute (stateless compute, no privileged runtime access, non-targetability, public binary transparency log) https://security.apple.com/blog/private-cloud-compute/

### NVIDIA confidential computing
- H100 CC needs a CPU TEE. The GPU cannot touch CVM memory directly; transfers go through encrypted bounce buffers. In CC-on mode performance counters are disabled to limit side channels. Overhead is at the CPU-GPU link (about 4 GB/s encryption bound in NVIDIA's measurement), not GPU compute. Source: https://developer.nvidia.com/blog/confidential-computing-on-h100-gpus-for-secure-and-trustworthy-ai/
- Attestation: NRAS, RIM and OCSP services plus Python/C++ SDKs. Source: https://docs.nvidia.com/attestation/index.html (page did not give evidence details).

### Nebius
- Nebius docs homepage lists VMs, GPU clusters, K8s, storage, KMS, SecretStash; no confidential computing or Token Factory retention text visible there. https://docs.nebius.com/
- Nebius blog: partner team BioHackCloud built an attested-TLS PoC and private LLM inference on Nebius infrastructure; not described as a standalone product. https://nebius.com/blog/posts/elixir-biohackathon . Whether Nebius sells H100/Blackwell CC VMs: UNVERIFIED, ask Nebius staff at the hackathon.
- Token Factory: ZDR option exists per earlier research (research/05, research/13; read the privacy policy before claiming). The provider sees prompts in all designs.

### Attacks and limits
- TEE.fail: DDR5 interposer, about $1000, extracts ECDSA attestation keys from TDX and SEV-SNP (even with Ciphertext Hiding), forges attestation quotes, lets attackers borrow NVIDIA GPU attestations. Intel acknowledged; AMD-SB-3040 says no SEV-SNP firmware update planned, interposer attacks out of scope; guidance is to ensure physical security. Source: https://tee.fail/
- NeMo Guardrails: input/retrieval/dialog/execution/output rails, content safety, topic control, PII masking, jailbreak detection, Nemotron/NemoGuard safety models. Not an exfiltration control. Source: https://docs.nvidia.com/nemo/guardrails/latest/index.html

## Fit for agent-bridge

### Realistic architecture ("Sealed Hosted")
1. Owner publishes a pack. The marketplace builds it reproducibly into an enclave image (EIF on Nitro; a CVM image on dstack/CoCo). The listing carries the expected measurement (PCRs), the pack hash, and the build recipe. Anyone can rebuild and compare.
2. Requester client: sends a nonce, gets the attestation document, verifies the signature chain to the pinned Nitro root, PCR0 equals the listed pack measurement, nonce is fresh, and extracts the enclave public key.
3. Client encrypts the task and data (HPKE or libsodium sealed box to the attested key). Optionally releases a per-task data key through a key broker (KMS condition keys on Nitro) so key release is gated on measurement.
4. Inside the enclave: the pack runs with the task. All egress goes through an in-enclave allowlist proxy; the parent only sees TLS ciphertext, destination and size metadata (parent forwards via vsock).
5. Inference options:
   - A: enclave calls Nebius Token Factory (Nemotron). TLS terminates inside the enclave, so the owner cannot read prompts. Nebius can (ZDR on). Use a hub-issued per-task Nebius key, never the owner's key, so the owner cannot read provider-side logs or usage. This is the hackathon-valid path.
   - B: GPU CVM (Azure NCCadsH100v5 or GCP A3 High TDX) runs an open Nemotron model locally; no third party sees prompts. Strongest, expensive, minutes of provisioning, Nebius required-use rule must still be met elsewhere (UNVERIFIED rules).
   - C: small CPU model inside the enclave: weak quality, not recommended.
6. Result: signed by the enclave key, returned encrypted to the requester, passes the existing result guard (schema, inert render, human accept).
7. Active defense inside the enclave: watchdog and egress proxy detect canary hits, off-allowlist destinations, oversize or high-entropy outputs, memory-dump or env-read attempts; on detection kill the task, wipe keys, emit a signed incident record to the hub, hub revokes the pack hash (client verifiers refuse revoked measurements). Honest limit: the watchdog is trusted by measurement, but detection of subtle semantic exfiltration in result text is heuristic.
8. Bonus for the marketplace: the same TEE hides the owner's proprietary harness from the requester (mutual confidentiality). Plain Pull mode exposes the harness to the requester's machine.

### Hackathon-grade proof (my estimate, 2-4 days)
- One Nitro-capable instance, one enclave app (Python or Rust) with a tiny pack, vsock proxy, in-enclave TLS to Nebius.
- Client verifier (a few hundred lines, use an existing COSE/CBOR library).
- Demo scenes: (1) attestation verified, PCR shown vs listing; (2) owner with root on the parent instance tries to read the enclave, fails; (3) owner rebuilds a modified pack, PCR0 changes, client refuses; (4) malicious pack tries off-allowlist egress, gets killed, hash revoked. Fits AWS Builder and the Nebius model-ID story. Costs: Nitro has no extra charge; EC2 price, GPU CVM price UNVERIFIED (check Azure/GCP calculators).

### What to show the user (honest labels)
- Pull (local): "Your data never leaves this machine. The pack runs in a sandbox here. The pack author's harness is visible on your machine."
- Sealed Hosted: "Verified at <time>: this pack, build <hash>, runs in an AWS Nitro enclave. The machine's operator cannot read your data. Still visible to: the pack code itself, Nebius (zero retention requested), AWS as hardware root of trust. Not protected against: physical attacks on the host, hardware side channels, a compromised AWS or vendor root."
- Hosted (unsealed): "The machine's owner can read everything you send. Use only for non-sensitive tasks."
- Never write "nobody can see your data" or "the host is blind". Never show a "sealed" badge from a self-attested log.

## Recommendation

1. Keep Pull as the default and as the answer for private data. Its guarantee rests on local sandbox and egress deny (software) rather than vendor hardware and physical security.
2. Add Sealed Hosted as a clearly separate tier, Nitro first (documented attestation, KMS gating, no extra fee, AWS Builder fit), designed behind an interface so a dstack or CoCo GPU CVM backend can be added later for local Nemotron.
3. Treat TEE as defence against the operator only; keep egress allowlist, no-search-after-data, result guard and active defense inside the enclave.
4. Require reproducible builds and a published measurement per pack version, and revocation by measurement.
5. Do not run sealed hosting on an owner's home hardware and call it sealed; require a cloud host with physical security.
6. Ask Nebius staff whether any CC-capable GPU offering exists; if so evaluate it as backend B.

## Risks

- Overclaiming: "secure/private" is false if the pack code is malicious; the TEE sees it all.
- Physical-attack class (TEE.fail) out of vendor scope; attestation keys can be forged on TDX/SNP and GPU attestation borrowed.
- Nitro trust = AWS; no GPU, so inference leaves the enclave to Nebius.
- Metadata leakage to the host: destination, timing, sizes, task frequency.
- Reproducible-build effort: a measurement is only meaningful if users can rebuild it; otherwise the badge is theatre.
- Nebius ZDR availability on hackathon accounts UNVERIFIED; GPU CVM availability, quotas, spot-only on GCP, cost UNVERIFIED.
- Dev effort and key-management complexity (key broker, rotation, revocation) are easy to underestimate.
- Hackathon rules for the required Nebius model location (inference on Nebius vs elsewhere) UNVERIFIED.

## Open questions

- Does Nebius offer confidential GPU VMs or attestation for Token Factory? What do the rules require for "NVIDIA model via Nebius"?
- Can an enclave get a GPU on any AWS path (not documented)? Check AWS docs/roadmap directly.
- Who runs sealed hosts: the owner in their own cloud account, or a marketplace-operated pool (cleaner trust story, adds ops and cost)?
- Is owner IP protection (sealed harness) a required property or a bonus?
- Where is the attestation verifier and revocation list hosted so the hub itself is not the single trusted party (transparency log like Apple PCC)?
- Exact on-demand and spot prices for Nitro-capable, Azure NCCadsH100v5 and GCP A3 High instances.
