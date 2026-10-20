# 04 - Harness library: existing open-source harnesses/packs to install on owner machines

Date: 2026-10-07. Stats pulled with `gh repo view` / `gh api` on 2026-10-07 (stars, pushedAt = last push, license from GitHub metadata). Not verified: skill quality, demo behaviour (nothing was installed or run).

## Summary
Plenty of strong, actively maintained, permissively licensed material exists, so we should build zero harness content ourselves. Best "library" strategy: OpenClaw as base, ClawHub as the skill/package registry model (it already has stars, search, publish, versioning), plus a small set of curated packs for three demo tasks. The ClawHub registry has a serious malware problem, so only curated, pinned, reviewed skills should be installed on owner machines. That also reinforces our isolation story.

## Key facts (with sources)
- OpenClaw: MIT, 391,525 stars, last push 2026-10-07. Local gateway; models and agent harnesses (Claude, Codex, local models) are swappable plugins; installs via npm or install script. https://github.com/openclaw/openclaw
- ClawHub (the OpenClaw registry): MIT, 9,491 stars, last push 2026-10-06. Publish/version/search skills (`SKILL.md` plus files), vector search, stars and comments, VirusTotal-linked moderation, CLI (`clawhub install/inspect/pin`), and package catalog with "experimental whole-agent Claw packages". Directly overlaps our marketplace/stars idea; its schema/CLI could be reused or mirrored. https://github.com/openclaw/clawhub
- VoltAgent/awesome-openclaw-skills: MIT, 52,977 stars, last push 2026-10-05. Curated from ClawHub; states 373 skills excluded as malicious per security audits and 4,065 as spam; warns about prompt injection, tool poisoning, hidden payloads. https://github.com/VoltAgent/awesome-openclaw-skills
- anthropics/skills: 179,957 stars, push 2026-10-05; license NOT a single one (GitHub: none). README says many skills are Apache 2.0, but docx/pdf/pptx/xlsx are source-available, not open source. Includes mcp-builder, webapp-testing, skill-creator, xlsx, pdf. https://github.com/anthropics/skills
- wshobson/agents: MIT, 40,258 stars, push 2026-10-05. 94 plugins, 202 agents, 184 skills, 105 commands; multi-harness (Claude Code, Codex, Cursor, OpenCode, Copilot, others). https://github.com/wshobson/agents
- VoltAgent/awesome-claude-code-subagents: MIT, 25,548 stars, push 2026-10-05; 100+ subagents. https://github.com/VoltAgent/awesome-claude-code-subagents
- hesreallyhim/awesome-claude-code: 55,175 stars, push 2026-10-07; license "NOASSERTION" (custom), so link, do not redistribute. https://github.com/hesreallyhim/awesome-claude-code
- ComposioHQ/awesome-claude-skills: 76,622 stars, push 2026-09-18; no license in metadata. https://github.com/ComposioHQ/awesome-claude-skills
- OpenHands: MIT, 90,136 stars, push 2026-10-07; full coding agent platform. https://github.com/OpenHands/OpenHands
- SWE-agent: MIT, 20,495 stars, push 2026-10-06; mini-swe-agent: MIT, 8,256 stars, push 2026-10-06, "100 line" agent, claims >74% SWE-bench Verified (repo description, unverified by us). https://github.com/SWE-agent/SWE-agent , https://github.com/SWE-agent/mini-swe-agent
- Cline: Apache-2.0, 69,957 stars, push 2026-10-07. https://github.com/cline/cline
- OpenAI Codex CLI: Apache-2.0, 128,094 stars, push 2026-10-07. https://github.com/openai/codex
- PatrickJS/awesome-cursorrules: CC0, 40,885 stars, last push 2026-05-30 (stale ~4 months). https://github.com/PatrickJS/awesome-cursorrules
- punkpeye/awesome-mcp-servers: MIT, 95,887 stars, push 2026-09-27; modelcontextprotocol/servers (reference MCP servers): 91,053 stars, push 2026-10-05, license "other". https://github.com/punkpeye/awesome-mcp-servers , https://github.com/modelcontextprotocol/servers
- langchain-ai/deepagents: MIT, 29,976 stars, push 2026-10-07, "batteries-included agent harness" (planning, filesystem, subagents). https://github.com/langchain-ai/deepagents
- microsoft/data-formulator: MIT, 17,538 stars, push 2026-10-05; interactive AI data analysis/visualization. https://github.com/microsoft/data-formulator
- Aider: Apache-2.0, 49,403 stars, last push 2026-05-22 (stale). https://github.com/Aider-AI/aider

