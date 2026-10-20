# 09 - PayPal for agent-pays-agent (research, 2026-10-07)

## Summary
- The PayPal AI Hackathon (Devpost) explicitly lists "two agents negotiating and settling a payment between themselves (agent-to-agent commerce)" and "a payout tool ... that pays out the moment a task is approved" as inspiration. agent-bridge's marketplace fits this directly.
- Cleanest flow that works in the free sandbox with NO partner approval: **platform as merchant of record (first-party)**. Requester authorizes (hold) -> owner agent runs -> requester accepts -> platform captures -> platform pays the owner via Payouts and keeps a fee. Reject/timeout -> void.
- PayPal's native marketplace features (`platform_fees`, `DELAYED` disbursement, referenced payouts) require being an **approved partner** with sellers onboarded. Do not depend on them for the demo; show them as the production path.
- The official Agent Toolkit / MCP server covers create/get/pay(capture)/refund order but its documented tool list has no authorize, void or payout tool. We must wrap Orders v2 / Payments v2 / Payouts ourselves (thin MCP tools).
- Judges score 5 criteria (below). Hard requirements: public open-source repo with visible license, runnable demo, YouTube video under 3 minutes. Per-prize descriptions for "Most Creative", "Best Demo Delivery", "Best Use of Agentic Commerce" were NOT found on any page I could read (UNVERIFIED beyond the names).

## Key facts (with sources)

### Hackathon
- Submission period: Oct 1 2026 9:15am PDT to **Nov 12 2026 12:00pm PST**; judging Dec 1-15; winners Dec 21. Source: https://paypalaihackathon.devpost.com/details/dates (an aggregator, https://devgrantsdaily.com/items/2026-10-02-paypal-ai-hackathon-2026/, says 2:00 pm PT: treat the Devpost dates page as authoritative, submit a day early).
- Requirements: meaningfully integrate at least one PayPal technology (free sandbox), meaningfully incorporate AI, working prototype, documented. Any AI tool/model allowed "as long as PayPal integration is central". Sponsor tools optional. Sources: https://paypalaihackathon.devpost.com/?ref_feature=challenge&ref_medium=discover, https://paypalaihackathon.devpost.com/details/faqs
- Submission items: text description, tools used and how, **public repo on GitHub/GitLab/Bitbucket with license visible in About**, functional demo (run instructions in repo or hosted URL; mockup/static does not count), **YouTube demo video under 3 minutes showing the project on its target device**, no third-party trademarks or copyrighted music. Same source as above.
- Judging criteria (no weights found): Technological Implementation (how skillfully PayPal platform and AI used; non-trivial), Design (complete coherent product, not just a PoC), Potential Impact (credible, specific real problem/audience), Innovation/Idea (novelty vs existing), Presentation (video shows end-to-end working; clear problem/who/why). Judges are PayPal and sponsor representatives. Same sources.
- Prizes: 1st $12,000, 2nd $8,000, 3rd $5,000; Honorable Mentions $5,000 each: Most Creative, Most Impactful, Best Demo Delivery, Best Use of PayPal + AI, Best Use of Agentic Commerce. One project wins at most one Sponsor Prize plus either one Grand or one Honorable Mention. Sources: https://paypalaihackathon.devpost.com/details/faqs, https://developer.paypal.com/community/blog/PayPal_AI_Hackathon/ (blog page lists 5 honorable mention categories). Eligibility excludes some regions (e.g., Brazil, Quebec); owner is US-based (per HACKATHONS.md), check Section 3 of https://paypalaihackathon.devpost.com/rules (could not fetch: Cloudflare 403/503).
- What the three target prizes reward: **UNVERIFIED** (only the names are public in what I could read). Inference from the criteria and the Resources "Inspiration" text: Best Use of Agentic Commerce = agents that actually transact (not just recommend); Best Demo Delivery = Presentation criterion (end-to-end working video in <3 min); Most Creative = Innovation criterion. Treat as inference.
- Resources page, Inspiration text: "AI agents ... not just recommend, but actually transact ... two agents negotiating and settling a payment between themselves (agent-to-agent commerce)"; Business Solutions: "a marketplace checkout flow that splits payment automatically between a platform and its sellers"; Money movement: "a payout tool ... pays out the moment a task is approved". Source: https://paypalaihackathon.devpost.com/resources
- Sponsor tools: AG Grid, APIMatic, Astropods, Bryntum, Channel3, Elastic, KERNEL, Postman, Render, Zapier (optional). Source: https://ainave.com/events/hackathons/paypal-ai-hackathon (secondary), Devpost page.

