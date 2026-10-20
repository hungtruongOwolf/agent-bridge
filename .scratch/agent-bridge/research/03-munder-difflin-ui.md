# 03 - munder-difflin as an observability UI for agent-bridge

Researched 2026-10-07 by cloning https://github.com/HarnessMD/munder-difflin (shallow, HEAD committed 2026-10-07) and reading source. All facts below are from repo files unless marked UNVERIFIED.

## Summary

munder-difflin is a free MIT Electron desktop app that wraps terminal coding CLIs (Claude Code, Codex, Gemini CLI, etc.) as real PTY processes and shows them as pixel-art avatars at desks on a 2D "office floor" (Pixi.js), with a hive (mailboxes, router, orchestrator "Michael"), per-agent token/cost telemetry, a tool-span waterfall, a kanban, a message-thread viewer, and a cost circuit breaker. It is a LOCAL multi-agent dashboard: everything flows through Electron IPC (`window.cth`) from one main process. It is not a web app and has no notion of remote machines, owners, prices or ratings. Adapting it wholesale is a bad idea; lifting its visual language and 5-6 self-contained components (floor scene + message envelopes, status badge, tool waterfall, thread viewer, kanban, cost header) is realistic, and the quickest route is to treat it as a design/component reference and rewrite the data layer against our own WebSocket/SSE feed.

## Key facts (with sources)

