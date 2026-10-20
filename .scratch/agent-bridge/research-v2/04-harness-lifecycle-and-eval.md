# 04 - Harness lifecycle, evaluation, improvement, verifiable leaderboard

Date: 2026-10-07. Round 2. Scope: how a pack (agent + harness) is developed, evaluated, improved, versioned, signed, published, ranked. Sources are primary (papers, official docs, repo READMEs) unless marked SECONDARY. Anything not read from a source is UNVERIFIED.

## Summary

- A pack should be treated like a software release with an eval suite: `pack.yaml` manifest + prompt/tools/MCP config + eval suite + memory schema, versioned by semver, content-addressed (digest), signed (Sigstore/cosign style), and accompanied by signed eval and provenance attestations (in-toto/SLSA style).
- Improvement loop: eval-driven development (Anthropic guidance) with an optional automated optimizer (GEPA / DSPy / Meta-Harness style) that proposes new pack versions; every candidate is gated by regression evals on a private held-out set before it can be published. Self-modifying (DGM style) search is allowed only inside a sandbox and only produces candidates, never auto-publishes.
- The key lesson for a leaderboard: public agent benchmarks are gameable. UC Berkeley RDI broke 8 major agent benchmarks (SWE-bench Verified, Terminal-Bench, GAIA, WebArena, etc.) to near-perfect scores without solving tasks. So the ranking must NOT trust owner-reported or owner-hosted scores. Evals run in a marketplace-controlled grader isolated from the pack, with private rotating tasks, and the primary ranking signal is verified paid completions (escrow capture bound to requester acceptance), combined with eval results via a statistical model with confidence intervals.
- Hackathon fit: GEPA/DSPy and NeMo Evaluator (Apache-2.0) are real, usable; Nemotron via Nebius can be both the pack's model and the optimizer's reflection/judge model. A small live "improve this pack" demo (before/after eval score, new signed version) is a strong harness+agent story.

## Key facts with sources

### Eval-driven development and agent evals
- Anthropic: workflows (predefined code paths) vs agents (LLM directs itself); start simple, add complexity only when it demonstrably improves outcomes; invest in the agent-computer interface (tool docs, poka-yoke). https://www.anthropic.com/engineering/building-effective-agents
- Anthropic "Demystifying evals for AI agents" (2026-01-09): vocabulary of task, grader, transcript; three grader types (code: fast/objective/brittle; model: flexible but needs calibration; human: gold standard but slow); pass@k (at least one success in k) vs pass^k (all k succeed) for non-determinism; capability evals start at low pass rate, regression evals should stay near 100%; read transcripts; prefer grading outputs over exact paths; watch saturation. https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- tau-bench: simulated user + domain tools + policy; compares final database state to goal state; introduces pass^k reliability metric; gpt-4o succeeded on under 50% of tasks and pass^8 under 25% in retail. https://arxiv.org/abs/2406.12045
- SWE-bench: 2,294 real GitHub issues from 12 Python repos; model must edit a codebase to resolve the issue. https://arxiv.org/abs/2310.06770
- GAIA: 466 questions, answers withheld for 300 to power a leaderboard; humans 92% vs GPT-4 with plugins 15% (at publication). https://arxiv.org/abs/2311.12983
- Terminal-Bench: terminal agent benchmark with leaderboard of resolution rate with 95% CIs plus cost/tokens; maintained by Stanford, Harbor Framework, Laude Institute; carries canary GUID notice against training-corpus inclusion. https://www.tbench.ai/
- NeMo Evaluator (NVIDIA): open source, Apache-2.0, containerized, pluggable scoring; includes agent solvers (HarborSolver, ToolCallingSolver) and Docker sandboxes. https://github.com/NVIDIA-NeMo/Evaluator (usable as eval runner; fit for the NVIDIA angle, but depth of agent support not verified beyond the README summary, so spike it).