## Ranking (top 10 for agent-bridge, by quality/license/activity/fit)
| # | Item | Fit for demo tasks | Notes |
|---|------|--------------------|-------|
| 1 | OpenClaw + ClawHub (platform + registry) | all; also the marketplace model | MIT, very active; use `clawhub install/pin` for pack distribution |
| 2 | wshobson/agents | code patching, review, research | MIT, multi-harness, largest permissive pack; pick a handful of plugins |
| 3 | anthropics/skills (Apache-2.0 subset: mcp-builder, webapp-testing, skill-creator) | code patching, tooling | avoid redistributing docx/pdf/pptx/xlsx (source-available) |
| 4 | mini-swe-agent / SWE-agent | code patching (issue to patch) | MIT, tiny, easy to sandbox; good "owner's codebase, only patch returns" demo |
| 5 | OpenHands | code patching, long multi-step | MIT, heavy (Docker sandbox); strong visual demo but costly to run |
| 6 | langchain-ai/deepagents | research, long multi-step | MIT, planning + subagents + filesystem; model-agnostic so works with Nemotron via OpenAI-compatible API (UNVERIFIED for Nebius) |
| 7 | microsoft/data-formulator | private-data analysis | MIT, UI-first; could be wrapped, or borrow ideas only |
| 8 | VoltAgent/awesome-claude-code-subagents | role prompts (analyst, reviewer) | MIT, text-only, safe to copy/adapt with attribution |
| 9 | punkpeye/awesome-mcp-servers + modelcontextprotocol/servers | tools (filesystem, fetch, sqlite) | MIT/"other"; use reference servers for read-only file and SQL tools |
| 10 | Cline / Codex CLI (as pluggable runtimes) | code patching | Apache-2.0; alternative runtimes behind our interface; cursorrules/Aider deprioritized (stale) |

Data-analysis note: no single dominant data-analysis harness was verified; practical path is a harness pack of (filesystem/sqlite MCP + Python sandbox + an analyst subagent prompt). UNVERIFIED which community ClawHub data skills are good; needs hands-on vetting.

## Fit for agent-bridge
- A harness pack = OpenClaw skills + MCP config + subagent prompts, versioned and starred through a ClawHub-like registry. Reuse ClawHub schema/CLI instead of building a registry.
- Three demo packs: "Private Data Analyst" (analyst prompt + sqlite/filesystem MCP + Python), "Patch Smith" (mini-swe-agent or wshobson code plugins), "Researcher" (deepagents or research subagents + web search such as Tavily).
- Prefer permissive text/config packs: they can be audited in minutes, matching our "owner approves, tight permissions" model.

## Recommendation
1. Base: OpenClaw, with ClawHub as registry model (fork or mirror its schema for stars/leaderboard).
2. Ship exactly three vetted, pinned packs built from wshobson/agents (MIT), anthropics/skills Apache-2.0 skills, mini-swe-agent, and reference MCP servers. Record commit SHAs and licenses in a NOTICE file (also helps the Open Source mini challenge).
3. Do not auto-install community ClawHub skills on owner machines; allow only allow-listed, pinned versions, and run a scanner (e.g. Snyk agent-scan, linked from the VoltAgent list) as a publish gate. This is a good marketplace feature to demo.
4. Verify Nemotron-via-Nebius tool-calling works in the chosen runtime early (Nebius requirement).

## Risks
- Supply-chain: ClawHub-derived list alone flags 373 malicious skills; a marketplace of third-party harnesses inherits this risk. Mitigate with curation, pinning, sandbox, scanner.
- Licensing: anthropics/skills mixed licenses; awesome-claude-code and ComposioHQ lists lack clear licenses.
- Star counts here are huge and may include hype; quality was not tested.
- OpenClaw is fast-moving (push today), API drift risk during the hackathon; pin a version. Node 24.16+/26.1+ is required per README (Windows owner machine must satisfy this).
- OpenHands/Docker weight may break two-machine demo reliability.

## Open questions
- Do the chosen packs call tools reliably with Nemotron on Nebius Token Factory? (UNVERIFIED)
- How does OpenClaw's skill/permission model map to read-only single-folder grants? Needs a pass over docs.openclaw.ai (not read in this task).
- Is ClawHub's "whole-agent Claw package" format stable enough to use as our harness-pack format? (README says experimental.)
- Which specific ClawHub data-analysis skills are trustworthy? Needs hands-on review.
