# 10 - Gap fill and completeness critique (round 2)

Date: 2026-10-07. Scope: critique of files 01-09, plus research on gaps. Tags: [SRC] = read from a primary source this session; [DESIGN] = our reasoning/proposal, not sourced; UNVERIFIED = not confirmed.

## Summary

Files 01-09 are consistent on the core architecture (Pull default, broker, quarantine tier, deterministic detectors kill, guard models only escalate). The main problems are: (a) one factual contradiction about Nebius retention that is now resolved in our favour, (b) several optimistic claims (detector kill authority with no false-positive budget, "manifest = request" UX, ranking per-version with thin data), and (c) seven gaps, now filled below with a concrete design position each. Biggest new findings:

1. Nebius Token Factory DOES document Zero Data Retention (ZDR); default behaviour stores prompts/outputs for speculative decoding in Finland; content is "not used to train any models in either mode". File 05 told us not to claim zero retention and file 09 assumed ZDR; the truth is "ZDR is an account-setting opt-in, off by default". Per-key ZDR and spend caps are NOT documented.
2. Nebius documents rate limits (60 RPM / 400k TPM default, per account/API key, auto-scaling up to 20x) but no spend caps and no per-key scopes, so cost control must live in OUR proxy.
3. A canary that is read is NOT a theft signal for an LLM agent that explores the filesystem; only canary egress is. Kill authority should attach to egress/taint, not to canary reads.
4. Harness portability across base models is a measured problem (prompt "model drifting"; harness sensitivity is non-monotone across model tiers). A pack must declare and be certified per model family.
5. Licensing: Claude Code is proprietary and API terms forbid resale of the Services; anthropics/skills docx/pdf/pptx/xlsx are source-available; AGPL-3.0 section 13 triggers on remote network interaction. A marketplace needs license gating in the manifest and at publish time.

## Part A - Claims that look unverified, contradictory or optimistic

| # | Where | Issue | Resolution |
|---|---|---|---|
| A1 | 05 vs 09 | 05: "do NOT claim zero retention; ZDR UNVERIFIED". 09: assumes ZDR with hub-issued per-task keys. | Verified: ZDR exists as an account-profile setting (see B1). But "per-task hub key with ZDR" is UNVERIFIED because ZDR is documented per account, not per key. Design the hub to use ONE dedicated Nebius account with ZDR on, then mint internal virtual keys. |
| A2 | 06 | "Deterministic detectors D1-D12 authorized to kill", canary reads included. | Over-optimistic for agents (B2). Split detectors into KILL (egress match, taint-to-sink, kernel rule, tamper) and PAUSE/ESCALATE (canary read, scope probes, volume). |
| A3 | 06/02 | "Canary detection near-zero false positives" (cites generic honeytoken lore). | True for humans/service accounts, not for an LLM that globs a directory. [DESIGN] reasoning; no data. Needs measurement against honest reference packs before demo. |
| A4 | 03 | "Manifest = request, grant = intersection" is the headline. | Correct as enforcement model, but approval UX is unspecified; Claude Code data shows 93% of permission prompts are approved, i.e. click-through (B6). |
| A5 | 04 | Rank by lower confidence bound of private-suite scores per version. | New versions have no data, and suites per speciality need authors (file 04 admits). Cold start not designed (B7). |
| A6 | 01 | Mem0 LoCoMo 92.5 / LongMemEval 94.4 vendor-reported. | Already flagged. Also: Graphiti license was UNVERIFIED in 01; now verified Apache-2.0 [SRC: gh api repos/getzep/graphiti, SPDX Apache-2.0]. |
| A7 | 06 | NeMo Guardrails licence not stated. | GitHub shows NOASSERTION, but LICENSE.md header is `Apache-2.0` with SPDX tag [SRC: github.com/NVIDIA/NeMo-Guardrails LICENSE.md]. Treat as Apache-2.0, with third-party notices in LICENCES-3rd-party. |
| A8 | 05/07 | Pull-mode "structural guarantee author learns nothing". | Honest wording must be: author gets nothing from the pack's own channels; requester's own sharing, Nebius, and covert result-channel encoding are residual. Files already say this; keep it in the UI copy. |
| A9 | 02/09 | Nemotron safety model "available on Nebius?" | Still UNVERIFIED. Nebius docs list examples of Meta-Llama models only on the pages read; no page for guard models; `llms.txt` index has no guard/ZDR page. Action: call `GET /v1/models` with a real key (cannot be done without credentials in this session). |
| A10 | 08 | Prize category text unreadable (Devpost 503). | Still UNVERIFIED; do not design to unverified rubric. |

## Part B - Gaps, researched

