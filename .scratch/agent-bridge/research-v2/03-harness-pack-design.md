# 03 - Harness pack design (what a pack IS, how it is built, versioned, evaluated, published, ranked)

Date: 2026-10-07. Round 2. Scope: pack format and lifecycle. Memory internals, sandbox internals and active defense are other topics; this file defines only the manifest hooks they need.
Legend: [V] verified from the cited primary source this session. [U] UNVERIFIED / our own proposal.

## Summary

- No existing format is a complete "pack". Each covers one slice: Agent Skills (instructions + scripts, progressive disclosure), AGENTS.md (plain markdown context), Claude Code plugins (bundle of skills, subagents, hooks, MCP, userConfig, evals), subagents (prompt + tools + model + memory scope), A2A Agent Card (public identity, skills, security schemes, JWS signature), MCP config (tool servers), SWE-agent YAML (prompt templates + tool bundles + model), DSPy (signature + optimized instructions/demos as saved state). None of them declares a capability budget that a runtime enforces, a price, a memory policy, a signed provenance chain, or a required eval suite as a publish gate.
- Proposal: a **Harness Pack** is a directory (distributed as a content-addressed archive) with one `pack.yaml` manifest on top of existing formats. Reuse as-is: `skills/<name>/SKILL.md` (Agent Skills), `AGENTS.md`, `.mcp.json`, subagent `.md` files, A2A Agent Card (generated from the manifest, not hand-written). Add only what is missing: `capabilities`, `memory`, `model`, `evals`, `commercial`, `provenance`.
- The central design rule: **the manifest is a request, never a grant.** Effective permission = declared capabilities AND requester/owner policy AND mode ceiling (Pull or Hosted). The sandbox enforces the intersection; the pack's own prompt cannot widen it. Anything undeclared is denied by default; at runtime a tool call outside the grant is an event for the active-defense layer, not just an error.
- Packs are **data plus optional code**. Prompt, skills, memory schema, evals are inert data. Code (scripts, MCP servers) exists but only ever executes inside a cell. A pack that needs no code is the "tier 0" pack and gets the easiest approval path (Pull-eligible by default).
- Lifecycle is first class: author -> validate -> eval (with-pack vs no-pack baseline, N runs) -> security eval (exfiltration fixtures) -> sign -> publish (immutable version) -> verified runs feed ranking -> improve (optimizer proposes a new version; it must beat the previous on the same eval gate) -> deprecate/revoke. Every step produces a hash-addressed artifact, so rank, price and trust attach to an exact version.

## Key facts with sources

### Existing formats (what we reuse, what is missing)

1. **Agent Skills (SKILL.md)** [V] https://agentskills.io/specification
   - Directory with required `SKILL.md`; optional `scripts/`, `references/`, `assets/`.
   - Frontmatter: `name` (1-64 chars, lowercase/digits/hyphens, must match directory), `description` (1-1024, what and when), optional `license`, `compatibility` (max 500 chars, env needs), `metadata` (string map), `allowed-tools` (space-separated, experimental, support varies).
   - Progressive disclosure: ~100 tokens of metadata at startup, body (<5000 tokens recommended, <500 lines) on activation, resources on demand. Validator: `skills-ref validate`.
   - Gap: `allowed-tools` is advisory and experimental; no network/filesystem scope, no memory, no price, no signature.

2. **AGENTS.md** [V] https://agents.md/ - plain Markdown "README for agents", no required fields, closest file wins, user chat prompt overrides everything, stewarded by Agentic AI Foundation (Linux Foundation). Gap: instructions only; zero machine-readable policy. Use it as the pack's human-readable operating guide.

3. **Claude Code plugins** [V] https://code.claude.com/docs/en/plugins-reference
   - `.claude-plugin/plugin.json`; only `name` required. Fields incl. `version`, `description`, `author`, `license` (SPDX), `dependencies` (name/marketplace/version), `skills`, `commands`, `agents`, `hooks`, `mcpServers` (path, inline, or `.mcpb`/`.dxt` bundle), `userConfig` (typed prompts, `sensitive: true` goes to secure storage), `experimental.evals`.
   - Standard layout: `skills/`, `agents/`, `commands/`, `hooks/hooks.json`, `.mcp.json`, `bin/`, `settings.json`, `evals/`. Path containment rule: every component path must start with `./`, resolve inside the plugin root and exist; `..` escapes are rejected. `claude plugin validate` lints it; unknown top-level keys are stripped, unknown keys in strict objects are errors.
   - Reuse: containment rule, `userConfig` idea (secrets are injected by the host, never inside the pack), validate-in-CI, and `${PLUGIN_ROOT}` / separate `${PLUGIN_DATA}` (code vs state separation, state survives updates).
   - Gap: a plugin runs with the user's full privileges once enabled; no capability budget.

