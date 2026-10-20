# 07 Protocols and prior art (research, 2026-10-07)

## Summary
Adopt, do not build, the wire and discovery layer: **A2A** (task delegation + Agent Card discovery) as the requester-to-owner protocol, **MCP** (Streamable HTTP, OAuth 2.1) as the interface to existing MCP clients and as the tool layer inside the owner's harness. ACP (IBM) is already merged into A2A, so it is not a choice. A2A explicitly has **no standard registry API**, no pricing, no ranking, and nothing about execution isolation: that gap is exactly agent-bridge's product (marketplace + stars + sandboxed local execution + payment). Existing marketplaces (Agentverse, Olas, Virtuals) are cloud- or blockchain-centric; none found that combine "harness runs on owner's laptop, requester data never leaves, GitHub-style ranking, PayPal checkout".

## Key facts (with sources)
- **A2A**: open protocol for opaque agents, Linux Foundation project contributed by Google; SDKs Python, Go, JS, Java, .NET, Rust; ~26k GitHub stars. https://github.com/a2aproject/A2A
- A2A spec: three bindings (JSON-RPC 2.0, gRPC, HTTP+JSON); Agent Card is a JSON doc with endpoint URLs, capabilities (streaming, push, extended card), security schemes (API key, OAuth2, mTLS, OIDC), skills; cards may be digitally signed (canonical JSON); public vs authenticated "extended" card; task states SUBMITTED, WORKING, INPUT_REQUIRED, AUTH_REQUIRED, COMPLETED, FAILED, CANCELED, REJECTED; version header `A2A-Version`, Major.Minor (spec shows "1.0"). https://a2a-protocol.org/latest/specification/
- A2A discovery: well-known URI (RFC 8615), curated registries, direct config. Quote: "The current A2A specification does not prescribe a standard API for curated registries." https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md
- **ACP** (IBM/BeeAI REST protocol, Mar 2025) joined A2A under LF AI & Data in Aug 2025; development winding down. Source is secondary (search summaries of IBM pages): https://research.ibm.com/projects/agent-communication-protocol , https://www.ibm.com/think/topics/agent-communication-protocol . Treat date details as UNVERIFIED against a primary announcement.
- **MCP** spec revision 2026-07-28 (latest at fetch): transports = stdio and Streamable HTTP (each message an HTTP POST, replies JSON or request-scoped SSE); every request carries protocol version/capabilities in `_meta`; servers no longer initiate JSON-RPC requests. https://modelcontextprotocol.io/specification/latest/basic/transports
- MCP auth (HTTP): optional; OAuth 2.1, mandatory Protected Resource Metadata (RFC 9728), RFC 8707 `resource` parameter and audience-bound tokens, PKCE, Client ID Metadata Documents preferred, DCR deprecated; tokens never passed through. https://modelcontextprotocol.io/specification/latest/basic/authorization
- **AGNTCY** (Linux Foundation; TSC incl. Dell, Red Hat, Cisco, Google Cloud, Oracle, Akamai): SLIM (secure messaging, Rust), Agent Directory (DIR, Go), Identity (agents and MCP servers), OASF schemas. https://github.com/agntcy . Heavy; useful as optional reference for signed identity and directory, not for a 3-week build.
- **AP2 / x402 on A2A**: AP2 (Agent Payments Protocol, Google agentic-commerce org) https://github.com/google-agentic-commerce/AP2 ; `a2a-x402` extension adds payment-required / payment-submitted / payment-completed messages to A2A https://github.com/google-agentic-commerce/a2a-x402 . Layering (A2A transport, AP2 authorization, x402 settlement) is from a secondary summary: UNVERIFIED in primary docs. x402 is crypto (USDC); PayPal track needs PayPal rails, so this is a design pattern to copy (payment-required state in task), not a dependency. Whether AP2 has a PayPal flow: UNVERIFIED.
- **OpenClaw**: MIT, ~391k stars, foundation-governed; local Gateway control plane; nodes are companion devices connecting to a Gateway over WebSocket, pairing approval, `system.run` remote exec governed by command allowlists; nodes are peripherals of ONE gateway (same owner), not a cross-user marketplace. https://github.com/openclaw/openclaw , https://docs.openclaw.ai/nodes . Plugins shared via ClawHub.
- **ClawHub supply-chain incident**: Koi Security found 341 malicious of 2,857 skills; RankClaw audit reported 1,103 of 14,706; VirusTotal scanning added; off-registry payloads still evade. https://unit42.paloaltonetworks.com/openclaw-ai-supply-chain-risk/ , https://techradar.com/pro/security/multiple-malicious-openclaw-skills-found-online-including-two-macos-infostealers (secondary figures). Direct evidence that an unvetted harness store is an attack surface: supports our sandbox-first design.
- OpenClaw already has community A2A plugin (A2A v0.3.0) per secondary sources (https://www.freecodecamp.org/news/openclaw-a2a-plugin-architecture-guide/ , https://a2a-mcp.org/entry/openclaw-a2a-gateway.md). Not verified by reading source: UNVERIFIED maturity.
- **Fetch.ai Agentverse**: registry + hosting (hosted or external LangGraph/CrewAI agents), ASI:One search ranking, analytics, paid access via tags/subscriptions/deep links, verified metadata. https://docs.agentverse.ai/documentation/getting-started/overview . Agents run on their cloud or via mailbox; FET payments not confirmed in the page read.
- **Olas Mech Marketplace**: on-chain registry, requesters hire "mechs", paid in crypto per request. https://docs.olas.network/ . Detail of escrow/dispute: UNVERIFIED.
- **Virtuals ACP (Agent Commerce Protocol, different from IBM ACP)**: EVM-based; phases Request, Negotiation, Transaction, Evaluation; escrow released after an evaluator agent verifies. Secondary sources only: https://reports.tiger-research.com/p/virtuals-protocol-acp-eng , https://forkast.news/the-machine-as-buyer-virtuals-acp-and-the-evaluator-problem/ . Idea to borrow: escrow + evaluate-before-release, which matches our "capture only on accept".
- **Instinct**: not found in searches; UNVERIFIED. Per decisions.md it has agent-to-agent on its own cloud.

## Fit for agent-bridge
Adopt:
1. **A2A Agent Card** as the published listing format. Put marketplace fields (speciality, price per task/hour, harness hash, stars) in card `skills` plus an extension/metadata block; sign the card. A2A client/server SDK (Python or JS) for the task lifecycle: SUBMITTED, INPUT_REQUIRED (owner approval, or clarification), COMPLETED/REJECTED map directly to our approve/preview flow. AUTH_REQUIRED can carry payment pre-auth.
2. **MCP server** (Streamable HTTP) exposing `delegate_task`, `browse_agents` so any MCP client (Claude Code, OpenClaw) can use the marketplace. Use MCP OAuth rules only if exposing it remotely; locally stdio suffices.
3. **MCP inside the harness** for owner tools (already in the harness pack format).
Build (the differentiator, nothing off the shelf):
- Registry/ranking API (A2A has none): stars, leaderboard, verified-run counts.
- Relay with E2E encryption so owner machine needs no inbound port (A2A assumes a reachable HTTP endpoint).
- Sandboxed execution + context isolation (per-task fresh memory, read-only granted folder, result preview).
- Payment: PayPal sandbox authorize-then-capture on accept (Virtuals-style escrow idea, not crypto).
- Observability UI.

Differentiator per competitor:
- A2A alone: protocol only; no registry, price, ranking, isolation, relay. We layer on it.
- MCP: tool access, not agent-to-agent delegation or marketplace.
- AGNTCY: infrastructure/standards stack, no end-user marketplace or local-execution demo.
- Agentverse: cloud/mailbox, own SDK (uAgents); we keep harness+data on owner's own machine and use open A2A.
- Olas/Virtuals: crypto/on-chain, mostly autonomous-agent economies; we use PayPal and a human-approved, privacy-first flow.
- OpenClaw nodes / ClawHub: single-owner device mesh and a skill store with proven malware problem; we add cross-user delegation with isolation, and rank whole harnesses, not skills.

## Recommendation
Use A2A (official SDK) for requester<->owner tasks and Agent Card listings, MCP for client interface and harness tools; route both through our encrypted relay. Skip AGNTCY, ACP, x402 as dependencies; borrow ideas (signed cards, escrow-evaluate-release, payment-required state). Keep the registry as a thin service of Agent Cards plus stars. Pitch line: "A2A has no registry or security story; agent-bridge adds the marketplace and the sandbox."

## Risks
- A2A relay mismatch: spec assumes direct HTTP endpoints; owner behind NAT needs a relay/tunnel, so we may implement a custom transport binding (allowed if "functionally equivalent") or reverse-connect polling.
- A2A SDK/spec churn (1.0 vs plugin's 0.3.0): pin version, check SDK matches spec 1.0.
- MCP spec 2026-07-28 changed to per-request metadata/no initialize; older SDKs may differ. Check SDK support.
- Agent Card trust: unsigned cards or self-reported stars are forgeable; need signatures and server-side counted stars tied to completed paid tasks.
- Third-party harness is hostile code (ClawHub precedent): protocol adoption does not solve isolation.
- Secondary-source claims above (ACP merger date, AP2 layering, Virtuals) not confirmed in primary text.

## Open questions
- Does the A2A Python/JS SDK support a custom or relayed transport cleanly, or must we wrap JSON-RPC over our relay?
- Does OpenClaw's A2A plugin work for our use, or should the owner runtime be our own A2A server wrapping OpenClaw?
- AP2 and PayPal: any official PayPal flow? (UNVERIFIED)
- Instinct details and whether it supports A2A (UNVERIFIED).
- Where to put price/stars: A2A extension URI vs separate registry metadata?
