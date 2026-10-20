# 13 Gap fill: completeness critique of research 01-12

Date: 2026-10-07. Method: read the 12 digests, then verified gaps against primary sources (Docker docs, Microsoft Learn, Nebius Token Factory docs, A2A spec, OpenClaw repo cloned to scratchpad at depth 1, PayPal developer search). Devpost rule pages for all three hackathons still return HTTP 503 (checked 2026-10-07 via curl), so hackathon rules remain UNVERIFIED.

## Summary

Three findings change the plan, the rest are refinements.

1. **Docker Desktop does not officially support Windows 11 Home.** Research 05 recommends "Docker (WSL2 backend on Windows Home)". Docker's current requirements list only Enterprise, Pro or Education for both the WSL 2 and Hyper-V backends. The owner machine is Windows 11 Home. Practical fallback: install Docker Engine inside a WSL2 Ubuntu distro (systemd is supported by WSL), or run the sandbox host on a Linux box or AWS EC2. This must be a day-1 spike, not an assumption.
2. **The "two real machines" demo plus OpenClaw Fleet is Linux/macOS only.** OpenClaw's own Fleet doc says Windows is untested, and Docker-internal networks break Fleet's published loopback port, so deny-egress must be done via host firewall (DOCKER-USER chain) or Podman `--network internal`. The cheap path is: our own sandbox launcher (docker run with `--network none` or an internal network plus a model-proxy sidecar) rather than driving `openclaw fleet`.
3. **The combined scope is too large for 23 days to Nebius (30/10) and 36 days to PayPal (12/11)** if every digest's recommendation is followed (OpenClaw plugin + ClawHub fork on Convex + Pixi floor + relay + Noise + PayPal + Alexa MCP + voice + two listing modes + eval badge). A scoped cut list is at the end.

## Key facts (with sources)

### Unverified, contradictory or over-optimistic claims found

| Claim in digests | Problem | Evidence |
|---|---|---|
| 05: "disposable Docker (WSL2 backend on Windows Home)" | Docker Desktop requirements list no Home edition for Windows 11. Home can only run Linux containers if it runs at all. | https://docs.docker.com/desktop/setup/install/windows-install/ (System requirements: "Windows 11 64-bit: Enterprise, Pro, or Education version 23H2"; "Windows Home or Education editions only allow you to run Linux containers") |
| 01: plugin can launch per-task Fleet cells | Fleet is a host-side CLI supervisor; Fleet's `--runtime` only picks docker or podman; it targets multi-tenant gateways, not per-task job cells; Windows untested; egress unrestricted by default | OpenClaw repo `docs/gateway/multi-tenant-hosting.md` (cloned 2026-10-07) |
| 01/05: "egress allowlist" via Fleet | Fleet rejects Docker `--network internal` because it breaks the loopback-published Gateway port. Docker egress must use host firewall rules. Only Podman cells can use internal networks. | same file |
| 12: fork ClawHub (TanStack Start + Convex + OpenAI embeddings) in 3 weeks | Adds Convex backend, GitHub OAuth and an embeddings dependency (OpenAI) that conflicts with the Nebius-only story; Convex needs its own cloud/self-host. Time cost is not estimated anywhere. | digest 12 (ClawHub stack); not re-verified by build |
| 08: "~300-line WSS relay" | Optimistic. Needs signed-nonce auth, per-recipient TTL queue, reconnect, replay protection, backpressure, plus an ALB/WebSocket deployment. Realistic 2-3 days with tests. | digest 08 own risks list |
| 09: Payouts via sandbox | Sandbox default has one business and one personal account; business sends payouts, personal receives. Production needs funded balance and identity checks. Sandbox payout of a captured-then-paid-out flow is plausible but still not shown by anyone to work with a platform business account that received a capture. Treat as to-be-tested. | https://developer.paypal.com/payouts/use-payouts/set-up ; https://developer.paypal.com/docs/payouts/standard/ (search snippets) |
| 10/04: "Nemotron on Nebius handles tool calling" | Nebius function-calling doc has a single example model (`meta-llama/Meta-Llama-3.1-8B-Instruct-fast`) and does not list which models support tools, nor parallel calls or reasoning-model caveats. Still UNVERIFIED for Nemotron. | https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling.md |
| 11: Alexa+ MCP 500 ms round trip | Fine for a thin async `delegate_task` returning a task id; incompatible with synchronous long tasks. Already flagged, but implies the Amazon deliverable needs the async task API to exist first (dependency on core). | digest 11 |
| 02/03: reuse of PersonalJarvis and munder-difflin alongside OpenClaw | Three large upstreams, each Alpha or fast-moving. Total integration surface is bigger than the build-it-ourselves surface for the parts we actually use. | digests 01-03 |
| 10: hackathon requires an open-source license of Apache-2.0, MIT or MPL-2.0 | Only from a third-party blog (digest says UNVERIFIED). Choosing Apache-2.0 satisfies all three plausible rule sets (see licensing). | digest 10 |