4. **Claude Code plugin evals** [V] https://code.claude.com/docs/en/plugin-evals - `evals/<case>/prompt.md` + `graders/*.md`; grader types `regex`, `tool_used`, `tool_order`, `file_exists` (free, computed from transcript) and `llm`, `baseline` (judge model); 3 runs per case by default, score = fraction of graders passed, case passes at threshold (default 1.0); every case also runs against a **no-plugin baseline** and reports delta; no custom-code graders; runs in a fresh isolated non-interactive session. Reuse this exact shape: it is the best existing model of "does the harness actually add value".

5. **Subagents** [V] https://code.claude.com/docs/en/sub-agents - Markdown + frontmatter: `name`, `description`, `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, `memory` (`user` | `project` | `local`, directories under `~/.claude/agent-memory/<name>/` etc.), `isolation: worktree`. Subagents do not inherit conversation history or auto memory. Reuse: `maxTurns`, per-agent tool allow/deny, memory scopes, and the principle of an isolated context window.

6. **Claude Code memory** [V] https://code.claude.com/docs/en/memory - CLAUDE.md (human-written instructions) vs auto memory (agent-written notes); auto memory is a `MEMORY.md` index (first 200 lines or 25 KB loaded each session) plus topic files, machine-local. Doc states memory is "context, not enforced configuration"; enforcement needs hooks. Same page says a plugin-root CLAUDE.md is not loaded, so plugin instructions go in skills. Reuse: index + topic-file layout, and the lesson that policy must be enforced outside the prompt.

7. **Anthropic memory tool** [V] https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool - client-side; six commands (view, create, str_replace, insert, delete, rename) on a `/memories` prefix that the host maps to real storage; docs require path-traversal checks, size caps, expiry, and optional stripping of sensitive data before write. This is the template for the pack's memory interface: the pack sees only `/memories/...`, the host decides which store backs it.

8. **OpenClaw skills and ClawHub** [V] https://docs.openclaw.ai/tools/skills , https://docs.openclaw.ai/tools/clawhub
   - SKILL.md with `metadata.openclaw`: `requires.bins/anyBins/env/config`, `os`, `install` specs (brew/go/node/uv/download); precedence workspace > project > personal > managed > bundled; three separate states: inventory, readiness, visibility. Docs say treat third-party skills as untrusted code; `security.installPolicy` runs a policy command before installs; symlinks escaping the root are rejected; "env injection is scoped to the host agent run, not the sandbox".
   - ClawHub: versioned text bundles, publish via `clawhub skill publish`, `--version`, `--changelog`; publishing needs a GitHub account old enough; automated checks may hide flagged releases; install verification checks a "trust envelope" and exits non-zero on failure.
   - Reuse: requires/readiness gating, installPolicy hook, account-age publish gate, version+changelog. Gap: no sandbox-enforced capability manifest.

9. **A2A Agent Card** [V] https://a2a-protocol.org/latest/specification/ - fields: `name`, `description`, `version`, `provider`, `supportedInterfaces[]` (url, protocol, tenant), `capabilities`, `securitySchemes`, `security`, `skills[]`, `extensions[]`, `signature` (JWS over a canonicalized card). Reuse: generate the public listing card from `pack.yaml`; sign with JWS over canonical JSON. (Exact field names for the signature object should be re-checked against the spec before coding. [U] on details beyond what the fetch summary returned.)

10. **MCP** [V] https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization , .../basic/security_best_practices
    - MCP server config is just process or URL; local servers run "with the same privileges as the client"; spec says clients should show the exact command, sandbox local servers with minimal default privileges, and let users grant extra privileges explicitly (directory, network). Remote servers: OAuth 2.1, RFC 9728 metadata, RFC 8707 `resource` binding, token passthrough forbidden, scope minimization (progressive scopes, no wildcard scopes).
    - Reuse: pack MCP servers are declared, never auto-trusted; remote MCP servers must be listed with exact hosts; scopes follow the "minimal initial, step-up on demand" rule.

