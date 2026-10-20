# Nebius x NVIDIA Global AI Hackathon: research for agent-bridge

Researched 2026-10-07. Deadline: 30 Oct 2026, 10:00 am PT (23 days left).

CAVEAT: the official Devpost pages (https://nebiusglobalaihackathon.devpost.com/ and /rules) returned a "planned maintenance" 503 (curl, WebFetch and a real Chrome tab). Hackathon rules below come from a third-party blog that quotes the rules ("checked on 3 October 2026"). Treat them as UNVERIFIED against Devpost and re-check the Devpost page before submitting. Model/API facts are from official Nebius docs and NVIDIA model cards.

## Summary
- Hard requirement: project must run on Nebius Token Factory or Nebius AI Cloud AND use at least one NVIDIA open-source model. Our runtime (Nemotron via Token Factory, OpenAI-compatible) satisfies this.
- Best fit track: "Best Apps and Agents" (Nemotron via Token Factory); "Personal AI" is a plausible alternative (private assistant, memory, skills, user-controlled tools). Marketplace + isolation sandbox also touches "Coding and Agentic Engineering" (Token Factory Sandboxes), which is Beta and needs an access request.
- Judging: 4 equally weighted criteria (Technological Implementation, Design, Potential Impact, Quality of the Idea). Demo video under 3 minutes, public repo with open-source license, working demo URL.
- Nebius docs confirm OpenAI-compatible function calling and `tool_choice` (auto or forced function). Per-model price and context could not be read from primary pages (catalog is JS or key-gated); see Open questions.
- Recommended default model: `nvidia/nemotron-3-super-120b-a12b` for the agent loop (needs a smoke test), with `nvidia/Nemotron-3_5-Lightning` or Nano-30B-A3B as fast/cheap fallback.

## Key facts (with sources)

### Hackathon (UNVERIFIED vs Devpost; source is secondary)
Source: https://lucaberton.com/blog/aaif-builders-brews-amsterdam-nebius-nvidia-hackathon-2026/ (quotes official rules, "checked on 3 October 2026"). Cross-check: https://internshala.com/competitions/?p=11205 (period 26 Aug to 30 Oct 2026).
- Submission period: 26 Aug 2026 9:00 am PT to 30 Oct 2026 10:00 am PT. Judging period 1-15 Dec 2026 (search snippet from startupgrantsindia, not fetched).
- Core: must "run on either Nebius Token Factory or Nebius AI Cloud" and use "at least one NVIDIA open source model".
- Submit: (1) working demo or test-build URL (Physical AI track exempt), (2) public repo on GitHub/GitLab/Bitbucket with an open-source license file (Apache 2.0, MIT, MPL 2.0) and README with setup instructions, (3) demo video under 3 minutes.
- Judging: four equally weighted criteria: Technological Implementation, Design, Potential Impact, Quality of the Idea.
- Tracks (4): Coding and Agentic Engineering (agents that write/run/test code in Token Factory Sandboxes); Best Apps and Agents (apps/agents powered by Nemotron through Token Factory); Personal AI (private always-on assistant with memory, reusable skills, user-controlled tools); Physical AI.
- Prizes: $50,000+ total; Grand, 2nd, 3rd; 4 track winners (also NVIDIA Jetson Orin Nano kit); Best Use of Tavily ($3,000); City winners x20 ($500 each); Most Valuable Feedback x10 ($100 plus NVIDIA swag).
- City tour: 20 cities 9 Sep to 13 Oct; last stops San Francisco 9 Oct, Los Angeles 13 Oct (SF has passed as of 2026-10-07; LA on 13 Oct is still ahead). Whether City Winner requires physical attendance is unclear (see Open questions).
- Builder Program: $25 Token Factory credit, $25 Tavily credit, $1 Nebius certification. Tavily free tier: 1,000 credits/month (per same blog).
- Org-side: Nebius announced an agreement to acquire Tavily in Feb 2026 (per blog; UNVERIFIED), so Tavily use is on-brand for Nebius judges.
- Separate Berlin event (18 Oct 2026, onsite, approval-based) with a dedicated NVIDIA Nemotron challenge: https://nebius.com/events/nebius-nvidia-ai-builders-hackathon. Not the same as the online submission.

### Nebius Token Factory API (official docs)
- Base URL `https://api.tokenfactory.nebius.com/v1/`, `NEBIUS_API_KEY`, OpenAI-compatible. Source: https://docs.tokenfactory.nebius.com/ (index: https://docs.tokenfactory.nebius.com/llms.txt).
- Function calling: model outputs OpenAI-format tool calls; you execute them and feed results back. `tool_choice` supports `"auto"` (default) and forcing a named function. Source: https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling.md. Docs example uses Llama; the page does not list which models support tools (per-model flag is in the catalog UI). Structured output/JSON also exists: https://docs.tokenfactory.nebius.com/ai-models-inference/json.md.
- Rate limits: dynamic. Example baseline in docs 60 RPM / 400,000 TPM; +20% when 15-min average usage >= 80%, /1.5 when <= 50%; hard ceiling 20x base; 429 on exceed; headers `x-ratelimit-*`; Batch API has higher limits; over-limit requests may still run at low priority. Actual per-model limits: Token Factory console (https://tokenfactory.nebius.com/project/rate-limits) or `GET /v1/models?verbose=true` (`pricing`, `context_length`, `per_request_limits` fields). Source: https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md and https://docs.tokenfactory.nebius.com/api-reference/examples/list-of-models.md. Both need an API key, not available to me: UNVERIFIED for Nemotron.
- Flavors: append `-fast` to model name for lower latency (higher price). Source: overview.md under ai-models-inference.
- Zero-retention inference, EU and US regions (per blog slides; also Nebius launch page https://nebius.com/newsroom/nebius-launches-nebius-token-factory-to-deliver-production-ai-inference-at-scale).
- Sandboxes (Beta, access request): VM-level isolation, git-like branching/rollback, OCI images, Python SDK, MCP tools (run, rsync, read_file, grep...), LangChain and mini-swe-agent integrations. Source: https://docs.tokenfactory.nebius.com/sandboxes/overview.md.

### Models
- Deprecation notice (official): on 31 Aug 2026 serverless removed `nvidia/Cosmos3-Super-Reasoner`, `nvidia/Nemotron-3-Nano-Omni`, `nvidia/Llama-3_1-Nemotron-Ultra-253B-v1` (replacements: MiniMax-M3, `nvidia/Nemotron-3_5-Lightning`, `nvidia/nemotron-3-super-120b-a12b`). Llama-3.3-70B, Hermes-4-70B and Qwen3-32B also deprecated in favor of `nvidia/Nemotron-3_5-Lightning`. Source: https://docs.tokenfactory.nebius.com/august-2026-deprecation-notice.md. This CONFLICTS with HACKATHONS.md "Verified facts" (written 2026-10-03), which lists Cosmos3-Super-Reasoner and Nemotron-3-Nano-Omni as in the catalog. Re-check with `GET /v1/models` before relying on them (the notice may be a dated plan that was later extended, or they remain on dedicated endpoints only).
- Nemotron-3-Nano-30B-A3B: reasoning on/off toggle in chat template; trained with multi-step tool use RL; recommended vLLM `--tool-call-parser qwen3_coder`; up to 1M context in NVIDIA's own serving (256k default). Source: https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16. NVIDIA's numbers are not Nebius's served limits.
- Nemotron-3-Super-120B-A12B: "up to 1M tokens" context per model card; agentic design. Source: https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16. Nebius-served context UNVERIFIED (a third-party price tracker, not primary, showed 256k for Super and 32k for Nano; do not rely on it).
- Nemotron-3_5-Lightning, Nemotron-3-Ultra-550b: named in Nebius docs/HACKATHONS.md; no primary specs read: UNVERIFIED.
- Cosmos / Nemotron-Nano-V2 VL: vision models, irrelevant to agent-bridge (no screen/vision); skip.
- Price per 1M tokens for any Nemotron on Nebius: UNVERIFIED (pricing page is JS-rendered: https://nebius.com/token-factory/prices).

## Fit for agent-bridge
- Natural fit for "Best Apps and Agents": delegated long multi-step agent tasks run by Nemotron with tool calls on the owner's machine. Also a legitimate "Personal AI" angle (user-controlled tools, local data).
- "Run on Token Factory": our runtime on each machine calls Token Factory. Optional: host the relay/registry on Nebius AI Cloud or serverless to strengthen "runs on Nebius" and also satisfy AWS Builder? Conflict: AWS Builder wants AWS hosting. Pick one per submission (Nebius submission can host nothing but call Token Factory).
- Tavily as the agent's web-search tool: functional runtime call earns Best Use of Tavily ($3,000) and is already planned.
- Open-source license required here and also matches Amazon Open Source mini challenge: MIT or Apache-2.0 from day 1.
- Security and isolation story = Potential Impact + Technological Implementation. Sandboxes (VM-level isolation) is a Nebius-native option to run the untrusted third-party harness; Beta, apply for access now. Fallback: local container/gVisor/Firecracker is more work; Nebius Sandboxes would also hit the "Coding and Agentic Engineering" track.
- Tool-calling reliability of Nemotron under long loops is the main technical risk; must be tested early.

## Checklist: what B must show to score high
Required (disqualifying if missing; verify against Devpost rules page when it is back up):
1. Runs on Nebius Token Factory (or AI Cloud) and uses an NVIDIA open model (name it explicitly in README, video and form: e.g. `nvidia/nemotron-3-super-120b-a12b`). Show real API calls in the demo (a visible model-id/usage panel).
2. Public repo (GitHub) with LICENSE (MIT/Apache-2.0/MPL-2.0) and README with setup steps that a judge can follow in minutes.
3. Working demo URL or test build (hosted marketplace web UI plus a downloadable agent). Provide test credentials/instructions for judges.
4. Demo video under 3 minutes (hard cap), showing the end-to-end flow.
5. Chosen track named in the submission (Best Apps and Agents primary).
6. Built/updated within 26 Aug to 30 Oct 2026 (new project or significantly updated; read full legal text).

Scoring boosters (map to the four equal criteria):
- Technological Implementation: multi-step tool-calling loop with Nemotron (not a single call); error handling and retries on 429 (honor `Retry-After`); structured outputs; isolation architecture diagram; an eval or log of long chains finishing; cite measured tokens/latency/cost per task.
- Design: polished marketplace UI (listings, stars, leaderboard), observability view of machine-to-machine traffic, clean phone approval page.
- Potential Impact: clear problem statement (no harness is best at everything), real two-machine demo, privacy proof (raw file never leaves owner machine; show requester-side network capture or log), pricing/payment story.
- Quality of the Idea: marketplace of agent+harness with isolation guarantees is novel; state the threat model table.
- Side prizes: Tavily search as a real tool (Best Use of Tavily $3K); fill the feedback section thoroughly (Most Valuable Feedback $100 + swag, x10); ask organizers about City Winner eligibility.
- Optional: Nebius Certified Agentic AI Builder cert ($1) and credits (promo NEBIUS-DEVPOST-GLOBAL26 per HACKATHONS.md, UNVERIFIED here).

## Recommendation
1. This week: `GET /v1/models?verbose=true` with the owner's key; record context_length, pricing, per_request_limits for the four Nemotron IDs; confirm which ones are still on serverless post-31 Aug.
2. Build a 50-line smoke test: 10-step tool-calling loop (read_file, python, tavily_search) against Super-120B, Lightning and Nano-30B, measure tool-call validity, latency, and cost. Pick the default by results; keep the model id configurable. Disable/enable reasoning per the model's chat-template flag if exposed.
3. Request Sandboxes Beta access now (https://tokenfactory.nebius.com/sandboxes/about); decide by ~15 Oct whether to use it for isolating the third-party harness.
4. Submit under Best Apps and Agents; license MIT/Apache-2.0 from first commit; use the same repo for Amazon Open Source challenge.
5. Re-fetch the Devpost rules page as soon as maintenance ends and diff against this checklist.
6. Record the <3 minute video from a scripted run; keep a longer cut for other hackathons.

## Risks
- Devpost rules unverified (primary source down); criteria weights and required items may differ slightly.
- Nemotron model availability changes (deprecation notice vs HACKATHONS.md list conflict).
- Nemotron tool-call format/parsing quirks and reasoning traces may break loops (vLLM uses the qwen3_coder parser for them); on Nebius the OpenAI-compatible layer should hide this but is untested.
- Rate limits (example baseline 60 RPM / 400K TPM) can throttle long multi-agent demos; scale-up is gradual (x1.2 per 15 min), so warm up before the recording; Batch API is not suited to interactive loops.
- Credits: $25 may not cover heavy development with a 120B model; price unknown.
- Sandboxes are Beta/access-gated.
- Same project cannot be double-submitted as "new" to hackathons that forbid it; reuse across hackathons is allowed per HACKATHONS.md reading but check Nebius legal text.
- Judging is 1-15 Dec; repo must remain public and demo URL alive until then.

## Open questions
- Official per-model price, context length, and rate limits for Nemotron-3-Super/Lightning/Nano on Nebius serverless (needs API key).
- Which Nemotron IDs support tool calling on Nebius (catalog flag); is `-fast` flavor available for them?
- Official Devpost text: exact judging wording, whether a hosted demo URL is mandatory for a desktop+relay product, team size, eligibility, whether prior-hackathon work is allowed.
- City Winner: is physical attendance of a Builders and Brews event required, and does an online-only entrant qualify?
- Is Tavily integration judged by a separate rubric (what counts as "functional")?
- Does hosting the relay on Nebius AI Cloud earn anything extra versus hosting on AWS (needed for AWS Builder)?
