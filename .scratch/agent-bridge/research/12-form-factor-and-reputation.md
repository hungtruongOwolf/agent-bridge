# 12 - Form factor and marketplace mechanics (agent-bridge, 2026-10-07)

## Summary
Recommend a CLI + daemon + web hybrid, not a desktop app or a pure web app. A pure web app cannot run the owner's local harness. A desktop app costs packaging time and adds nothing a local daemon with a browser UI does not give. The daemon is OpenClaw's own Gateway, extended. The requester side is the same daemon plus an MCP server and the web UI. The marketplace is one hosted web app (TanStack Start + Convex, forked from ClawHub, MIT). The phone approval page is a PWA route on the relay/marketplace origin. Reputation: stars are cheap social proof only. Rating and ranking must come from verified, paid, completed tasks (the PayPal capture event is the proof of purchase) plus a small reproducible eval ("verified" badge, like Hugging Face). The listing is an A2A-style Agent Card plus a harness-pack manifest.

## Key facts (with sources)
- OpenClaw Gateway runs as a daemon (LaunchAgent on macOS, systemd on Linux/WSL2, Scheduled Task on Windows). It serves a browser Control UI and has companion apps and node pairing. Node is the default runtime. https://docs.openclaw.ai/platforms
- The Control UI is a Vite + Lit SPA on port 18789 by default. It handles chat, activity monitoring, node management and config. Remote access is recommended via Tailscale. It is mobile-friendly, PWA-installable with web push, and pairing uses setup codes or tokens. https://docs.openclaw.ai/web/control-ui
- ClawHub is the public registry for OpenClaw skills and plugins. It has semver versions, tags, changelogs, download counts, stars, security scan summaries, user reports, and moderators who can hide or ban. Publishing needs a GitHub account old enough to pass the upload gate. https://docs.openclaw.ai/tools/clawhub
- ClawHub stack: TanStack Start (React, Vite/Nitro), Convex (DB, file storage, HTTP actions), Convex Auth with GitHub OAuth, OpenAI embeddings plus Convex vector search, MIT license. Skills are described by SKILL.md frontmatter (`name`, `description`, `metadata.openclaw.requires.env/bins`). https://github.com/openclaw/clawhub
- A2A Agent Card is JSON with identity/provider, service endpoint, capabilities, auth schemes, and skills (id, name, description, input/output modes, examples). Discovery is via `/.well-known/agent-card.json`, curated registries, or direct config. The doc says it does not address card signing. https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md
- MCP Registry holds metadata only (`server.json`: reverse-DNS name, package or remote URL, run instructions). It has namespace verification through GitHub/DNS/HTTP challenge, manual takedown, and delegates scanning and community ratings to downstream aggregators. It does not support private servers. https://modelcontextprotocol.io/registry/about
- Hugging Face model cards use YAML metadata (tags, license, base_model, pipeline_tag). Eval results live in `.eval_results/*.yaml` and aggregate into benchmark leaderboards. Badges: verified (a valid `verifyToken`, evaluation ran in HF Jobs with inspect-ai), community (open PR), source (links to traces). Marked work in progress. https://huggingface.co/docs/hub/model-cards and https://huggingface.co/docs/hub/eval-results
- GitHub: "Many of GitHub's repository rankings depend on the number of stars", and Explore shows popular repos by stars. https://docs.github.com/en/get-started/exploring-projects-on-github/saving-repositories-with-stars
- npm provenance links a package to its source and build via Sigstore (signing cert plus transparency log). It proves where the package was built, not that it is safe. https://docs.npmjs.com/generating-provenance-statements
- Terminal-Bench leaderboard ranks model+agent combinations by resolution rate, cost and token usage (v4.0). Task-format details were NOT on the landing page, so they are UNVERIFIED here. https://www.tbench.ai/
- Chatbot Arena ranks by pairwise human votes. The abstract mentions 240K+ votes and agreement with expert raters. The Bradley-Terry/Elo detail is NOT in the abstract, so it is UNVERIFIED here. https://arxiv.org/abs/2403.04132
- PayPal authorize/capture: a hold is placed first, capture comes later. Authorization is valid 29 days with a 3-day honor period, reauthorization is possible, and voiding is possible. Orders v2 has create/authorize/capture endpoints. https://developer.paypal.com/docs/checkout/standard/customize/authorization/ and https://developer.paypal.com/docs/api/orders/v2/
- munder-difflin (observability reference) is an Electron + React + TypeScript + Pixi.js + xterm.js + node-pty desktop app, MIT for source (assets licensed separately). It has OTel spans, a tool waterfall, and per-agent cost ledgers. https://github.com/HarnessMD/munder-difflin
- Smithery: its docs landing page does not cover listing format, badges or ranking, so those are UNVERIFIED. https://smithery.ai/docs

## Fit for agent-bridge

### Form factor by component
| Component | Form | Why |
|---|---|---|
| Owner daemon | OpenClaw Gateway (or our thin runtime) as a background service, started by a one-line CLI (`bridge publish ./harness-pack`) | Must run the local harness and data; OpenClaw already has the daemon, service install and Control UI |
| Owner console | Web UI served by the daemon on localhost (extend the OpenClaw Control UI, or a small page reusing munder-difflin ideas) | No Electron packaging; mobile-capable |
| Requester client | Same CLI/daemon plus an MCP server (`delegate_task`) and a web "Hire" page | Already decided: MCP interface |
| Phone approval | PWA/web page on the relay origin, opened via QR/push; shows task, scope, price, expiry; approve/deny | Control UI docs confirm PWA + web push is feasible in this ecosystem |
| Marketplace browse and leaderboard | Hosted web app (fork ClawHub: TanStack Start + Convex, MIT) | Stars, search, versions, moderation, GitHub login already exist. Convex is real-time, good for live status. Hosting it on AWS fits the AWS Builder challenge UNVERIFIED (check that Convex cloud vs AWS-hosted wording) |
| Live observability | Web view in the marketplace/console: map of machines, whose agent, status, step waterfall. Borrow only the data model (OTel spans, tool waterfall, ledger) from munder-difflin | Its UI is Electron/Pixi; we need a browser view, so lift ideas, not the app |