11. **SWE-agent config** [V, summary only] https://swe-agent.com/latest/config/config/ - YAML with agent templates (system, instance, observation), tool bundles (`tools/registry`, `tools/edit_anthropic`), model settings, environment variables, history processors; multiple config files merge. Reuse: tool **bundles** as the unit of tool packaging, and "layered config files merge" for overlays.

12. **Cursor rules** [V] https://cursor.com/docs/context/rules - `.cursor/rules/*.mdc` with `description`, `globs`, `alwaysApply`; four application modes (always, intelligent, file-scoped, manual); AGENTS.md supported. Reuse: activation modes as a vocabulary for pack instruction fragments.

13. **DSPy** [V] https://raw.githubusercontent.com/stanfordnlp/dspy/main/docs/docs/learn/optimization/optimizers.md , https://raw.githubusercontent.com/stanfordnlp/dspy/main/docs/docs/tutorials/saving/index.md
    - Programs = signatures + modules; optimizers tune demonstrations (BootstrapFewShot, KNNFewShot), instructions (COPRO), both (MIPROv2, SIMBA, GEPA), or weights (BootstrapFinetune).
    - Save state-only as JSON (`save_program=False`, recommended: "safer and readable") vs whole program via cloudpickle (same risks as pickle; load only from trusted sources).
    - Reuse: the **"optimized state is data" principle**. A pack's learned improvements (instructions, few-shot demos) are stored as JSON/Markdown, never pickles. Do not accept pickle or cloudpickle artifacts in packs.

14. **OpenHands microagents** - UNVERIFIED. The docs URL redirected and the repo path returned 404 this session; do not rely on its format. Use only as "keyword-triggered instruction fragments" prior art if re-verified.

15. **Supply-chain provenance** [V] https://docs.sigstore.dev/about/overview/ (cosign, Fulcio short-lived certs, Rekor transparency log, keyless signing), https://slsa.dev/spec/v1.0/provenance (predicate `https://slsa.dev/provenance/v1`: `buildDefinition` {buildType, externalParameters, internalParameters, resolvedDependencies}, `runDetails` {builder.id, metadata, byproducts}; "builder.id is the sole determiner of the SLSA build level"). Reuse: sign the pack digest with Sigstore-style or plain Ed25519; attach a SLSA-shaped provenance statement.

### What this implies

- Instructions, skills, subagent prompts, MCP configs and eval cases already have de-facto formats. We should not invent new ones for them.
- The three things nobody standardizes and our marketplace needs: (a) enforced capability declaration, (b) memory policy, (c) commercial + provenance + eval-gate metadata.
- Memory docs from both Claude Code and the memory tool agree on the same structure (index + topic files, host-controlled path mapping, size caps, expiry). The pack should consume memory only through that interface.

## Fit for agent-bridge

### 1. Pack layout on disk

```
<pack-name>/                         # directory name == manifest name (kebab-case, like Agent Skills)
  pack.yaml                          # the manifest (this file is the only new format)
  AGENTS.md                          # human + agent operating guide (reused)
  prompts/
    system.md                        # base system prompt
    phases/{plan,work,return}.md     # optional per-phase prompts (Rule-of-Two phases from round 1)
  skills/<skill>/SKILL.md (+scripts/ references/ assets/)   # Agent Skills, unmodified
  agents/*.md                        # optional subagent definitions (reused frontmatter)
  mcp/mcp.json                       # MCP servers the pack wants (declared, mediated by the broker)
  tools/                             # optional code: scripts, bundles. Runs only inside a cell
  memory/
    schema.yaml                      # what kinds of memory exist, scopes, retention, redaction rules
    seed/                            # optional seed knowledge (owner-authored, read-only to the task)
  evals/
    cases/<case>/{prompt.md, graders/*.md, case.yaml}       # capability evals, plugin-eval shape
    security/<fixture>/...           # adversarial fixtures: exfil attempts, injected docs, memory-theft probes
    baseline.json                    # recorded no-pack baseline scores per model
  LICENSE
  CHANGELOG.md
  .pack/                             # generated, not hand-edited
    lock.json                        # content hashes of every file + resolved deps (SHA-256)
    card.json                        # generated A2A-style Agent Card (public listing)
    provenance.json                  # SLSA-shaped statement
    signature.sig                    # signature over the pack digest (digest of lock.json)
```