### B1. Nebius data handling and the cost of a pack run (cost control)

Facts [SRC]:
- ZDR: "with ZDR enabled, your inputs (prompts) and outputs (responses) are not stored on our systems after each request is processed". Without ZDR: "may be stored and used for Speculative Decoding", stored in Finland (EU) regardless of where inference runs; "We do not use your content to train, fine-tune or improve any AI models - ours or third parties'." Public endpoints: processing location dynamic. ZDR "may impact the level of service". Source: https://docs.tokenfactory.nebius.com/legal/legal-quick-guide (also https://nebius.com/services/token-factory/enterprise-grade-inference per search snippet).
- The general privacy policy (https://docs.nebius.com/legal/privacy) does NOT mention inference retention; the quick guide is the operative document. Cite both.
- Rate limits: default 60 RPM and 400,000 TPM, applied per account/API key, scale +20% per window when usage >=80%, up to 20x; overage is deprioritised not rejected. No spend limits documented. https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md
- API base https://api.tokenfactory.nebius.com/v1, bearer key (from file 05).

Design implications [DESIGN]:
- Cost control cannot rely on Nebius. Our key-holding supervisor/proxy must enforce: per-task token budget (input+output), max calls, max parallel, wall-clock, and a hard USD ceiling derived from the signed quote. LiteLLM proxy shows the proven shape: virtual keys with `max_budget`, `budget_duration`, `rpm`, `tpm`, `max_parallel_requests`, soft-budget alerts at e.g. 80% (https://docs.litellm.ai/docs/proxy/users). Adopt the pattern (or LiteLLM itself, MIT-licensed per its repo; licence not re-verified here) instead of building from scratch, per the "do not build simple things" decision.
- Because a single Nebius account has 60 RPM default, concurrent demo runs share one pool; the proxy needs a fair-share queue or the demo will 429.
- Pricing model must separate: harness fee (author), inference at pass-through cost (requester pays), compute fee (host, Hosted only). Show the cap before approval; the proxy returns a "budget exhausted" result and the pack must checkpoint, never overrun.
- Hub-side ZDR: turn it on in the account; show the badge "inference provider retention: none requested (ZDR on)" only if actually on. Do not say "no one can see data": Nebius processes it.

### B2. Detection without false positives ruining the demo

Facts [SRC]:
- Claude Code auto mode data: users approve 93% of permission prompts; a two-stage classifier had 8.5% FPR on stage 1 and 0.4% FPR with full pipeline, but 17% FNR on real overeager actions; design is "deny-and-continue" with escalation after 3 consecutive or 20 total denials (https://anthropic.com/engineering/claude-code-auto-mode). Lesson: even a tuned Anthropic classifier misses 17%; a lower FPR costs recall.
- Sandboxing cut permission prompts 84% internally (via search snippets of Anthropic's engineering post; primary page not fetched here: UNVERIFIED wording).
- Honeytoken claim "never accessed by legitimate users" holds for human/service principals; the sources found are generic security articles, not agent studies.

Design [DESIGN]:
1. Kill authority only on evidence that data LEFT or is about to leave: (a) egress payload matches canary value or vault content (normalised, n-gram/hash overlap), (b) taint-to-sink violation by broker, (c) sandbox boundary violation (blocked syscall/escape attempt), (d) pack digest drift / tamper. These have a near-zero honest-pack rate because honest packs have no network and no business emitting canary strings.
2. Canary READ, scope probes, volume anomalies = deny-and-continue, then PAUSE and ask the requester on repeat, with a per-run strike budget (mirrors Anthropic's 3 consecutive / 20 total). Honest explorer agents trip these; killing here would fail demos and tank ratings.
3. Make canaries LOW-attractiveness for honest tasks: place them only in paths outside the granted lens root and in memory records tagged out-of-lens, so an honest pack that stays in the lens never sees them. A broad `grep -r` over the granted folder should not hit a canary at all; a canary hit then means "left the lens", a stronger signal.
4. Slashing, escrow void and publisher ban only after a second independent detector or human confirmation (already in file 06); add an appeal path and a "false-positive ledger" for honest authors.
5. Required test set before demo: run 5-10 honest reference packs (different harnesses) through 50+ varied tasks and report FP rate; run the malicious reference pack and MINJA/MEXTRA-style attacks and report detection rate and time-to-kill. Publish both numbers on the slide. No FPR data exists yet (carried risk from file 01).
6. Fail-safe behaviour on kill: return partial result + reason, auto-void only the unaccepted portion, never delete requester data.

### B3. Memory in Pull mode (how the four planes meet a foreign pack)

No new primary source needed; this reconciles files 01, 02, 03 [DESIGN] with sources already cited there (MCP resources/roots advisory; Anthropic memory tool is client-side with path-traversal protection; AgentPoison/MINJA/MEXTRA).
- The pack never gets a memory backend. It gets (i) a read-only staged snapshot at `/in` containing only lens-selected items, and (ii) a `memory.search` tool exposed by the broker sidecar over the unix socket, with k and byte budgets and provenance labels. No `read_graph`/dump tool.
- Pack-side memory (plane H, harness procedural memory) ships inside the pack, read-only at run time. In Pull mode there is NO writable persistent store for the pack; per-run scratch is tmpfs and destroyed. This makes "pack memorises requester data" impossible by construction rather than by policy.
- Pack proposes memory writes as structured items to the broker; they land in "proposed", with source=pack/<digest>, trust=low. They cannot influence the pack's own next-run context unless the requester promotes them. This stops the pack from using the vault as a covert channel to its next run, and blocks MINJA-style persistence.
- Relationship memory (plane P) is requester-side and hashed by pack digest, so a new version is a new relationship until the requester carries trust over. Prevents silent trust inheritance after an update (relevant to the supply chain risk in file 03).
- Deletion: crypto-shred per-task keys at task end (file 02) so the staged snapshot cannot be recovered from the VM disk. Verify on WSL2 that scratch is tmpfs, not ext4.
- Lens definition recommendation (answers open Q in 01): user-chosen tags AND a query-time budgeted filter; lens is the intersection, never the union. Enforcement at the mount and the broker, not in the prompt.

### B4. Cross-base-model portability of a pack

Facts [SRC]:
- PromptBridge: prompts are model-sensitive; reuse across models "often yielding substantially worse performance" ("Model Drifting"); transfer method reported +27.39% on SWE-Bench and +39.44% on Terminal-Bench relative to direct transfer on o3 (search-result summary of arXiv 2512.01420; numbers not verified against the paper body). https://arxiv.org/html/2512.01420v1
- "It's Not the Capability: Harness Sensitivity Is Non-Monotone Across LLM Agent Tiers" (arXiv 2605.26731): 432 runs; verbose harness detail cut Gemini 2.5 Flash success by 29-38 points while Qwen3.5-122B with extended thinking peaked at 91.7% under strict harness. Abstract-level only. https://arxiv.org/abs/2605.26731
- Hackathon requires an NVIDIA open model via Nebius, so the effective base model for the demo is fixed; the open question is only for the real product.

Design [DESIGN]:
- Manifest `model.tested_on` must be a list of (model id, eval digest, score CI), and a pack is only listed as "works on X" for models with a Certifier-run result. Ranking is per (pack version, model family), with a "works-on matrix" (already an open question in 03; this settles it: per model, because the sources show harness effects are model-dependent).
- Model-specific parts live in overlay files (`models/<family>/prompt.md`, tool-format adapter), not forked packs. A requester asking for an untested model gets a "not certified" warning and a lower default budget.
- Run a cheap portability probe at install: run the pack's smoke eval on the requester's configured model; fail closed if below threshold.
- Hackathon demo: pin ONE Nemotron model id and show the improvement loop on it; mention portability as a roadmap with the sources above.

### B5. Protecting harness author IP

Facts [SRC]:
- System prompt extraction is widely successful; defenses reduce extraction by 83.8% (Llama2-7B) and 71.0% (GPT-3.5) but do not eliminate it (arXiv 2408.02416 search summary; also 2404.16251, 2505.23817). Prompt secrecy by obfuscation is not achievable; file 05 reaches the same conclusion.
- ClawHub incident: 341 malicious skills found, 335 from one campaign (ClawHavoc), disguised as popular tools (The Hacker News, Feb 2026: https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html). Shows both that open skill registries are attacked and that publish-time vetting is mandatory.

Design [DESIGN], tiered honest options:
1. Open pack: IP = brand, updates, evals, curation. Cheapest, matches Pull.
2. Licensed pack: signed manifest with license terms, per-licensee watermark (unique canary phrases/whitespace/tool-name salts in prompt and skill files, one per requester license) so leaks are attributable. Deterrent and evidence only, not prevention.
3. Split pack: public Pull-eligible shell (tools, formats, light prompts) plus Hosted-only "brain" (planner prompt, private skills, fine-tuned weights). Requester data flows to the brain only as a minimal task package in Hosted mode (file 02 packet). Honest: this is Hosted semantics for the brain part.
4. Sealed Hosted (TEE) protects the owner from the host only if the owner is not the host; protecting the owner from the requester is a different property (mutual confidentiality), still an open question from 09.
Also state clearly that Hosted mode protects owner IP from requester but sends requester data to the host (owner).
- Do not use manifest-level "obfuscated prompt" as a feature.

### B6. UX of approving a pack (without click-through)

Facts [SRC]: 93% approval rate of Claude Code prompts (approval fatigue); Anthropic's answer is to shrink the prompt surface with real containment plus a classifier for the residue (same source as B2).

Design [DESIGN]:
- Approve ONCE at install/hire time per (pack digest, mode, lens, budget), not per action. Containment replaces per-action prompts (the 84% prompt-reduction logic).
- The approval card has fixed fields in a fixed order: who (publisher, verified?), what version/digest + change summary vs previous, mode and driver tier badge, data granted (lens, byte-exact preview of what the pack can read), network (none, or listed), cost cap, time cap, writes (output folder only), certified-on model, last Certifier score with CI, incidents count.
- Diff-only re-approval on update: new digest widening any permission is a MAJOR change and re-prompts; otherwise silent with a notification.
- Mandatory human gates only where irreversible or durable: widening lens, promoting proposed memory (profile/procedural/secret), payment capture. Everything else deny-and-continue.
- Show approval strength honestly: tier-0 (no code) vs tier-1 (code) pack, driver tier (container in VM vs microVM) from file 07.
- Demo flow: approval card on the phone/desktop, then the attack theater (malicious pack kill, quarantine, void), which makes the default-safe story visible without more prompts.

### B7. Licensing and legal redistribution of third-party harnesses

Facts [SRC] (gh api, licences as of 2026-10-07):
- MIT: openclaw/openclaw, SWE-agent/mini-swe-agent, All-Hands-AI/OpenHands (repo-level SPDX; any enterprise subfolder terms not checked), langchain-ai/deepagents, HarnessMD/munder-difflin.
- Apache-2.0: block/goose, Aider-AI/aider, PersonalJarvis/PersonalJarvis, getzep/graphiti, mem0ai/mem0, NVIDIA/NeMo-Guardrails (via LICENSE.md header).
- anthropics/claude-code: no SPDX; LICENSE.md: "All rights reserved. Use is subject to Anthropic's Commercial Terms of Service" (https://github.com/anthropics/claude-code). So it cannot be bundled or redistributed in a pack; a pack can only declare it as a requester-installed runtime.
- Anthropic Commercial Terms: customer may not "access the Services to build a competing product or service ... or resell the Services except as expressly approved by Anthropic"; own products powered by the API are allowed (https://www.anthropic.com/legal/commercial-terms). So a marketplace must never resell a user's Claude subscription/API access to other requesters; each requester brings their own key. Hackathon path uses Nebius, which avoids this, but Nebius's own terms for reselling inference were not read (UNVERIFIED).
- anthropics/skills: "Many skills ... Apache 2.0"; docx/pdf/pptx/xlsx are "source-available, not open source" (https://github.com/anthropics/skills). Not redistributable inside packs.
- AGPL-3.0 s.13: if you modify the Program, your modified version must offer all users interacting with it remotely over a network the Corresponding Source (https://www.gnu.org/licenses/agpl-3.0.txt). Consequence for Hosted mode: a host running a modified AGPL harness for requesters triggers source offer to those requesters. GPL-family code in a Pull pack distributed to requesters needs source/notice compliance. I did not verify any candidate harness is AGPL; this is a rule for the license gate.
- NVIDIA Nemotron Open Model License: commercial use allowed, may redistribute and create derivatives; must give recipients the licence, keep notices, include "Licensed by NVIDIA Corporation under the NVIDIA Nemotron Model License", NOTICE file for derivatives; licence terminates if you sue alleging the model or its output infringes; indemnity clause (section 7); no explicit prohibition on hosting as a service (per fetch summary; the full text and the Trustworthy AI terms were not read in full: UNVERIFIED for guardrail-bypass termination detail). https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-nemotron-open-model-license . Applies if we redistribute weights or fine-tunes; calling via Nebius API mostly does not redistribute.

Design [DESIGN]:
- Manifest `upstream[]` entries carry SPDX, source, pinned SHA; publish-time license gate with allow list (MIT, Apache-2.0, BSD, ISC, MPL as file-level), warn list (LGPL, GPL), block list (AGPL for Hosted unless source offer is wired, proprietary, source-available, unknown), and a mandatory `NOTICE`/third-party file generated by the CLI.
- Packs contain references (git URL + SHA) rather than vendored copies wherever possible; the requester's runtime fetches under the upstream licence. This sidesteps redistribution but keeps supply-chain pinning.
- Author attests rights to publish (content licence) at upload; platform ToS with takedown process. Not legal advice; get counsel before production. UNVERIFIED: any legal opinion specific to marketplace redistribution.

### B8. Ranking cold start and wash trading (supplement to A5)
[DESIGN] No new sources. New versions inherit a prior from their parent lineage (same publisher, diff size, security-suite pass) shrunk toward the speciality mean; show "new" badge with wide CI instead of a score. Separate verified-run columns for Pull (receipt token + requester acceptance, host unattested) and Hosted (host-attested), as file 08/04 already indicate.

## Key facts with sources (new this file)

- Nebius ZDR and default speculative-decoding retention in Finland: https://docs.tokenfactory.nebius.com/legal/legal-quick-guide
- Nebius rate limits and no documented spend caps: https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md
- Nebius general privacy policy lacks inference retention text: https://docs.nebius.com/legal/privacy
- LiteLLM per-key budgets/limits: https://docs.litellm.ai/docs/proxy/users
- Claude Code auto mode: 93% approvals, 8.5%/0.4% FPR, 17% FNR: https://anthropic.com/engineering/claude-code-auto-mode
- Anthropic Commercial Terms resale restriction: https://www.anthropic.com/legal/commercial-terms
- Claude Code proprietary licence line: https://github.com/anthropics/claude-code
- anthropics/skills split licensing: https://github.com/anthropics/skills
- AGPL s.13: https://www.gnu.org/licenses/agpl-3.0.txt
- Nemotron Open Model License: https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-nemotron-open-model-license
- Harness sensitivity: https://arxiv.org/abs/2605.26731 ; PromptBridge: https://arxiv.org/html/2512.01420v1
- ClawHub malicious skills: https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html
- Prompt extraction: https://arxiv.org/pdf/2408.02416 ; Whisper Leak: https://arxiv.org/abs/2601.21233 (search-result level)
- Repo licences: gh api repos/<owner>/<repo> (see B7).

## Fit for agent-bridge

All findings tighten rather than change the architecture: the broker/proxy is already the choke point, so it also becomes the cost governor, the memory gateway, and the kill switch. The license gate and per-model certification slot into the existing publish pipeline (file 03/04).

## Recommendation

1. Edit round-2 wording: "ZDR is available on Nebius as an account setting (off by default); we enable it for the hub account and display it only when active."
2. Restrict automatic KILL to egress/taint/boundary/tamper evidence; canary reads and probes are deny-and-continue with a strike budget; measure FPR on honest reference packs before the demo.
3. Implement cost governance in the key-holding proxy (per-task budgets, rpm/tpm/parallel, hard USD cap, fair-share queue); reuse the LiteLLM pattern.
4. Pull-mode packs get no writable persistent store; memory via broker lens only; proposed-writes tier; relationship memory keyed by digest.
5. Rank and certify per (version, model); store model overlays, not forks; pin one Nemotron model for the demo.
6. IP tiers: open, licensed + watermark, split shell/brain, Hosted-only; never promise prompt secrecy in Pull.
7. Single approval card per (digest, mode, lens, budget), diff-based re-approval, human gates only on irreversible/durable actions.
8. License gate in `bridge pack validate`/publish; never bundle Claude Code or non-redistributable skills; never resell a user's Anthropic access.

## Risks

- No empirical FPR/recall data for our detectors; Anthropic's own classifier shows 17% FNR even at low FPR.
- Nebius ZDR per-key semantics, guard-model catalogue and spend caps remain undocumented in what I read.
- Several sources were read at search-summary level (arXiv 2512.01420, 2408.02416, Anthropic sandboxing 84% figure); numbers may differ in the papers.
- Licence analysis is not legal advice; the Nemotron licence's Trustworthy AI terms were not read in full.
- Watermarks and licences deter but do not prevent copying.
- Per-model certification multiplies Certifier cost.

## Open questions

- Is ZDR per account only, and does Nebius allow multiple accounts/sub-keys under one ZDR account? Check account settings and `GET /v1/models?verbose=true` with a real key.
- Does Nebius ToS permit passing inference through to third parties inside a marketplace (resale/aggregation clause)? Not read.
- What is the demo's honest-pack FP target (e.g. 0 kills in 50 runs) and who writes the 5-10 reference packs?
- Do we gate AGPL packs entirely or support source-offer for Hosted?
- Who owns copyright/licence of pack improvements produced by an automated optimizer on top of an upstream licensed pack (DSPy/GEPA outputs)? UNVERIFIED, needs counsel.
- Which approval surface (desktop, web, phone) is the primary one in the demo, and can it show the byte-exact context preview within seconds?
