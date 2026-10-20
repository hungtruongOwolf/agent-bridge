# Amazon "Build, Ship, Shape" track: AWS Builder + Open Source mini challenges (research, 2026-10-07)

## Summary
- The Amazon hackathon (Devpost: https://amazonappdev2026.devpost.com/) has four device tracks (Fire TV, Alexa+, Bee, Ring). Mini challenges (AWS Builder, Open Source; $5K each) are layered on top of a primary track submission, not standalone. So entering the mini challenges means ALSO entering a primary track; for agent-bridge that is Alexa+.
- The Alexa+ track does not require Echo hardware and accepts three paths: Agent Skill, MCP-based experience, or a simulated Alexa+ experience. agent-bridge already plans an MCP server, so the minimal path is cheap.
- IMPORTANT: the official Devpost pages (home, /rules, /resources) returned 503 "planned maintenance" (WebFetch and Chrome, 2026-10-07) and 403 to curl. Everything about the track/mini-challenge rules below comes from SECONDARY aggregators and is UNVERIFIED against the legal rules text. Re-read the Devpost rules before committing.
- Recommendation: CONDITIONAL GO, time-boxed (see Recommendation).

## Key facts (with sources)
Dates and prizes
- Start 31 Aug 2026; submission deadline 23 Oct 2026 12:00 PM PT (matches hub). Judging 9-20 Nov. Source: https://www.aicompetition.dev/en/competitions/amazon-build-ship-shape-2026, https://tierones.io/opportunities/amazon-build-ship-shape-2026 (secondary).
- Fire TV and Alexa+ prizes $25K / $15K / $4K; mini challenges $5K each; AWS credits up to $15K additionally (tierones, secondary). One track prize + one mini challenge prize max per project (howdoiuseai blog, secondary: https://www.howdoiuseai.com/blog/2026-09-25-how-to-enter-amazon-s-190k-hackathon-with-an-mcp-s).

Submission requirements (secondary, aicompetition.dev): project description, PUBLIC GitHub repo WITH an open-source license, public English demo video under 3 minutes, product feedback, track selection. Existing projects must explain what was updated. (The open-source license is therefore a requirement for every entry, which makes the Open Source mini challenge cheap on the licensing side.)

Mini challenges (secondary, per a search summary of the Devpost page; wording UNVERIFIED)
- AWS Builder: incorporate AWS services with documented integrations into the primary-track project (examples listed: Amazon Bedrock, AgentCore, Strands SDK, Kiro, SageMaker, and more). Whether plain hosting (EC2/Fargate/Lambda) of the relay counts is UNVERIFIED; hub file assumes "relay hosted on AWS, documented".
- Open Source: "making a contribution to an open-source repository during the hackathon window, alongside your primary submission"; public repos and popular package directories work (same summary). This reads as a contribution to an (upstream) open-source repo, and may not be satisfied by merely licensing our own new repo. UNVERIFIED; check exact text. Practical hedge: send a real PR to a reused upstream (e.g. OpenClaw or an MCP SDK) during the window.
- Credits: builders can request $150 AWS credits via a credit request form (howdoiuseai, secondary).

Alexa+ track technical requirements (primary: Amazon docs)
- Alexa+ accepts MCP, Agent Skill or simulated-experience path (aicompetition.dev, secondary). No Echo needed; testable in a browser web simulator (https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html).
- MCP add-on server must: support Streamable HTTP (spec 2025-11-25 deprecates HTTP+SSE), be reachable at a remote URL (cloudflared tunnel OK for dev), support OAuth 2.1 authorization code + PKCE (S256), return 401 Unauthorized for unauthenticated requests, host RFC 9728 Protected Resource Metadata, auth server metadata at /.well-known/oauth-authorization-server with S256 listed; round-trip latency under 500 ms (quickstart doc). Sources: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html, https://developer.amazon.com/docs/alexaplus/add-ons/category-sdk-mcp-authentication.html (found via search; page body not read).
- Tooling: `alexa-ai configure` (Login with Amazon developer account), `alexa-ai new mcp`, fill `addon.json` (descriptions, compliance URLs, media), `alexa-ai deploy` to development stage, test in web simulator; certification only needed to publish (quickstart). Whether the hackathon requires certification: UNVERIFIED (likely not, since simulator path exists).

AWS building blocks
- API Gateway WebSocket pricing: per million messages and per million connection minutes; messages metered in 32 KB increments, max 128 KB; ping/pong free; free tier 1M messages + 750K connection minutes/month for 12 months for new customers; AWS's example of 1,000 users 12 h/day = about $23.40/month. Source: https://aws.amazon.com/api-gateway/pricing/.
- Nitro Enclaves: isolated VM carved from an EC2 instance, no persistent storage, no external network, no SSH, parent root cannot read it; supports cryptographic attestation integrated with KMS key policies; no extra charge beyond EC2; up to 4 enclaves per parent; enclaves die with the parent instance; supported on many instance families, not on the smallest sizes (e.g. m5.large excluded; c5.xlarge-class and up). Source: https://docs.aws.amazon.com/enclaves/latest/user/nitro-enclave.html.

## Fit for agent-bridge
- Alexa+ via MCP: the bridge already exposes an MCP server (decisions.md). Alexa+ needs that server public, Streamable HTTP, OAuth 2.1 PKCE. The relay can host this same endpoint; the "voice" story is "Alexa, ask Bridge to delegate task X to the top-rated data-analysis agent" (simulated in the web simulator, no Echo). Effort: mostly the OAuth/PRM plumbing (reuse an existing OAuth server library or AWS Cognito, do not hand-write).
- Cheapest solid relay architecture (my assessment; costs beyond the fetched pricing page UNVERIFIED):
  1. Single small container/VM (EC2 t4g/small or Fargate/App Runner) running the relay: holds outbound WebSocket connections from owner machines, serves the MCP Streamable HTTP endpoint + web UI, SQLite/Postgres or DynamoDB for listings/stars. Fewest moving parts, no WebSocket message metering, easiest TLS (ALB or Caddy). Best for a 16-day sprint.
  2. API Gateway WebSocket + Lambda + DynamoDB: serverless, free-tier friendly, but more glue (connection table, Lambda per route, 128 KB message cap and 10-minute connection limit are UNVERIFIED here) and awkward for streaming long tasks.
  3. IoT Core (MQTT): works for many outbound device connections but adds a second protocol; not worth it.
  Pick option 1; document it in README with an architecture diagram for the AWS Builder judges. Adding one managed AI/agent service (e.g. Bedrock for a non-core feature) may be needed if "documented integration" means more than hosting: UNVERIFIED. Must not replace Nebius/NVIDIA models in the core path (Nebius submission requires them).
- Nitro Enclaves: relevant only for a relay-side or AWS-hosted agent runner (attested enclave that executes third-party harness code on requester data, with KMS-released keys). Owner machines are local so enclaves do not protect the core local-execution flow. Good as a documented "hosted execution tier" in the threat model/roadmap, too costly to build in 16 days. Treat as stretch/diagram only.
- Open Source: repo must be public with an OSS license anyway (Apache-2.0 or MIT; also matches OpenClaw/MCP ecosystem conventions; check OpenClaw's license for compatibility: not researched here). Add one upstream PR (OpenClaw, MCP SDK, or munder-difflin) to hedge the "contribution" wording.

## Recommendation
CONDITIONAL GO, strictly time-boxed:
1. Today: re-read Devpost rules when maintenance ends. Confirm (a) mini challenges require a primary track, (b) AWS Builder qualifying wording, (c) Open Source "contribution" wording, (d) existing-project/new-in-window rule.
2. Alexa+ minimal scope (about 1-1.5 days): public Streamable HTTP MCP endpoint on the AWS relay with `list_agents`, `delegate_task`, `get_result`; OAuth 2.1 PKCE via a library/Cognito; one web-simulator demo clip; 3 min video segment. No Echo, no Skill, no certification.
3. AWS Builder: host relay on one AWS compute service, document it (diagram + README), claim $150 credits.
4. Open Source: MIT/Apache-2.0 license, plus one small upstream PR before 23/10.
5. Nebius (30/10) stays the priority; cut Amazon if the core marketplace demo is not working by about 16/10, as the hub file says. The deliverables overlap heavily (public repo, demo video), so marginal cost is low; the Alexa+ OAuth plumbing is the main real cost.
Expected value: the track prizes are competitive ($25K top); the realistic target is a mini challenge ($5K) given one prize of each type max, but even that likely requires being credible in the Alexa+ track.

## Risks
- Rules unverified (Devpost down); mini challenges might need more than hosting, or the Alexa+ path might judge "Alexa fit" and score a marketplace low on that axis.
- Alexa+ OAuth 2.1/PKCE/RFC 9728 plumbing is fiddly and the 500 ms round-trip limit conflicts with long-running delegated tasks (use async: delegate returns a task id; poll/notify).
- Web simulator/CLI availability may require a Login with Amazon developer account and possibly region/device eligibility: UNVERIFIED.
- Time split with Nebius (30/10) and PayPal (12/11) deliverables.
- Judging by "Alexa+ experience" may disfavor a product whose main UI is web/phone.
- Same project cannot take two track prizes; also Amazon excludes some regions (Brazil, Quebec, Russia, etc.; owner is US-based, fine).

## Open questions
- Exact Devpost wording for both mini challenges and the judging criteria (not retrievable on 2026-10-07).
- Does hosting-only on EC2/Fargate satisfy AWS Builder, or must Bedrock/AgentCore/Strands/etc. be used?
- Does the Open Source challenge require a contribution to a third-party repo, or is a new public licensed repo enough?
- Does the Alexa+ track require a deployed add-on in the simulator (alexa-ai deploy) or only a public MCP URL plus video?
- Is "new or significantly updated in window" enforced per hackathon for reuse across Nebius/PayPal submissions?
- OpenClaw license and whether it allows our planned redistribution.

## Sources
- https://amazonappdev2026.devpost.com/ (503 maintenance, not read)
- https://www.aicompetition.dev/en/competitions/amazon-build-ship-shape-2026 (secondary)
- https://tierones.io/opportunities/amazon-build-ship-shape-2026 (secondary)
- https://www.howdoiuseai.com/blog/2026-09-25-how-to-enter-amazon-s-190k-hackathon-with-an-mcp-s (secondary)
- https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html
- https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-test-add-ons.html
- https://developer.amazon.com/docs/alexaplus/add-ons/category-sdk-mcp-authentication.html (search snippet only)
- https://aws.amazon.com/api-gateway/pricing/
- https://docs.aws.amazon.com/enclaves/latest/user/nitro-enclave.html