Rules: all paths relative and contained in the pack root (plugin rule, [V] item 3); no symlinks leaving root (OpenClaw rule, [V] item 8); no pickle/cloudpickle/binary blobs outside `assets/` with declared type; file count and size caps (we propose 5 MB text, 50 MB total [U]). State never lives in the pack directory (plugin `${PLUGIN_DATA}` idea): learned memory lives in the host's memory store, so pack updates do not erase it and pack contents stay hash-stable.

### 2. Concrete manifest (`pack.yaml`) [U: our proposal]

```yaml
schema: agent-bridge.pack/1
name: data-analyst                       # kebab-case, unique per publisher
display_name: Data Analyst (pandas + charts)
version: 1.4.0                           # semver; every published version is immutable
publisher: { id: "ed25519:ab12...", handle: "owner-handle", url: "https://..." }
description: Analyses tabular data and returns charts and a short report.   # one sentence for listing
speciality: [data-analysis, csv, charts]
license: Apache-2.0                      # SPDX for the pack content
upstream:                                # honest attribution for reused harnesses
  - { name: mini-swe-agent, ref: "git:<repo>@<sha>", license: MIT }

# ---- what the agent IS ----
entry:
  runner: { type: builtin-loop, version: ">=1" }   # or openclaw / mini-swe-agent / deepagents / claude-code via adapter
  system_prompt: prompts/system.md
  phases: { plan: prompts/phases/plan.md, work: prompts/phases/work.md, return: prompts/phases/return.md }
  skills: [analysis-workflow, chart-style]         # resolved under skills/
  subagents: [verifier]
  mcp: mcp/mcp.json
  limits: { max_steps: 40, max_wall_seconds: 900, max_output_bytes: 1048576, max_model_tokens: 400000 }

# ---- what it WANTS (request, never grant) ----
capabilities:
  fs:
    read:  [{ id: input, path: "$INPUT", mode: ro, why: "analyse the dataset the requester points at" }]
    write: [{ id: scratch, path: "$SCRATCH", max_bytes: 200000000 }, { id: out, path: "$OUT", write_only: true }]
  net:
    egress: []                                     # empty = none. Hosts here must be exact, no wildcards
    model_endpoint: via-broker                     # model calls go only through the key-holding broker
  tools:                                           # tool ids exposed by the broker, not raw shells
    allow: [read_file, list_dir, python_sandbox]
    deny:  [shell, web_search]
  mcp_servers:
    - { id: charts, transport: stdio, runs_in: cell, command_digest: "sha256:...", net: none }
  secrets: []                                      # pack never receives secrets; keys live in the broker
  memory_access: [pack_private.rw, task_scratch.rw, requester_context.none]   # see memory below
  phases:                                          # Rule-of-Two: which capability sets are live per phase
    plan:   [model]
    work:   [model, fs.read.input, tools.python_sandbox]
    return: [model, fs.write.out]
modes:                                             # what the pack supports and its own ceiling
  pull:   { supported: true,  requires_code: true }
  hosted: { supported: true,  accepts_input_classes: [public, low-sensitivity] }

# ---- memory policy (details in the memory topic file) ----
memory:
  schema: memory/schema.yaml
  scopes:
    task_scratch:     { lifetime: task,   storage: cell-tmpfs, exported: false }
    pack_private:     { lifetime: durable, owner: pack-owner,   exported: false, max_bytes: 5000000, ttl_days: 180 }
    requester_context:{ lifetime: grant,  owner: requester,     pack_can_read: by-grant, pack_can_write: false, leaves_machine: never }
  writes: { allow_from: [agent], redact: [secrets, pii], review: owner-approval-for-promotion }
  learning: { promote_to_pack_private: false-by-default, never_from: [requester_context] }

# ---- model requirements ----
model:
  family: [nvidia/nemotron]                        # exact IDs resolved by the runtime, not baked here
  min_context: 128000
  needs: [tool_calling, json_mode]
  tested_on: ["nemotron-3-super-120b-a12b", "nemotron-3-nano-30b-a3b"]   # facts come from eval runs
  fallback: error                                  # never silently swap to a model the evals did not cover

# ---- quality gate ----
evals:
  capability: { dir: evals/cases, runs_per_case: 3, threshold: 0.8, must_beat_baseline_by: 0.15 }
  security:   { dir: evals/security, must_pass: all, runs_per_case: 3 }
  report: .pack/eval-report.json                   # produced by CI, hash-bound into provenance

# ---- commercial ----
commercial:
  pricing: { unit: per_task, currency: USD, amount: 2.50, cap: 5.00, hold_policy: authorize-capture-on-accept }
  refund: { on: [timeout, schema_violation, requester_reject], window_hours: 24 }
  rev_share: { platform_pct: 10 }
  terms_url: https://...

# ---- provenance ----
provenance:
  digest: "sha256:<digest of .pack/lock.json>"
  sbom: .pack/lock.json
  built_by: { builder_id: "https://agent-bridge/builder/v1", source: "git:<repo>@<sha>" }
  signatures: [ { kind: ed25519, key: "ed25519:ab12...", sig: "..." } ]      # + optional Sigstore bundle
  parent: { name: data-analyst, version: 1.3.2, digest: "sha256:..." }       # lineage for improvement lineage
```