### Authorize / capture / void (Orders v2, Payments v2)
- Create order with `intent: AUTHORIZE`; authorize with `POST /v2/checkout/orders/{id}/authorize`. Source: https://developer.paypal.com/docs/api/orders/v2/
- Authorization is a hold valid **29 days**; capture within the **3-day honor period**; multiple reauthorizations allowed in the 29-day window (each gives a new authorization ID and restarts 3 days). Source: https://developer.paypal.com/docs/checkout/standard/customize/authorization/
- `POST /v2/payments/authorizations/{id}/capture` takes optional `amount`, `final_capture` (default false; false allows additional captures), `invoice_id`, `note_to_payer`; `.../void` cancels; `.../reauthorize` re-extends. Source: https://developer.paypal.com/docs/api/payments/v2/
- Capture response includes `seller_receivable_breakdown` (gross, paypal_fee, net). Same source. Idempotency via `PayPal-Request-Id` header (server stores keys 6 hours). Source: Orders v2 page.
- Buyer approval needs the PayPal checkout redirect/JS SDK (`payer-action` link) with a sandbox personal account. Source: Orders v2 page, https://developer.paypal.com/sandbox-testing/accounts

### Payouts
- `POST /v1/payments/payouts` (sandbox `https://api-m.sandbox.paypal.com`), batch up to 15,000 items, recipients by EMAIL/PHONE/PayPal ID, optional Venmo; returns `payout_batch_id` with status PENDING; funded from the sender business account's PayPal balance (fees on top). Sources: https://developer.paypal.com/docs/payouts/standard/integrate-api/, https://developer.paypal.com/payouts/faqs (max $20,000 per payment by default).
- Live use needs "Access to PayPal Payouts" (apply; PayPal emails a decision) plus identity/email/bank confirmation; "in the meantime, you can set up and test your integration in your sandbox accounts". Source: https://developer.paypal.com/limited-release/payouts/integrate/prerequisites
- Sandbox default accounts: one business, one personal; more can be created/cloned. Business sends payouts, personal receives; check balances by logging into the sandbox site. Sources: https://developer.paypal.com/payouts/use-payouts/set-up, https://developer.paypal.com/sandbox-testing/accounts