### Benchmark gaming (critical for the leaderboard)
- Berkeley RDI, "How We Broke Top AI Agent Benchmarks" (Apr 2026): an automated agent got near-perfect scores on 8 benchmarks without solving tasks. Examples: 10-line `conftest.py` resolves every SWE-bench Verified instance; fake `curl` wrapper gets all 89 Terminal-Bench tasks; `file://` navigation reads gold answers in WebArena. Seven root causes: shared agent/evaluator environment, exposed answers, `eval()` on agent strings, undefended LLM judges (prompt injection), weak matching, incomplete scoring, trusting outputs produced inside the compromised environment. Defences: isolate evaluator from agent, never ship reference answers with tasks, safe parsing, sanitize/delimit agent content in judge prompts, adversarially test the benchmark, read-only FS, private ground truth with rotating instances. "Don't trust the number. Trust the methodology." https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/
- SECONDARY (not primary, treat as context only): reports of METR finding reward hacking in about 30% of o3 runs (e.g. https://lilting.ch/en/articles/berkeley-rdi-ai-agent-benchmark-exploitation). UNVERIFIED against METR primary.

### Automatic harness / prompt optimization
- DSPy: declarative LM programs compiled by optimizers against a metric; MIT license; repo lists MIPROv2, GEPA, BootstrapFewShot. https://arxiv.org/abs/2310.03714 , https://github.com/stanfordnlp/dspy
- GEPA (ICLR 2026 oral): reflective prompt evolution using trajectories + natural-language reflection + Pareto frontier selection; reports +6% avg (up to +20%) over GRPO with 35x fewer rollouts and >10% over MIPROv2. https://arxiv.org/abs/2507.19457 (numbers are the authors' claims).
- TextGrad: backpropagates textual LLM feedback through a compound system; e.g. GPQA 51% to 55%, LeetCode-Hard +20% relative. https://arxiv.org/abs/2406.07496
- Meta-Harness (arXiv 2603.28052, Stanford/MIT): outer-loop search over harness CODE; an agentic proposer reads source, scores and execution traces of all prior candidates through a filesystem; +7.7 points on text classification with 4x fewer context tokens; +4.7 on IMO-level math across 5 held-out models; beats hand-engineered baselines on TerminalBench-2. https://arxiv.org/abs/2603.28052 . Note: it also optimizes what is stored/retrieved/presented, i.e. context memory, which links directly to the memory design topic.
- Darwin Godel Machine: self-modifying coding agent with empirical validation; SWE-bench 20.0% to 50.0%, Polyglot 14.2% to 30.7%; experiments run with sandboxing and human oversight. https://arxiv.org/abs/2505.22954 . Caveat: validating on a benchmark invites objective hacking (see Berkeley), so improvements must be validated on private held-out tasks.

### Versioning, signing, provenance, ranking math
- SemVer 2.0.0: MAJOR = incompatible API change, MINOR = backward-compatible feature, PATCH = backward-compatible fix; released versions immutable; pre-release and build metadata supported. https://semver.org/
- Sigstore/cosign: keyless signing; Fulcio issues short-lived cert binding an ephemeral key to an OIDC identity; Rekor transparency log records the signing event; roots distributed via TUF. https://docs.sigstore.dev/cosign/signing/overview/ . Rekor: append-only log with inclusion proofs; v1 in maintenance, v2 (tiles) in development; public instance limits attestation size to 100KB. https://github.com/sigstore/rekor
- in-toto attestations: Predicate / Statement (binds subject digest) / Envelope (DSSE) / Bundle. https://github.com/in-toto/attestation/blob/main/spec/README.md
- SLSA provenance v1: records builder identity, external parameters, resolved dependencies, subject digests; builder.id determines trust level. https://slsa.dev/spec/v1.0/provenance
- Chatbot Arena: pairwise comparisons from crowdsourced votes ranked with Bradley-Terry style statistics; 240k+ votes. https://arxiv.org/abs/2403.04132

## Fit for agent-bridge

### A. What a pack is (made precise)
Content-addressed directory (digest over a canonical tar/OCI artifact):
```
pack.yaml          name, semver, speciality, declared capabilities/permissions (tools, net, folders), base model(s), price, mode support (pull/hosted)
prompt/            system prompt, phase prompts (planner/worker/returner)
tools/             tool list + MCP config (pinned versions/digests)
skills/            optional skill files
memory.schema.yaml  what the pack may read/write in context memory (scopes, retention) - see memory topic
evals/             public dev suite + eval harness config (graders); private suite lives in marketplace, NOT in pack
CHANGELOG.md       what changed and which evals moved
```
Version rules (SemVer applied to packs, adapted): MAJOR = permission/capability manifest widened, output schema changed, or model family changed (requires re-approval by requesters); MINOR = new skill/tool within existing permissions or measurable capability gain; PATCH = prompt wording/bugfix with no permission change. Rule: any change that adds a permission is MAJOR and forces a fresh consent. Released versions immutable; "yank" = revoke, never edit. (The permission-widening-is-MAJOR rule is our design, not from SemVer.)

### B. Lifecycle: author -> test -> sign -> publish -> run -> feedback -> improve
1. Author: start from a library harness (mini-swe-agent, deepagents, etc.), write manifest + dev evals. Principle from Anthropic: start with simplest workflow, add agentic complexity only if evals show gain.
2. Test (local, CLI `bridge pack test`): run dev suite with k>=5 trials per task, report pass@1 and pass^k, cost, latency, token use, plus a transcript viewer. Static checks: manifest vs actual tool use, no undeclared network, dependency pins.
3. Certify (marketplace-controlled): pack digest is submitted to the Certifier, which runs it in a fresh sandbox, separate from the grader, against (a) a public suite, (b) a PRIVATE rotating suite, (c) safety suite (prompt injection, exfil attempts, canary-token reads; ties to the active-defense topic), (d) regression suite from previous version. The Certifier, not the owner, produces the eval attestation.
4. Sign: owner signs the pack digest (Sigstore-style OIDC keyless, or a plain Ed25519 key for the hackathon); Certifier signs an eval attestation (in-toto statement: subject = pack digest, predicate = suite id/version, seeds, model IDs, scores with CIs, grader version). Provenance attestation (SLSA-style) records how the pack was built. Entries are appended to a transparency log (Rekor, or our own hash-chained log with inclusion proofs for the hackathon).
5. Publish: listing points to digest; requesters pin a digest or a semver range (PATCH/MINOR auto-update opt-in, MAJOR never auto). Runtime verifies signature + attestation + digest before launching (ties to the existing "manifest/pack hash check" in architecture-options).
6. Run: every paid run records (pack digest, model ID, seed, config, grader-independent outcome) in a signed run record. Reproducibility: pin model ID + temperature/seed where supported, pin tool versions; note LLM outputs are only statistically reproducible, so reproducibility = replayable trace + re-runnable eval, not byte-identical output (UNVERIFIED whether Nebius exposes a seed parameter; spike).
7. Feedback: requester accept/reject/dispute + structured rating, outcome-based checks where possible (tests pass, schema valid), cost, time. With requester consent only, an anonymized and PII-scrubbed failure trace can be offered to the owner; raw task content and context memory are never returned to the owner by default (privacy over improvement; this is a deliberate tradeoff, flagged below).
8. Improve: (a) manual: owner reads transcripts of failures; (b) assisted: optimizer (GEPA/DSPy, Meta-Harness style proposer) runs on the owner's own dev set plus feedback-derived failure cases, in a sandbox, producing a candidate version; (c) all candidates go through step 3 and must not regress the regression suite and must beat the incumbent by a margin with non-overlapping CIs on the PRIVATE suite before publish. Optional A/B: new version receives a small share of traffic with requester opt-in ("canary"); shadow mode: new version runs on the same task in parallel in the Certifier sandbox on synthetic or consented tasks, output discarded, compared offline. Never shadow-run on a requester's real private data without explicit consent, because that would copy context to another run (security rule).
9. Retire/yank: security regression or detected theft attempt -> yank version, revoke signature trust, log.

### C. Verifiable leaderboard resistant to gaming
Threats (from Berkeley RDI): grader tampering, answer leakage, judge prompt injection, overfitting to public tasks, self-reported scores, plus marketplace-specific: wash trading (owner hires own pack), fake reviews/Sybil requesters, selection bias (only easy tasks), version-swapping after good score, price dumping.

Design:
- Score = f(Certified eval score, Verified paid outcomes), each with uncertainty; display as lower confidence bound, not raw mean (cf. Terminal-Bench shows 95% CIs). Pairwise/BT-style rating is an option for head-to-head arena tasks (Chatbot Arena precedent), but needs anti-Sybil weighting.
- Eval integrity: grader runs outside the pack's environment; ground truth held privately and rotated; no `eval()` on agent output; judge prompts delimit/sanitize agent text; graders themselves adversarially tested with a "cheater pack" before use (all Berkeley checklist items). Include canary tasks that a legit solver cannot pass without doing the work (honeypots) and a detector for tampering behaviour (writing to grader paths, monkeypatching test frameworks).
- Per-version scores: ranking attaches to pack digest + version, so a good score cannot be inherited by a later swapped version; MAJOR bump resets the verified-outcome history.
- Verified paid completions: only runs whose escrow was captured after requester acceptance count (receipt-bound, matching the existing "star bound to capture id"). Weight by amount, requester age/diversity, unique payer accounts; exclude owner-related accounts (same device/payment account, same identity cluster), cap the influence of any single requester, require minimum price floor so zero-price self-dealing is useless. Sandbox PayPal in a hackathon means these are demo-only; real anti-wash-trading needs KYC-level signals (UNVERIFIED how much PayPal exposes).
- Dispute signal: refunds/void/disputes count against the version; low-visibility penalty for packs with detected exfil attempts (active-defense events), which are quarantined entirely.
- Transparency: all attestations and run-record hashes in an append-only log; anyone can recompute the leaderboard from the log (verifiable). Honest limit: run records on Hosted mode are owner-attested; only the escrow capture and requester acceptance are third-party facts. In Pull mode the requester machine produces the run record, which is stronger for the requester but still self-attested by that requester.
- Show separate columns, not one blended score: Certified quality (CI), Reliability (pass^k), Verified paid completions, Cost/latency, Safety incidents. Blend only for default sort.

### D. Context memory interaction (light touch; the memory topic is separate)
- Pack manifest declares memory scopes; evals include "memory hygiene" tests (does the pack write secrets into persistent memory, does it leak scope A into B). Meta-Harness shows memory/retrieval policy is itself an optimizable harness component, so memory schema belongs in the versioned pack and must be covered by regression evals.
- Feedback loops write to the OWNER's pack knowledge only via scrubbed, consented artifacts; requester context memory is never an input to training/optimizing a foreign pack by default.

### E. Hackathon framing
- Nebius x NVIDIA: pack runs on Nemotron via Nebius; GEPA reflection and LLM-judge also use a Nemotron model; show "v1.0.0 score 41% -> v1.1.0 score 58% on private suite, CI shown, signed, published". NeMo Evaluator as optional eval runner (UNVERIFIED depth).
- PayPal: leaderboard weighted by captured payments, receipt-bound stars; refund path lowers score.
- Demo-able subset: `bridge pack test`, certifier run, signed attestation verify, tamper scene where a cheater pack that edits grader files gets caught.

## Recommendation

1. Define the pack manifest and digest first; everything else (signing, ranking, permissions) hangs off the digest.
2. Build a Certifier service (separate sandbox from the pack, separate from the grader) as the single source of eval truth; implement the Berkeley checklist as its acceptance tests, including a deliberately malicious "cheater pack".
3. Use DSPy+GEPA (MIT, real) as the default optimizer, with a Meta-Harness-style proposer as stretch; require private held-out gating and CI-aware promotion; no auto-publish.
4. Signing: Ed25519 + own hash-chained transparency log for the hackathon, with a documented upgrade path to Sigstore keyless + Rekor and in-toto/SLSA attestation formats. Do not claim Sigstore usage unless actually integrated.
5. Leaderboard: lower-confidence-bound score, per-version, with verified-paid-completion weighting and anti-wash-trading rules; publish the formula.
6. Metrics: report pass@1 and pass^k, cost, latency; read transcripts as a first-class tool.
7. Shadow/A-B only on synthetic or consented tasks, never on private requester data.

## Risks

- Eval/grader gaming (Berkeley-class exploits) can corrupt the leaderboard; mitigation is Certifier isolation, private rotating tasks, honeypots, but residual risk remains.
- Optimizer overfitting to dev/feedback sets; Goodhart on the private suite if owners can query it repeatedly (limit certification attempts, rotate tasks, add noise/holdout).
- Wash trading and Sybil requesters in a thin marketplace; sandbox payments give no real identity.
- LLM nondeterminism makes "reproducible" claims statistical; model provider drift (Nebius model updates) silently changes scores; mitigation: record model ID, re-certify periodically.
- Privacy vs improvement tension: restricting feedback traces slows improvement; consent-gated scrubbed traces may be too thin.
- Self-attested run records in Hosted mode; certifier and hub become trusted parties (single point of trust).
- Self-improving (DGM-style) loops can introduce unsafe behaviours; sandbox + human approval required.
- Rekor public instance has size limits and v1 is in maintenance mode; reliance on public Sigstore infra adds dependency and complexity.
- Scope: a full Certifier + private suite per speciality is a lot of content to author; need seed suites for 2-3 specialities.

## Open questions

1. Who authors private eval suites per speciality (marketplace, community, requester-contributed)? Conflict of interest if owners write them.
2. Does Nebius Token Factory support seed/determinism and stable model snapshots (UNVERIFIED)?
3. Is Sigstore keyless worth integrating for the hackathon, or is plain Ed25519 + own log enough?
4. How does the verified-paid weighting treat free/low-price packs (open source library packs)?
5. Should the Certifier run on the hub (trusted party) or be reproducible by anyone from the signed attestation (replay)?
6. How much of Pull-mode run data may flow into eval feedback without violating the "nothing sent to a foreign pack" rule (owner as recipient vs the marketplace as recipient)?
7. Does NeMo Evaluator's Harbor/tool-calling solver fit our pack runtime, or do we write a thin custom grader?
8. Exact GEPA/DSPy interface for optimizing a multi-phase (planner/worker/returner) harness: not verified, needs a spike.