Design notes:
- `capabilities` uses **ids and reasons** (`why`) so the approval UI can show a human-readable least-privilege diff between versions. Wildcards are forbidden for hosts, paths and tools; the linter rejects `*`. (Mirrors MCP "no wildcard scopes", [V] item 10.)
- `model` lists requirements and tested models, not a hard model id: Nebius/NVIDIA IDs change, and the eval report is the proof of what was actually tested.
- `modes` lets a pack state it is Pull-capable. A code-bearing pack is only Pull-eligible after the cell policy accepts it; a prompt-only pack is Pull-eligible almost for free.
- `commercial.cap` is the price ceiling the signed quote enforces; the model cannot raise it (round 1 rule).
- `parent` creates a lineage graph used by the improvement loop and by revocation (revoking a digest can cascade to children that did not change the vulnerable part).

### 3. Least privilege: how a pack declares it and is held to it

1. **Declare**: `capabilities` block above; generated `.pack/lock.json` records the exact file set, so the declaration is bound to the code that will run.
2. **Lint at publish**: reject wildcards, undeclared tool references (any `tools/` script that invokes a binary not in `allow`), network hosts not listed, MCP commands without `command_digest`, secrets requested, memory scopes broader than needed, `allowed-tools` in a SKILL.md that exceeds manifest `tools.allow` (the manifest wins, SKILL.md `allowed-tools` is advisory in the spec, [V] item 1).
3. **Negotiate at hire time**: the requester (Pull) or owner (Hosted) sees a **capability card** rendered from the manifest, a diff against the previously approved version, and the mode ceiling. Approval produces a **grant** that is a subset of the request. Pack requests can be tightened but not widened by the grantor.
4. **Enforce below the model**: the cell (container/microVM) mounts only granted paths, has no network except to the broker, and the broker exposes only granted tool ids. The prompt cannot expand this. (Claude Code docs say memory/instructions are "context, not enforced configuration"; enforcement must be a hook/sandbox, [V] item 6.)
5. **Phase-scoped grants**: the manifest declares which capabilities are live per phase (plan has no data, work has data but no network, return has only the output channel). Round-1 Rule-of-Two, now declared rather than hardcoded.
6. **Runtime violation = security event**: any tool call or syscall outside the grant is logged, counted, and sent to the active-defense layer (kill, quarantine, revoke, record), not just returned as an error. The listing's trust score includes violations per 1000 runs.
7. **Step-up, not up-front**: if the agent needs something undeclared, it can only request a **named, pre-declared optional capability** (`capabilities.optional`), which triggers a fresh human approval (MCP step-up pattern, [V] item 10). Undeclared requests are denied.
8. **Version diffs gate updates**: a new version that adds a capability does not auto-upgrade installs; the owner/requester re-approves. Pin by digest, not by tag.

### 4. Lifecycle

