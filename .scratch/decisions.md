# agent-bridge: decisions (from grilling, 2026-10-03)

Problem: two people on two machines cannot hand a task to each other's agent. The agent with the better harness (prompt, tools, MCP, skills, local data) lives on one machine. Sharing a machine/cloud account means surveillance/security issues. OpenClaw is local, one machine; Instinct has agent-to-agent but on its own cloud.

- Model: remote execution. Requester sends a task; the owner's agent runs it locally with the owner's harness and data; only the result returns. Harness and data never leave the owner's machine.
- Agent runtime: our own small runtime calling NVIDIA Nemotron via Nebius Token Factory (OpenAI-compatible API) so the Nebius submission is valid. A "harness pack" is a folder (prompt, tool list, MCP config). Runtime sits behind an interface so Claude Code can be plugged in for development.
- Demo: two real machines (any OS), phone web page for approval. Scenario: privacy. Owner's machine holds a private dataset/codebase; requester asks via their agent; owner's agent computes locally and returns only the answer or patch; show that the raw file never appears on the requester machine.
- Add-ons (built after core, per hackathon): Alexa+ (Amazon, 23/10) is ON HOLD, see HACKATHONS.md; PayPal sandbox pay-per-task (PayPal, 12/11), Tavily web search tool (Nebius award), AWS-hosted relay (AWS Builder mini challenge), open-source license (Open Source mini challenge).
- Owner participates as an individual, not via employer accounts.

- Approval: desktop notification + phone web page (via relay). No voice approval (security action).
- Remote agent permissions: default very tight. Read-only access to one granted folder; fixed tools (read files, Python in sandbox, Tavily web search); no shell. Owner sees a preview of the result before it leaves the machine; auto-return is an optional setting.
- Payment (PayPal module, built after core): owner sets a price per task type; requester pre-authorizes in PayPal sandbox; funds captured only when the result is accepted.
- Interface: the bridge also exposes an MCP server (delegate_task etc.) so any MCP client can use it. Owner has no Echo device; any Alexa path would be the simulated web app.
- Threat model (documented as a 'who can do what' table): public-key identity, end-to-end encryption (relay sees ciphertext only), every task approved, auto-expiry, step and time limits, append-only audit log.

## Pivot (2026-10-07): marketplace of agent + harness
Context: Sherpa (A) is DONE and out of scope; B is the only active project and gets full effort. Quality bar: very polished, top-tier demo flow, long/hard task chains automated end to end.

- Core insight: no single harness is best at everything. Each person owns a harness/agent set but cannot borrow another's, and there is no shared context/memory across the system.
- New framing: a MARKETPLACE of agents + harnesses. Owners publish their agent+harness with a price (per task or per hour) and a speciality. Requesters can (1) delegate a task to run on someone else's machine (saves own resources), (2) browse/rank top agent+harness (GitHub-style stars, leaderboard).
- Open problem to research and solve: security + context/memory isolation, so a third-party agent/harness cannot steal the requester's info (and the owner's data stays local). Needs concrete solution, not hand-waving.
- Open question: form factor (web / desktop app / CLI+web hybrid).
- Build-vs-reuse: do NOT build simple things ourselves. Base platform = OpenClaw. Source strong existing harnesses from GitHub as a "library" installed on machines.
- Voice: reference https://github.com/PersonalJarvis/PersonalJarvis
- Observability UI (see which machine talks to which, whose agent, status): reference https://github.com/HarnessMD/munder-difflin, pick only the needed parts.
- Hackathons to serve deeply: Nebius x NVIDIA (30/10), PayPal AI Agentic Commerce (12/11), plus Amazon track mini challenges (AWS Builder, Open Source; Amazon deadline 23/10; Alexa on hold).
- Earlier "keep core tiny / simple" guidance is superseded.

## Round 2 input (2026-10-07, owner)
- TIME IS NOT A CONSTRAINT: design the best possible version; owner will finish it. Stop optimizing for a 3-week cut line.
- Must design CONTEXT MEMORY properly: reasonable structure, updatable over time, and shareable across the system without leaking.
- Must emphasize HOW THE HARNESS + AGENT IS DESIGNED AND DEVELOPED (pack format, lifecycle, versioning, eval, how it improves). Round 1 under-covered this.
- Security direction: the agent may READ the data, but nothing is SENT to a foreign pack ("as you said": Pull mode, foreign pack runs in a sandbox next to the data). Plus ACTIVE DEFENSE: if there are signs of context/memory theft, block immediately (detect + kill + quarantine).
- Both modes should exist: Pull (private data, pack runs locally in sandbox) and Hosted (run on someone else's machine to save own resources / use their stronger setup).