### Gap 1: Nebius data handling, rate limits, region (cost and privacy)

- Zero Data Retention (ZDR) is an **organization-level** setting enabled on the account profile page, not per request. With ZDR off (default), prompts and outputs are retained for speculative decoding; content is not used for training in either mode. Source: https://docs.tokenfactory.nebius.com/legal/legal-quick-guide.md (sections 3.3, 4.1, 4.2). This answers open question in 05. It means: for the demo, turn ZDR on in the org that holds the key; and the requester-privacy claim must still say "the model provider sees prompts".
- Public serverless endpoints process in "Global" region decided dynamically, with no region guarantee; dedicated endpoints give a fixed region. Source: https://docs.tokenfactory.nebius.com/public-serverless.md. Relevant to any claim about data residency; do not claim it.
- Rate limits: baseline in the docs example is 60 RPM and 400K TPM, scales x1.2 per 15-minute window at >=80% usage, scales down by 1/3 when <=50%, ceiling 20x, and response headers (`x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`, `Retry-After`, `x-ratelimit-over-limit`) expose headroom. A Batch API has significantly higher limits. Source: https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md. Implication for a long multi-step demo: a cold account starts at the baseline, so warm up ahead of recording, honor `Retry-After` in the runtime, and cap parallel agent calls (planner/worker/returner split multiplies calls).
- Pricing and per-model limits: the price page (https://tokenfactory.nebius.com/organization/prices) is a client-rendered app and returned no data; `GET /v1/models` returns HTTP 401 without a key (checked). So per-model price, context and tool support remain UNVERIFIED until the owner calls `GET /v1/models?verbose=true` with the key. This is a day-1 action item.

### Gap 2: Task-spec format and long-running task state (nobody specified it)

- A2A task lifecycle: interrupted states `input-required` and `auth-required`; terminal states `completed`, `canceled`, `rejected`, `failed`; a terminal task cannot restart, a follow-up must be a new task in the same `contextId`. Agents may be message-only, task-generating or hybrid (messages for negotiation, tasks for committed work). Source: https://a2a-protocol.org/latest/topics/life-of-a-task/.
- A2A long-running mechanisms: `SendStreamingMessage` (stream starts with a Task or Message, then status and artifact updates, ends at a terminal state), `SubscribeToTask` (current state, then updates; the reconnect path), push-notification webhooks via `CreatePushNotificationConfig` (requires `capabilities.pushNotifications: true`). Message and artifact Parts are text, file or data (JSON). `CancelTask` must return `TaskNotCancelableError` for terminal tasks. Source: https://a2a-protocol.org/latest/specification/ (summarised by fetch tool; wording not quoted verbatim).
- Contrast with OpenClaw's own A2A channel: text only, no streaming, no files, CancelTask refused (digest 01). So "reuse OpenClaw A2A" cannot carry structured task specs or progress. Either use the official A2A SDK on our relay, or define our own envelope inside A2A data Parts.
- OpenClaw run semantics (our owner runtime if used): agent runtime timeout default 172800 s (48 h), progress does not reset it, `0` means unlimited; `agent.wait` defaults to 30 s and does not stop the run; queued runs report `pending`. Source: repo `docs/concepts/agent-loop.md`. For the marketplace, set a short per-listing timeout (for example 10-30 min) explicitly.
- Proposed minimal task envelope (our design, not a standard): `{task_id, context_id, listing_id, pack_hash, quote{price,currency,cap,expires,sig}, spec{goal, inputs[refs], constraints{max_steps,max_seconds,max_tokens,egress_allow[]}, output_schema(JSON Schema)}, requester_sig}`. State machine: `submitted -> quoted -> authorized(hold) -> approved(owner) -> running -> input-required* -> result-preview -> accepted|rejected|expired -> captured|voided`. Map onto A2A states, carry price and payment states as extension metadata. The `output_schema` is also the control for the Rule-of-Two returner (schema-validated result).
- Progress and resumption: use streaming with `SubscribeToTask` semantics over the relay; persist state on the relay (task id, state, last event id) so a phone or a reconnecting client can resume. This is also what the observability UI consumes.

### Gap 3: Result preview UX and approval fatigue

- No digest defines what the owner or requester sees. Required screens, derived from the threat docs already read (05, 06, 12): (a) owner-side: requester identity and stars, task goal, the granted folder listing, declared tool set, price, time and step caps, Approve/Deny; (b) owner-side result preview: diff-style view of exactly the bytes that will be returned, with the schema validation result and any redaction flags, plus Return/Edit/Block; (c) requester-side: "what leaves your machine" preview before sending (Presidio-style redaction highlights) and a final accept/reject which triggers capture or void.
- Approval-fatigue and phishing risk of the phone page (digest 12) needs: show price, scope and requester key fingerprint on one screen; require the phone's device key; never approve from voice (already decided).
- The existing UI references (munder-difflin `BlockedBanner` approve/deny, 76 lines; `ToolWaterfall`) cover only the in-run view, not the result preview. Result preview must be new work (budget about 1 day).

### Gap 4: Cost control (budgets, runaway loops)

- Nobody specified a cost control. Ingredients that exist: Nebius rate-limit headers (above), OpenClaw `/usage cost` and `/status` (local cost summary from session logs, estimated cost for API-key models; source repo `docs/concepts/usage-tracking.md`), munder-difflin cost circuit breaker (digest 03, Claude-centric pricing).
- Design: per-task token and step budget enforced by the model-proxy sidecar (the same component that holds the Nebius key outside the sandbox), so a malicious or looping harness cannot exceed it. Proxy returns 429 at cap and emits a `usage` event to the UI. Owner's price must exceed the Nebius cost estimate plus PayPal fee; the price-versus-cost margin is a real marketplace issue and should be shown in the owner listing form. Nemotron prices are UNVERIFIED (need key).
- Per-hour pricing: PayPal's 3-day honor period and reauthorization (digest 09) make true per-hour metering awkward. Recommendation: quote per task with a hard cap and a time budget; show "per hour" only as a display unit converted to a cap. Cut metered partial captures.

### Gap 5: Windows specifics (owner machine is Windows 11 Home)

- Docker Desktop: not supported on Home per Docker requirements (see table). Docker Desktop is also licensed free only for personal use, non-commercial open source, education, or businesses under 250 employees and under US$10M revenue; individuals in a hackathon qualify. Sources: https://docs.docker.com/desktop/setup/install/windows-install/ and https://www.docker.com/legal/docker-subscription-service-agreement/ (search summary; not read in full).
- WSL2 itself installs on Windows 11 with `wsl --install`; no edition restriction stated on the install page. systemd inside WSL is supported on recent Store-version WSL (`/etc/wsl.conf` `systemd=true`). Sources: https://learn.microsoft.com/en-us/windows/wsl/install and https://learn.microsoft.com/en-us/windows/wsl/systemd. So "Docker Engine (apt) inside Ubuntu on WSL2" is the likely Home-compatible route. UNVERIFIED by running; it is also still one shared WSL VM kernel (digest 05), so isolation strength equals ordinary Docker.
- OpenClaw native Windows: installs via `iwr -useb https://openclaw.ai/install.ps1 | iex`; Gateway runs as a Scheduled Task (S4U principal); a native WinUI "Windows Hub" companion exists. Source: repo `docs/platforms/windows.md`. So the OpenClaw runtime is fine on Windows; only the Fleet and container sandbox part is the problem.
- Practical decision: make the **owner worker a Linux machine** (a small AWS EC2 instance, an old laptop, or WSL2 Ubuntu) and keep the Windows machine as the requester and UI. This also helps the AWS Builder hosting story. The "two real machines (any OS)" decision in decisions.md stays satisfied.

### Gap 6: Licensing conflicts when reusing repos

(Facts about each license taken from the digests; license texts not re-fetched except where stated.)

| Component | License (per digest) | Constraint / conflict |
|---|---|---|
| OpenClaw, ClawHub, munder-difflin source, wshobson/agents, mini-swe-agent, deepagents | MIT | Keep copyright and license notice. No conflict with an Apache-2.0 repo. |
| PersonalJarvis 2.x | Apache-2.0 | Ship LICENSE and NOTICE, mark modified files; trademark carved out. Compatible if we license Apache-2.0. If we copy 1.x code it is MIT. |
| anthropics/skills | Mixed: many Apache-2.0, docx/pdf/pptx/xlsx source-available only | Do not vendor the four source-available skills. |
| awesome-claude-code (NOASSERTION), ComposioHQ awesome-claude-skills (no license) | Unclear or none | Do not copy content. Link only. |
| munder-difflin bundled LimeZu tilesets | Separate license: credit to limezu.itch.io, no redistribution beyond the app | **Cannot be committed to our public repo or served from our web UI** (that is redistribution). Use the MIT procedural sprites only, or draw our own. |
| Parakeet model | CC-BY-4.0 (digest 02) | Attribution only. Silero VAD and Smart Turn model licenses UNVERIFIED. |
| Presidio, NATS, @noble/curves | MIT / Apache-2.0 / MIT (digests) | Fine. |

- Recommended repo license: **Apache-2.0** (patent grant, compatible with MIT inputs, within the Apache/MIT/MPL list reported for Nebius, and OSI-approved for PayPal and Amazon). Add a `NOTICE` file listing every vendored component, upstream URL, commit SHA and license. This is a standard Apache-2.0 requirement; the license text itself was not re-fetched here.
- Hackathon "new work during the period" rules: unverified (Devpost down). A repo that mostly vendors OpenClaw could be judged as a wrapper (digest 01 risk). Mitigation: keep upstream code out of the repo (depend on pinned releases, no fork), so the repo history shows only our new code.
- "Open Source" mini challenge wording (contribution upstream vs new licensed repo) still UNVERIFIED; a small upstream PR to OpenClaw or ClawHub (docs or a plugin example) is cheap insurance.

### Gap 7: Hackathon rules still unread

- Nebius, PayPal and Amazon Devpost pages (`/rules`, home) all returned 503 on 2026-10-07 (curl). All rule-dependent claims in digests 09, 10, 11 stay UNVERIFIED. Action: retry daily; save the rules text into the repo the moment the pages return; check specifically: hosted demo URL requirement, reuse across hackathons, team and prior-work rules, mini-challenge definitions.

## Fit for agent-bridge

- The strongest verified building blocks: A2A task lifecycle and long-running semantics (gap 2), OpenClaw as owner runtime on Linux or Windows (gap 5), Nebius OpenAI-compatible endpoint with ZDR available (gap 1), PayPal sandbox with default business and personal accounts (gap 1 of table).
- The weakest verified links: container sandbox on the owner's Windows Home machine, Nemotron tool calling on Nebius, Fleet as a per-task launcher, ClawHub fork cost, Payouts in sandbox, all hackathon rules.

## Recommendation

Day-1 to day-2 spikes (each has a binary outcome; decide by 2026-10-09):

1. Call `GET /v1/models?verbose=true` on Nebius; run a 3-tool agent loop with `nemotron-3-super-120b-a12b`, `Nemotron-3_5-Lightning` and `Nemotron-3-Nano-30B-A3B`; record tool-call success rate, latency, price. Turn ZDR on.
2. Decide the sandbox host: try Docker Engine in WSL2 Ubuntu on the Home machine; if it fails within 2 hours, use a Linux box or EC2 as the owner worker.
3. Own thin sandbox launcher (docker run, read-only mount of one folder, internal network or `--network none`, model-proxy sidecar holding the Nebius key and enforcing token and step budgets) in place of driving Fleet.
4. PayPal sandbox: authorize, capture, then payout to the owner account end to end with REST calls; verify the payout works with the platform business account balance.

Scope cuts to protect quality (the user wants polish over breadth):

- Cut: ClawHub fork (build a 5-8 listing page of our own, static plus small DB), Pixi office floor (use a node graph plus envelope animation, or 2-3 reused MIT React components), voice, per-hour metering, eval badge, Alexa+ unless core demo works by 2026-10-16, Pack mode as a second implementation (describe it as roadmap; keep one execution mode: Hosted with sandbox).
- Keep: relay, task envelope and state machine, owner approval plus result preview, sandbox with attack theater, PayPal hold/capture/void/payout, stars bound to captured payments, observability view fed by one event stream, Apache-2.0 repo with NOTICE.
- Proposed order: week 1 spikes, relay, task state machine, sandbox runner; week 2 owner and requester UI plus preview, PayPal flow, Nebius submission build; Nebius submission by 2026-10-28 (2 days margin); week 4-5 PayPal polish, demo video, Amazon only if cheap.

## Risks

- Sandbox isolation unproven on the demo OS; the headline security claim depends on it.
- Nemotron tool-calling and rate limits unverified; a cold account is throttled.
- Hackathon rules unreadable; any of the rule-dependent assumptions could be wrong (hosted demo URL, reuse, license list).
- Scope: the sum of the digest recommendations exceeds 23 days for one person with AI help.
- Reusing LimeZu art would violate its license if redistributed.
- Per-hour pricing conflicts with the PayPal honor-period model.
- Gap-fill sources that were summarized by the fetch tool (A2A spec, Docker FAQ, PayPal search snippets) may omit caveats; the Docker requirement lines were confirmed against raw page text.

## Open questions

- Does Docker Engine in WSL2 Ubuntu run on the owner's Windows 11 Home machine with `--network none` and a mounted read-only folder? (UNVERIFIED)
- Does PayPal sandbox allow a Payout from a business account that just received a capture, and does the platform's balance reflect it?
- Which Nebius Nemotron model IDs exist now and support tools? Price, context, limits (need key).
- Does ZDR require a plan or approval on a trial or hackathon-credit account? The guide says it is activated on the account profile page; trial restrictions not stated.
- Do any Devpost rules forbid or restrict a repo whose core runtime is an existing project (OpenClaw)?
- Should the requester also need an OpenClaw install, or only our thin client plus MCP server?
- Is A2A official SDK usable over our relay transport (no HTTP endpoint on the owner side)? Still UNVERIFIED (digest 07).

## Sources

- https://docs.docker.com/desktop/setup/install/windows-install/
- https://www.docker.com/legal/docker-subscription-service-agreement/
- https://learn.microsoft.com/en-us/windows/wsl/install
- https://learn.microsoft.com/en-us/windows/wsl/systemd
- https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling.md
- https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md
- https://docs.tokenfactory.nebius.com/public-serverless.md
- https://docs.tokenfactory.nebius.com/legal/legal-quick-guide.md
- https://docs.tokenfactory.nebius.com/llms.txt
- https://a2a-protocol.org/latest/topics/life-of-a-task/
- https://a2a-protocol.org/latest/specification/
- https://developer.paypal.com/payouts/use-payouts/set-up
- https://developer.paypal.com/docs/payouts/standard/
- OpenClaw repo (cloned 2026-10-07): docs/gateway/multi-tenant-hosting.md, docs/platforms/windows.md, docs/concepts/agent-loop.md, docs/concepts/usage-tracking.md