| Stage | Action | Artifact produced | Gate |
|---|---|---|---|
| Author | Start from a template (`bridge pack init`), pick a runner, write prompt/skills, import existing harnesses (wshobson/agents, anthropics/skills Apache-2.0 parts, mini-swe-agent configs) via an upstream pin | Source tree | none |
| Validate | `bridge pack validate` (schema, path containment, lint rules, SKILL.md validated with `skills-ref`) | validation report | must pass |
| Evaluate (capability) | Run `evals/cases` with the pack and a **no-pack baseline**, N runs per case, free graders first (regex/tool_used/tool_order/file_exists), judge-model graders only for short outputs (guidance from plugin-evals [V] item 4) | `eval-report.json`, per-model score, delta vs baseline, cost, latency | delta >= `must_beat_baseline_by` |
| Evaluate (security) | Run `evals/security` plus a platform-owned suite of attack fixtures (read ~/.ssh, curl out, memory-theft probes, prompt injection in inputs, poisoned tool results) inside a real cell | `security-report.json` | all must pass; platform suite cannot be edited by the author |
| Package | Build `lock.json`, `card.json`, provenance statement | `.pack/*` | deterministic build (same inputs -> same digest) |
| Sign | Ed25519 (or Sigstore keyless) over the digest; builder id = our platform builder so score and provenance are attached to a known builder (SLSA principle, [V] item 15) | `signature.sig` | publisher identity verified |
| Publish | Registry stores an immutable version + digest; listing is generated from `card.json` | Registry entry | account-age/identity gate (ClawHub-like, [V] item 8), automated scan, then `listed` |
| Operate | Each hire runs under a grant; runs emit receipts (quote id, digest, cell id, model id, tokens, verdict) | Verified-run records | none |
| Rank | Score from verified runs only (see below) | Leaderboard | only accepted+captured runs count |
| Improve | Offline loop: collect failed/rejected runs (with consent, redacted) -> optimizer proposes a new instruction/demo set -> new version with `parent` link -> must pass the same gates and beat parent on the held-out set -> publish | New version | no regression on security suite |
| Deprecate/Revoke | Publisher or platform marks a digest `deprecated` or `revoked`; revocation list is checked at hire time and by running daemons | Revocation record | immediate effect for new runs; running cells killed on `revoked` |

Improvement loop details:
- Prefer **data-only improvements**. DSPy-style optimizers change instructions and few-shot demos (COPRO, MIPROv2, GEPA, BootstrapFewShot) or weights (BootstrapFinetune) ([V] item 13); we restrict the platform optimizer to instructions and demos, store them as Markdown/JSON, and refuse pickle artifacts. Weight tuning is out of scope for packs.
- Train/held-out split is kept by the platform; optimizing on the same cases that gate publishing is overfitting, so gating uses a hidden slice maintained by the platform (UNVERIFIED design choice, but a standard ML hygiene point).
- Agent-written memory that proves useful can be **promoted** into `memory/seed` of the next version only through owner review (memory `learning.promote_to_pack_private`), never automatically from requester-context data.

### 5. Ranking (GitHub-style stars made trustworthy)

- Inputs: verified runs (receipt-bound, only after accept+capture), acceptance rate, eval delta vs baseline on the platform suite, security violations per 1000 runs, median latency and cost, refund/dispute rate, recency, number of distinct requesters (anti-sybil).
- Stars bound to a capture id (round-1 rule), not free clicks. A user can star a version they paid for.
- Score computed per `(pack, version digest, model)`; show confidence interval, not a bare average; new versions inherit a discounted prior from `parent` until they have their own runs.
- Receipts and audit logs are owner-attested in Hosted mode, so ranking must not claim them as proof of isolation; platform-run eval and requester-side acceptance are the stronger signals. In Pull mode the requester machine produces the receipt, which is stronger. (Round-1 flaw carried forward.)

### 6. Agent Card and discovery

- `card.json` is generated from the manifest: name, description, version, provider, skills (from `speciality` and SKILL descriptions), security schemes, our extension block with `pack_digest`, `capabilities_summary`, `modes`, `price`, `model.tested_on`, `eval_summary`, and a JWS signature over the canonicalized card (A2A signing model, [V] item 9).
- Private details (full prompt text, memory seed, scripts) are NOT in the public card. In Hosted mode they stay on the owner machine. In Pull mode the pack must be shipped to the requester, so the pack author must accept that the prompt and scripts are visible to the requester's machine (see Risks: IP exposure).