- Repo: https://github.com/HarnessMD/munder-difflin (README links point at chaitanyagiri/munder-difflin; GitHub API reports full_name HarnessMD/munder-difflin, ~8.5k stars, TypeScript, pushed 2026-10-07). Version 0.5.3 in README (package.json says 0.4.6), labelled "pre-release".
- License: MIT for source (https://github.com/HarnessMD/munder-difflin/blob/main/LICENSE, (c) 2026 Chaitanya Giri). Art assets are NOT MIT: `LICENSE-ASSETS` says the tilesets/maps under `src/renderer/src/assets/` are LimeZu "Modern Interiors" under a separate paid licence; credit to https://limezu.itch.io/ is mandatory, no resale of the assets. Character sprites are procedurally drawn (`scene/office/portraitArt.ts`) and MIT. The author also sells a Pro plan (README); UNVERIFIED which features, if any, are gated in the open-source build (no licence gating found in `src/main` by grep).
- Stack (package.json): Electron 32, React 18, TypeScript 5, electron-vite/Vite 5, Pixi.js 8 (floor), xterm.js + node-pty (terminals), zustand (store), better-sqlite3, i18next, Monaco/CodeMirror, `@openai/agents-realtime` (voice), localtunnel/tunnelmole, PostHog (anonymous telemetry, allowlisted in TELEMETRY.md; must be disabled/removed in a fork).
- Architecture (docs/ARCHITECTURE.md): two planes, a "terminal plane" (PTYs) and an "event plane" (hook server + hive router + GOD agent), both reaching React via a typed `window.cth` preload bridge. 55 renderer files reference `window.cth`, so the UI is tightly coupled to Electron IPC.
- Data model the UI expects:
  - `Agent` (store/store.ts): id, name, character (avatar), accent, description, project, cwd, status, action, progress, currentStation, carrying (tool kind), recentAssistantText, blockReason {summary, detail, command, actions[approve|deny]}, ptyId, command, provider, model, lastPrompt, contextTokens/contextLimit, isGod, onHold, worktreePath.
  - `StatusKind` (components/PixelBadge.tsx): idle, thinking, working, waiting, blocked, success, ghost, compacting, looping, typing.
  - `HiveMessage` (src/main/hive.ts): id, conversation, in_reply_to, from, to (agentId | 'god' | 'broadcast'), act (request, inform, propose, query, agree, refuse, done), subject, body, hops, requires_reply, needs_human, created_at.
  - Telemetry (hooks/useTelemetry.ts): `AgentUsageSample` {agentId, sessionId, ts, input, output, cacheRead, cacheCreation, model, usd}, `ToolSpan` {agentId, ts, tool, success, durationMs, decision, error}, `BreakerState` {agentId, level healthy|steering|constrained|stopped, reason}. Samples are cumulative snapshots.
  - Source of cost: Claude Code OTel / transcript JSONL (`src/main/telemetry.ts`, `transcript.ts`, `usage.ts`, `pricing.ts`); pricing is model-table based, Claude-centric.
- A synthetic event generator exists (`store/mockEvents.ts`) that drives avatars without real PTYs; useful for a demo/prototype data feed.
- Message flight animation: `scene/office/MessageEnvelope.ts` (146 lines) draws an envelope flying between two desks, tinted by speech-act (request=sky, refuse=coral, done=mint). This is exactly "who talks to whom".

## Fit for agent-bridge

What we need on screen: who requested, which owner machine/agent runs it, live status, cost, task trace; plus marketplace browse/rank (not in munder-difflin at all).

Pick (reuse or port as reference):
1. Design system: `design/tokens.css`, `tokens.ts`, `fonts.css`, `components/PixelPanel.tsx`, `PixelBadge.tsx`, `PixelButton.tsx`. Gives a polished, consistent look cheaply. Rebrand colours (their maroon/gold is Dunder-Mifflin branding) to avoid looking like a clone.
2. `components/PixelBadge.tsx` status model: map to bridge task states (queued, awaiting-approval = blocked, running = working, thinking, returning, success, refused = looping/ghost).
3. `scene/office/*` floor scene, reinterpreted as a "network floor": one room/desk cluster per machine (requester side, owner side), avatar per remote agent+harness, `MessageEnvelope` flying across for task-request and result-return, `ThoughtBubble`/`ToolBubble` for current tool, `Camera`, `TiledMapRenderer`. Highest wow factor; also highest cost (OfficeFloor.tsx alone is 1805 lines, Character.ts 972, themes tied to LimeZu tilesets).
4. `components/ToolWaterfall.tsx` (93 lines): per-task tool-span timeline with cost header; nearly drop-in once `useAgentSpans`/`useFleetTelemetry` are replaced by our feed. Directly serves "task trace".
5. `components/ThreadsPanel.tsx` (175 lines): grouped conversation viewer with speech-act colours; reuse for requester<->owner task conversation, and as the audit-log view.
6. `components/BlockedBanner.tsx` + `AgentCard.tsx`/`AgentStrip.tsx`: approval banner (summary, command, approve/deny) maps to owner approval and result-preview gate; cards map to marketplace listing/agent status cards.
7. `components/TasksKanban.tsx` (499 lines): optional; task board of delegated jobs.
8. Cost/breaker concept (`breaker.ts` 416 lines, levels healthy/steering/constrained/stopped): borrow the idea for per-task budget limits (PayPal pre-auth cap); do not port code (Claude transcript-coupled).

Drop:
- Everything Electron/PTY: `PtyTerminalView`, `TerminalView`, `FullscreenTerminal`, `terminal*` helpers, `node-pty`, `xterm`, `pty.ts`, `hooks.ts` (Claude hook shims), `workerLaunch/Wake`, `hire*`, `cliInstall`, `nodeInstall`.
- IDE/dev-tool surfaces: `FilesTab`, `FileTree`, `GitTab`, `CodeEditor`, Monaco/CodeMirror, `git/`, `github.ts`.
- Product shell: `OnboardingWizard`, `SettingsModal`, `AiEnginesSettings`, `McpDefaultsSettings`, `IntegrationsRegistry`, `SkillsTab`, `UpdateToast/Badge`, `ReleaseDrop`, `QuitWarningModal`, `i18n` (unless wanted), `analytics.ts`/PostHog, `slack*`, `webhook`, `triggers/`, `freeflow`, localtunnel/tunnelmole.
- Local-memory features: `MemoryPanel`, `MemoryGraphPanel`, `memory.ts`, `reflect.ts`, hive git/markdown memory (conflicts with our isolation goal; we do not want shared memory).
- Voice: `realtime*` (we use PersonalJarvis as voice reference separately).
- Marketplace pieces missing entirely and must be built: listings, price, speciality, stars/leaderboard, ranking, wallet/payment status, machine identity/trust badges, security/isolation indicators.

Effort estimate (our judgement, UNVERIFIED by prototyping):
- Port design tokens + 3 Pixel components + ToolWaterfall + ThreadsPanel into a Vite/React web app, fed by our own JSON/WebSocket events: about 1 day.
- Add the Pixi floor with envelopes, desks per machine, stripped of IPC: 2-3 days (hard parts: `OfficeFloor.tsx` is large and coupled to the zustand store and `window.cth`; LimeZu asset licence needs credit; need to rewrite the cast/seat logic to remote agents).
- Forking the whole app and bending it to a marketplace: not recommended (Electron-only, 55 files tied to `window.cth`, 53 main-process modules).
- Alternative for the "who talks to whom" view: a simpler Pixi/SVG node graph with the same envelope animation and badges; lower risk, ~1 day.

## Recommendation

Do not fork munder-difflin as the app. Build the agent-bridge UI as a web app (works from the phone approval page too) and copy in, with MIT attribution (keep LICENSE notice, add LimeZu credit if tiles are used):
1. Design tokens + PixelPanel/Badge/Button (look and feel).
2. ToolWaterfall + ThreadsPanel + BlockedBanner (task trace, conversation, approval).
3. A trimmed Pixi "network floor" (MessageEnvelope, Camera, Character/ThoughtBubble, tile map) as the headline demo visual, only if time allows after the trace/status views work; otherwise ship the node-graph variant with the same envelope and status colours.
Define our own event schema (task.created, task.approved, tool.span, usage, result.preview, result.returned, payment.captured) mapped onto `HiveMessage`/`ToolSpan`/`AgentUsageSample` shapes so ported components need minimal change. Use `store/mockEvents.ts` as a pattern for a scripted demo feed. Use a different colour theme/mascot art to avoid brand confusion. Remove PostHog. Marketplace browse/leaderboard should be built with an off-the-shelf React table/card kit, not from munder-difflin.

Optional: munder-difflin itself could be a "harness library" candidate (its agents are CLI wrappers), but that is out of scope here.

## Risks

- Electron/IPC coupling: components import `window.cth` types and hooks; porting means rewriting hooks (`useTelemetry`, `useHive`, store) before anything renders.
- Asset licence: LimeZu tilesets need credit and cannot be redistributed outside the app; the Pixi floor looks bare without them (use own tiles or simple shapes).
- Cost model is Claude/Sonnet-centric (`pricing.ts`, transcript usage); Nemotron via Nebius needs its own pricing table (UNVERIFIED current Token Factory prices).
- Visual identity heavily tied to "The Office" (Dunder-Mifflin colours, cast names); trademark-adjacent, rebrand.
- Project is fast-moving (pre-release, daily commits); pin a commit.
- Judges may see "reskinned munder-difflin"; open-source reuse is encouraged by our principle, but credit it clearly and make the marketplace/security layer the visible original work.
- Open Source mini challenge wording: confirm whether vendored third-party code is acceptable (UNVERIFIED).

## Open questions

- Form factor decision (web vs desktop vs hybrid): this research favours a web UI; confirm.
- Does the owner want the pixel-office metaphor, or a more enterprise look for PayPal judges?
- Which event source feeds the UI: our relay (cleaner) or OpenClaw events (need to check what OpenClaw exposes; separate research topic)?
- Any Pro-gated features in the OSS build? (not found, not fully audited)
- Exact behaviour of `OfficeFloor.tsx` when detached from the store (not tested; no build run).