Desktop (Electron) is rejected for the core. If a tray icon is wanted, add it last.

### Listing format (reuse, do not invent)
- Agent Card (A2A-shaped JSON): name, provider, endpoint (relay address), skills[] (speciality tags, examples, input/output modes), auth scheme. Add our extension block: `pricing` (per task or per hour, currency), `harness_pack` (name, version, content hash), `permissions_required`, `data_residency: local`.
- Harness-pack manifest: a SKILL.md-style or `server.json`-style file (prompt, tool list, MCP config) with semver and a content hash. Publish metadata only. The pack never needs to be uploaded because the owner's private data and tools stay local. Optionally publish a public "sanitized" pack for the library.
- Namespace identity: reverse-DNS or `github:user/pack`, tied to GitHub OAuth (MCP Registry and ClawHub pattern).

### Reputation and anti-sybil design
1. Stars (cheap, GitHub-style): one per GitHub account, used for browse, trending and discovery, with an account-age gate as in ClawHub's upload gate. Weak signal, so label it "interest".
2. Verified reviews: only the requester who paid for a completed task can review it. A review is bound to the escrow record (PayPal order id, captured amount, task id, result hash). One review per task, weight proportional to the amount paid. This makes sybil reviews cost real money. Self-dealing (owner hires own agent) is limited by excluding same-GitHub or same-PayPal-account pairs and by weighting unique paying counterparties, not review count. This design is ours. No primary source describes a registry that does exactly this, so it is a proposal. The nearest sources are the PayPal authorize/capture flow and the HF "verified" badge idea.
3. Eval badge: a small suite of reproducible tasks per speciality (hidden test, auto-grade, run through the same delegate flow on a fixed model). Results stored as HF-style YAML (`task_id`, `value`, `date`, `source` = trace link, `verified` flag when run by the marketplace's own runner). Show cost and resolution rate side by side, as Terminal-Bench does (model+agent pairs, cost and tokens).
4. Ranking score (transparent, shown in UI): eval score x verified-review score (Bayesian-smoothed) with a small stars term. Optionally add "head-to-head" votes later (Arena-style). Skip for the demo.
5. Provenance of the pack: content hash plus signed manifest (npm provenance / Sigstore is the precedent). For the demo, a hash plus owner key signature is enough. Full Sigstore is UNVERIFIED as quick to wire.

## Recommendation
Minimal credible marketplace feature set for a polished demo (in priority order):
1. Listing page per agent+harness: Agent Card render, speciality tags, price, stars, verified-task count, eval badge, trace-linked sample run.
2. Browse/search/leaderboard by speciality (fork ClawHub UI/Convex; seed 5-8 listings from real OSS harnesses, with at least two live owner machines).
3. Hire flow: pick agent, enter task, PayPal sandbox authorize (hold), owner phone approval, live run view, result preview, requester accepts, capture, then prompt for a verified review/star.
4. Live observability view (machine graph, step waterfall, cost) used as the demo's visual centrepiece.
5. Reputation: stars plus "verified paid review" badge plus one eval badge on two seeded agents. Show the anti-sybil rule in the UI ("only completed paid tasks can review").
6. Cut: Arena-style voting, Sigstore, multi-currency, per-hour billing UI (support per-task only, mention per-hour on the listing), desktop app, voice (add last).
Time-box: Nebius deadline 30/10 needs steps 1-4 with NVIDIA Nemotron via Token Factory. PayPal (12/11) adds step 3's payment and review binding.

## Risks
- Forking ClawHub carries its Convex dependency and OpenAI embeddings (we may swap in a Nebius-hosted embedding model, UNVERIFIED availability) and extra surface to understand; budget one day to run it locally.
- Does OpenClaw Gateway expose what we need to be driven headlessly as the remote executor? NOT checked in this topic (see other research files).
- Hold expiry: PayPal authorization has a 3-day honor period and 29-day validity, so long tasks must capture or reauthorize in time.
- Reviews bound to payments still allow a wealthy attacker to buy reputation; the weighting limits but does not eliminate this. State it honestly in the threat table.
- HF verified eval relies on a trusted runner; our "verified" badge is only as trustworthy as the marketplace's runner. Do not claim more.
- Phone page on a public relay origin is a phishing/approval-fatigue target: show scope and price, require device-bound key.
- Claims marked UNVERIFIED above must not appear in submission copy.

## Open questions
- Does the PayPal AI Agentic Commerce rubric reward a hold-then-capture escrow, or an agent-pays-agent flow (check the hackathon page)? Not read in this topic.
- Smithery listing/badge format (docs landing page lacked it); read https://smithery.ai/docs/llms.txt if needed.
- Terminal-Bench task format and Arena rating method (read the repo and full paper) if we build the eval suite on them.
- Can the ClawHub fork run on AWS for the AWS Builder challenge, and does the Open Source challenge accept a ClawHub fork?
- Should listings of the harness pack itself be public, and who audits packs for malicious tools (ClawHub scans exist, details UNVERIFIED)?