### 7. Pull vs Hosted consequences for pack design

| Aspect | Pull (pack runs on requester machine) | Hosted (pack runs on owner machine) |
|---|---|---|
| Pack content exposure | Requester machine can read the whole pack (prompt, skills, scripts). Author IP is only protected by license, signing and optional obfuscation of nothing important | Pack stays on owner host; requester sees only results |
| Data exposure | Data stays on requester machine; pack code is the untrusted party inside a sandbox | Requester data is sent to owner machine; owner is root; not solved without TEE (round-1) |
| Capability ceiling | Ceiling set by requester policy; `net.egress` should be empty unless declared and brokered | Ceiling set by owner policy; plus `accepts_input_classes` limit |
| Memory | `requester_context` readable by grant, never leaves machine; `pack_private` must be shipped as a seed snapshot and cannot be updated back to the owner without an explicit upload channel | `pack_private` lives with the owner and keeps learning; `requester_context` is not stored on the owner host beyond the task |
| Updates | Requester pins by digest, updates explicitly | Owner can change harness, so the quote binds the digest and the daemon verifies it |

## Recommendation

1. Adopt **`pack.yaml` + reuse of SKILL.md, AGENTS.md, subagent frontmatter, `.mcp.json`, plugin-eval-shaped `evals/`** as the pack format. Own only: `capabilities`, `memory`, `model`, `evals` gates, `commercial`, `provenance`, plus generated `.pack/` files. Ship a JSON Schema for `pack.yaml` and a `bridge pack validate` CLI (mirrors `claude plugin validate`, `skills-ref validate`).
2. Make **"manifest = request, grant = intersection, enforcement below the model"** the headline design rule, with phase-scoped grants and violations feeding active defense.
3. Treat **eval-as-publish-gate** as the product differentiator: every listing shows delta over a no-pack baseline on the platform suite, per model, plus a security-suite pass. This is the answer to "how do we know a harness is actually better", and gives the leaderboard meaning.
4. Make **improvement a built-in loop** (data-only optimizer, lineage via `parent`, regression-gated, owner-reviewed memory promotion). Do not allow pickles; version immutably; pin by digest.
5. Sign with Ed25519 for the hackathon (libsodium already in the stack); add Sigstore keyless as roadmap. Use our own builder id so provenance has a trust root. Do not claim SLSA levels without a real hardened builder.
6. Build order for the demo (time is not constrained, but order still reduces risk): schema + validator -> three reference packs (prompt-only analyst, code-bearing patcher, adversarial "malicious" pack for security demos) -> eval runner with baseline -> sign/verify -> registry listing from `card.json` -> improvement loop on one pack with a visible version 1.0 -> 1.1 delta.
7. Nebius/NVIDIA fit: `model.family: nvidia/nemotron` with `tested_on` filled from real eval runs makes the model requirement and Nemotron usage visible in the listing. NeMo Guardrails or a Nemotron safety model can serve as an optional **graders/guard** component (security-suite grader, result guard); whether they work as needed is UNVERIFIED here and belongs to the security topic files.

## Risks