### Multiparty / partner (marketplace-native path)
- Requires "an approved partner" and onboarded sellers; features gated per seller: `PARTNER_FEE` for `payment_instruction.platform_fees`, `DELAY_FUNDS_DISBURSEMENT` for `disbursement_mode: DELAYED`. Source: https://developer.paypal.com/docs/multiparty/checkout/delayed-disbursement/
- With DELAYED the funds are held, released by a referenced payout (`/v1/payments/referenced-payouts-items`) or auto-released after 28 days. Same source. `payee` selects the receiver of funds. `platform_fees` "only applicable to merchants ... enabled for PayPal Complete Payments Platform"; "Platform fee is not supported for first-party integrations"; partner fees settle daily to the partner's bank account. Sources: https://developer.paypal.com/api/orders/v2/definitions/payment_instruction, https://developer.paypal.com/docs/multiparty/
- Multi-seller order: up to 10 purchase_units, intent must be CAPTURE (so no auth/hold there). Source: https://developer.paypal.com/docs/multiparty/checkout/multiseller-payments/
- Whether a hackathon participant can obtain partner approval/onboarding in sandbox: UNVERIFIED (docs say "test in sandbox before applying for live credentials" at https://developer.paypal.com/docs/multiparty/ but partner credentials need PayPal action).

### Agent tooling
- Agent Toolkit (TypeScript/Python): OpenAI Agents SDK, LangChain, Vercel AI SDK, CrewAI, Amazon Bedrock, MCP. Works with LLM providers supporting function calling. Sources: https://github.com/paypal/agent-toolkit, https://docs.paypal.ai/developer/tools/ai/agent-toolkit-quickstart
- Tool list (README): invoicing, `create_order`, `get_order`, `pay_order`, `create_refund`, `get_refund`, disputes, shipment tracking, catalog, subscriptions, reporting. No authorize/void/payout tools listed. Source: README above; tool reference at https://paypal.gitbook.com/agent-toolkit-and-mcp-server/available-tools (`pay_order` = "Capture payment for an authorized order" per snippet).
- Local MCP: `npx -y @paypal/mcp --tools=all` with `PAYPAL_ACCESS_TOKEN` and `PAYPAL_ENVIRONMENT=SANDBOX`; sandbox tokens last 3-8 hours. Source: https://github.com/paypal/paypal-mcp-server
- Remote MCP: sandbox `https://mcp.sandbox.paypal.com` (`/sse` or `/http`), production `https://mcp.paypal.com`, OAuth login or client-credential bearer. Source: https://docs.paypal.ai/developer/tools/ai/mcp-quickstart
- AP2 (Google-led, PayPal supports): Intent Mandate (human-not-present, pre-approved budget/conditions), Cart Mandate (human-present, merchant+user signed), Payment Mandate; W3C Verifiable Credentials; roles user/agent/credential provider/merchant/issuer; trust via allow-lists. Sources: https://developer.paypal.com/community/blog/PayPal-Agent-Payments-Protocol/, https://github.com/google-agentic-commerce/AP2 (spec still in active development; Python samples exist). No PayPal sandbox endpoint for AP2 mandates found: UNVERIFIED.
- ACP (OpenAI): PayPal announced adoption Oct 28 2025 for ChatGPT checkout of products from merchants. Source: https://newsroom.paypal-corp.com/2025-10-28-OpenAI-and-PayPal-Team-Up-to-Power-Instant-Checkout-and-Agentic-Commerce-in-ChatGPT. It targets merchant product checkout in ChatGPT, not agent-service marketplaces.

## Fit for agent-bridge
Recommended flow ("hold, deliver, accept, capture, payout"), using only sandbox-available pieces:
1. **Listing**: owner publishes price (per task cap, or per hour rate). Platform business sandbox account is the payee.
2. **Quote = AP2-style Cart Mandate (lightweight)**: owner key signs {task type, max price, expiry}; requester key co-signs with an Intent-Mandate-like budget cap. Reuse existing ed25519 identities and audit log. Label it "AP2-inspired", not compliant (AP2 compliance UNVERIFIED in sandbox).
3. **Pre-authorize**: platform creates order `intent=AUTHORIZE` for the cap; requester approves with sandbox personal account (PayPal redirect or SDK, phone-friendly) -> `authorize` -> authorization_id. Task is dispatched only after this succeeds.
4. **Execute** on owner machine; owner previews result (existing decision).
5. **Accept** (requester button, or auto-accept rule) -> `capture` with the actual amount, `final_capture=true`. For per-hour pricing: several partial captures with `final_capture=false`, last one true. **Reject/timeout/owner fails** -> `void` (requester never charged).
6. **Owner payout**: Payouts batch to owner's sandbox email for (captured - platform fee - PayPal fee from `seller_receivable_breakdown`). Platform keeps the fee, so the fee must exceed the PayPal fee.
7. **Reputation hook**: stars/ranking only counted for tasks with a captured payment (verified buyers), which also answers "GitHub-style stars" gaming.
8. Expose steps 3, 5, 6 as MCP tools (`authorize_task_payment`, `capture`, `void`, `payout_owner`) so the Nemotron-via-Nebius agent loop calls them: this satisfies "AI central + PayPal central" and "agent actually transacts". Use the official Agent Toolkit/MCP for `create_order`/`get_order`/`pay_order`/reporting and add our 3 tools; or call REST directly if function-calling compatibility with Nemotron is a problem (Nemotron tool calling through the toolkit: UNVERIFIED).
- Security link: no card/PayPal credentials ever reach agents; only authorization IDs and server-side captures. Escrow-like semantics defend the requester against a bad third-party agent (money moves only on acceptance) while the owner is protected by the hold (funds exist before work starts).

Sandbox-demoable realistically: all of steps 3-6 with the default business + personal accounts plus one extra personal account as owner. Visible proof: sandbox transaction pages and balances (log into https://www.sandbox.paypal.com), webhooks optional (`PAYMENT.AUTHORIZATION.VOIDED`, payouts events, per https://developer.paypal.com/payouts/use-payouts/set-up). Not demoable without partner approval: native `platform_fees` and `DELAYED` seller disbursement (call out as roadmap).

Mapping to prizes: Best Use of Agentic Commerce (agent holds funds, decides capture/void, pays another agent's owner), Best Demo Delivery (<3 min video: phone approves hold -> task runs across two machines -> accept -> sandbox balances visibly change), Most Creative (marketplace of harnesses with verified-purchase stars). Stackable only as one Grand or one Honorable Mention plus one Sponsor prize.

## Recommendation
- Build the first-party platform-as-merchant flow above; keep the module small (4 REST wrappers + webhook + ledger table) and mirror it as MCP tools.
- Start now: create the sandbox accounts (platform business, requester personal, owner personal) and request Payouts access; sandbox testing does not wait on approval.
- Do not spend time on ACP or on a real AP2 integration; mention AP2 mandates as the design reference for signed intent/cart.
- Plan the 3-minute video from the Presentation criterion: show the hold, the void path (rejected result), the capture + payout path, and the sandbox ledger. Fresh public repo with an OSI license in About (also serves the Amazon Open Source mini challenge).
- Submit before the deadline buffer (target Nov 10); fill every submission field (tools used and how).

## Risks
- Authorization honor period is 3 days; long tasks need `reauthorize` (new ID each time). Keep demo tasks short; implement reauthorize for tasks > 3 days.
- Capture is "subject to risk and money availability" even in an authorized state (docs). Sandbox likely lenient; UNVERIFIED for edge cases.
- Capturing an amount different from the authorized amount (over-capture tolerance) is not verified; capture <= authorized cap only.
- Payout needs platform business balance: capture net of PayPal fee lands in it; if fee ordering is wrong the payout can fail. Pre-fund the sandbox business account.
- Platform is merchant of record: real-world this needs money-transmission/KYC/marketplace-compliance review; acknowledge in the pitch, use PayPal partner/multiparty as the production answer.
- PayPal sandbox quirks (token expiry 3-8 h, `PayPal-Request-Id` idempotency) can break live demo; pre-record fallback and use refreshed tokens.
- PayPal community Devpost pages were intermittently 403/503 for direct fetch; prize category descriptions and Official Rules text (Sections 3, 8) were not read directly. Re-read https://paypalaihackathon.devpost.com/rules before submitting (IP, new-vs-existing project rule, reuse across hackathons).
- Deadline time discrepancy (12:00pm PST vs 2:00pm PT in one aggregator).

## Open questions
- Exact Official Rules text on prior-work, team size, open-source license acceptable types, and how "meaningful progress during the period" is judged.
- Any published description or past-winner examples for Best Use of Agentic Commerce / Best Demo Delivery / Most Creative (last year's Dev Days winners blog: https://developer.paypal.com/community/blog/winners-dev-days-hackathon, not yet read).
- Can a hackathon sandbox obtain partner/multiparty credentials (PARTNER_FEE, DELAY_FUNDS_DISBURSEMENT)? Ask in the PayPal Discord.
- Does Payouts work in the sandbox without the live access approval for all recipient types (expected yes per docs, UNVERIFIED by test).
- Does Nemotron (Nebius Token Factory) do reliable function calling against PayPal Agent Toolkit tool schemas?
- Per-hour pricing: metered partial captures vs. fixed-cap tasks only; does multiple capture on one authorization behave as documented in sandbox?
- Venmo/phone payouts as an extra demo flourish (US numbers only per docs).