- **Pull mode exposes the pack to the requester machine.** Prompt, skills and scripts are readable and copyable. Mitigation is business-level (license, signed provenance, paid-run model for Hosted-only premium packs, optionally split packs into a public Pull-eligible shell plus a Hosted-only "brain"). Do not promise prompt secrecy in Pull mode.
- **Manifest lies.** A pack can declare little and still try to do more. The enforcement point must be the sandbox and broker, never the linter. Lint is defense in depth and developer feedback.
- **Eval gaming and overfitting.** Authors can tune to visible cases. Hidden platform slices, rotating fixtures and model diversity are needed; judge-model graders vary run to run (plugin-eval docs recommend free graders and concrete rubrics, [V] item 4).
- **Instruction vs data confusion.** Packs and inputs are text that steers the model; skill bodies, memory notes and tool outputs can carry injections. Memory/instructions are not enforcement ([V] item 6); guard with phases and result quarantine.
- **Supply chain.** Reused harnesses (GitHub) and their dependencies can be compromised; hence lock files, pinned SHAs, builder-signed provenance, revocation. OpenClaw docs explicitly say third-party skills must be treated as untrusted code ([V] item 8).
- **Code in packs enlarges attack surface.** Tier-0 (no code) vs tier-1 (code in cell) packs should be labelled and ranked separately; consider disallowing code in Hosted-for-sensitive-input classes.
- **Memory leakage via pack-private learning.** If the pack learns from requester data and the owner owns `pack_private`, requester context could leak into the owner's store. The manifest forbids it (`never_from: requester_context`), but enforcement is in the memory broker (another topic file).
- **Spec drift.** Agent Skills `allowed-tools` is experimental; A2A and MCP specs evolve; plugin `evals` is under `experimental`. Pin spec versions in `schema:` and keep adapters thin.
- **Our manifest is a proposal, not a standard.** Field names, limits (5 MB / 50 MB), and eval thresholds are [U] choices to be tuned by spikes.
- Sherpa/screen-tutor is out of scope and not referenced.

## Open questions

1. Should the manifest be YAML (matches SKILL.md frontmatter, easier to author) or JSON with a JSON Schema (matches plugin.json, A2A, easier to canonicalize and sign)? Proposal: author YAML, canonicalize to JSON for hashing/signing.
2. Runner adapter set for v1: builtin loop only, or also OpenClaw, mini-swe-agent, deepagents, Claude Code? Each adapter needs a capability-mapping layer; which one earns first-class support for the Nebius demo?
3. Who runs the platform eval and security suites (central builder vs publisher's machine)? Central runs give trustworthy scores but cost money (Nebius tokens) and need a model budget.
4. Pull-mode distribution of code-bearing packs: do we require an additional reproducible-build / reviewed-by-platform step, or accept sandbox-only trust?
5. Can a pack be split into a public part and a Hosted-only private part, and how does the manifest express the dependency without leaking the private part's contents?
6. How are `capabilities` defaults expressed per input class (public, personal, secret) so the approval UI is one click for low-risk and strict for high-risk?
7. Pricing for Pull mode: the pack runs on the requester's machine, so per-task capture depends on honest receipts. What proof of use is acceptable (requester-side receipt vs owner-side)?
8. Exact A2A signature object and canonicalization rules (re-read spec before implementing), and whether to emit a real A2A card or only borrow fields.
9. OpenHands microagent format and DSPy compiled-program JSON layout: re-verify from repo source before importing or exporting either.
10. Licence compatibility when packs include upstream harness content (MIT, Apache-2.0, source-available skill folders in anthropics/skills that are NOT redistributable per round 1): manifest `upstream` + automated licence check is proposed but unspecified.
11. Is NeMo Guardrails / Nemotron safety model suitable as a pack-level guard layer or only as a platform-level component? (security topic)
12. Should ranking be per model, or per best-tested model with a "works on" matrix?

## Sources

- Agent Skills spec: https://agentskills.io/specification
- AGENTS.md: https://agents.md/
- Claude Code plugin reference: https://code.claude.com/docs/en/plugins-reference
- Claude Code plugin evals: https://code.claude.com/docs/en/plugin-evals
- Claude Code subagents: https://code.claude.com/docs/en/sub-agents
- Claude Code memory: https://code.claude.com/docs/en/memory
- Anthropic memory tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- OpenClaw skills: https://docs.openclaw.ai/tools/skills
- ClawHub: https://docs.openclaw.ai/tools/clawhub
- A2A specification: https://a2a-protocol.org/latest/specification/
- MCP authorization: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- MCP security best practices: https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices
- SWE-agent config: https://swe-agent.com/latest/config/config/
- Cursor rules: https://cursor.com/docs/context/rules
- DSPy optimizers: https://raw.githubusercontent.com/stanfordnlp/dspy/main/docs/docs/learn/optimization/optimizers.md
- DSPy saving: https://raw.githubusercontent.com/stanfordnlp/dspy/main/docs/docs/tutorials/saving/index.md
- Sigstore: https://docs.sigstore.dev/about/overview/
- SLSA provenance: https://slsa.dev/spec/v1.0/provenance
- Internal: .scratch/decisions.md (Pivot, Round 2 input), .scratch/agent-bridge/architecture-options.md
