# 08 - Business and payment design for Pull and Hosted modes (round 2, 2026-10-07)

## Summary
- Two modes have opposite metering problems. Hosted: the host machine runs the work, so the host can meter and the requester pays. Pull: the pack runs on the REQUESTER machine, so the author cannot observe or meter anything; money must hang on a hub-controlled gate (run token / key release), a license, or an acceptance event, never on the author's word.
- Recommended settlement core for both modes: platform-as-merchant-of-record (first party), Orders v2 `intent=AUTHORIZE` -> capture (partial, `final_capture`) or void -> Payouts to authors/hosts. This is fully demoable in PayPal sandbox. PayPal-native marketplace features (`platform_fees`, DELAYED disbursement, referenced payouts) need partner approval and are the production path.
- Pricing: three price lines kept separate in the signed quote: harness fee (author), compute fee (host, Hosted only), inference pass-through (Nebius tokens at cost), plus a platform fee. Demo uses fixed cap per task. Real product adds subscription/license for Pull packs and metered captures for Hosted hours.
- Pull-mode honesty: once a pack is on the requester disk the author cannot technically stop copying. Protect revenue by run-token gating, signed updates, eval-backed ranking and brand/trust, not by DRM claims.
- Fraud: the main levers are economic (non-refundable fees, minimum price), identity (PayPal payer id on capture), and graph checks on stars. Chargeback window is 180 days, so payouts need a holdback.

## Key facts with sources
### PayPal products (verified from docs this session unless marked)
- Authorize/capture: hold valid 29 days, capture inside 3-day honor period, multiple reauthorizations allowed, each issues a new authorization ID and restarts the 3 days. https://developer.paypal.com/docs/checkout/standard/customize/authorization/
- Payments v2 supports partial captures, multiple captures, final-capture designation, void, reauthorize, and "reauthorization with allowances for amount increases". https://developer.paypal.com/docs/api/payments/v2/ (exact allowance size UNVERIFIED; round 1 note 09 lists `final_capture`, `invoice_id`, `PayPal-Request-Id` idempotency, `seller_receivable_breakdown`).
- Payouts: send to many recipients (96 countries, 24 currencies) by email/phone; needs business account, approved Payouts access, verified identity/email/bank, and balance; Venmo US/USD only, mobile only. https://developer.paypal.com/docs/payouts/standard/ . Sandbox testing without approval: https://developer.paypal.com/limited-release/payouts/integrate/prerequisites (via round 1 note 09; not re-fetched).
- Subscriptions: Product + Plan model, fixed/volume/tiered pricing, trials, plan changes, payment-failure recovery, API or dashboard. https://developer.paypal.com/docs/subscriptions/ . Usage-based (metered) subscription billing: UNVERIFIED.
- Vault / save payment methods: needs Expanded Checkout approval, vaulting enabled in dashboard, Risk Data Acquisition (FraudNet/Magnes); can vault without a transaction ("charge later"). https://developer.paypal.com/docs/checkout/save-payment-methods/ . Sandbox availability of vaulting without that approval: UNVERIFIED.
- Multiparty / platforms: partners can charge `platform_fees`, settled daily to partner bank; fee account cannot hold a balance or sell; "Platform fees aren't supported for first-party integrations"; test in sandbox before applying for live platform approval. https://developer.paypal.com/docs/multiparty/ . DELAYED disbursement and referenced payouts: https://developer.paypal.com/docs/multiparty/checkout/delayed-disbursement/ (from note 09). Multi-seller orders: max 10 purchase_units, CAPTURE only (note 09).
- Disputes: buyer has 180 days to dispute; internal disputes 20 days to resolve then PayPal decides within 10; external = chargebacks / ACH returns; Disputes API exists. https://developer.paypal.com/docs/disputes/
- Agent Toolkit / MCP: Apache-2.0, sandbox default, tools cover invoices, payments (create order, process payment, refunds), disputes, tracking, catalog, subscriptions, reporting; no authorize/void/payout tool listed. https://github.com/paypal/agent-toolkit . Local `npx @paypal/mcp`, remote `https://mcp.sandbox.paypal.com` (note 09, https://docs.paypal.ai/developer/tools/ai/mcp-quickstart).
- AP2: mandates Intent, Cart, Payment; human-present and human-not-present; Python/Go/Android samples; spec active. https://github.com/google-agentic-commerce/AP2 . PayPal sandbox endpoint for mandates: none found, UNVERIFIED.
- ACP (OpenAI) with PayPal: merchant product checkout inside ChatGPT, not agent-service marketplace. https://newsroom.paypal-corp.com/2025-10-28-OpenAI-and-PayPal-Team-Up-to-Power-Instant-Checkout-and-Agentic-Commerce-in-ChatGPT (note 09).
- Hackathon: deadline 2026-11-12; criteria Technological Implementation, Design, Potential Impact, Innovation, Presentation; public repo with license, working demo, YouTube video under 3 min; Devpost main page returned 503 again today, so prize-category text still UNVERIFIED. https://paypalaihackathon.devpost.com/ , https://paypalaihackathon.devpost.com/resources ("a payout tool that pays out the moment a task is approved", "marketplace checkout flow that splits payment between platform and sellers", agent-to-agent settlement).

### Sandbox-demoable vs production-only
| Capability | Sandbox demo | Note |
|---|---|---|
| Orders AUTHORIZE, capture (partial/final), void, reauthorize | Yes | core of both modes |
| Payouts to author/host personal sandbox accounts | Yes (access approval needed only for live) | pre-fund business balance |
| Subscriptions plan + buyer approval | Yes (expected) | metered usage UNVERIFIED |
| Remote/local PayPal MCP | Yes | no authorize/void/payout, wrap ourselves |
| Vault (tokenize, charge later) | UNVERIFIED | needs Expanded Checkout enablement |
| platform_fees, DELAYED disbursement, seller onboarding | Partner approval needed | show as roadmap |
| AP2 mandates | Our own signed AP2-style objects only | not PayPal-processed |
| ACP | No | wrong use case |
| Disputes/chargebacks | Simulation limited, UNVERIFIED | design only |

## Fit for agent-bridge
### Price lines (one signed quote, both modes)
`quote = {pack_hash, mode, harness_fee, compute_fee (Hosted), inference_cap (Nebius pass-through), platform_fee, total_cap, expiry}` co-signed by author/host key and requester key (AP2 Intent/Cart-style, labelled "AP2-inspired"). Cap lives in the signature and in the PayPal hold amount, never only in the model prompt.

### Hosted mode (renter pays compute + harness on owner machine)
- Per task (demo, default): authorize `total_cap`, run, requester accepts or timeout auto-accepts after objective checks, capture actual <= cap with `final_capture=true`, void remainder. Compute fee is captured even on rejected result when the run completed to the declared limits (host spent resources); harness fee is outcome-based.
- Per hour (real): authorize a block (for example 2 hours), partial captures with `final_capture=false` per metering interval, last one true; reauthorize for runs beyond 3 days. Meter = hub-visible signals (sidecar token counts, wall clock heartbeats), still self-attested by the host; requester-side cap and kill switch bound the loss.
- Settlement: capture lands in platform balance; Payouts batch splits to host and author (two recipients when different) after holdback; platform fee must exceed PayPal fee from `seller_receivable_breakdown`.

### Pull mode (pack runs on requester machine, author gets paid)
Options ranked by how well they resist cheating:
1. Run-token gate (recommended core): pack ships signed, prompt/skills encrypted at rest; each run needs a one-time run token from the hub, issued only after a PayPal authorization exists. Hub counts tokens = billable runs. A signed receipt (requester runtime + hub nonce) is the audit record, but it is NOT proof because the requester controls the machine.
2. License/subscription: PayPal Subscriptions plan per pack (monthly) or one-time license order; hub issues short-lived license JWT while subscription ACTIVE (webhook `BILLING.SUBSCRIPTION.*` event names UNVERIFIED here). Best for packs with frequent runs and for the real product.
3. Outcome-based: authorize at start, capture on acceptance. Weakness: requester self-judges, so require objective acceptance checks declared in the pack manifest (tests pass, schema valid, citation count) and auto-capture on pass or timeout.
4. Tips: separate small CAPTURE order after acceptance; cosmetic, optional, feeds author reputation not ranking.
- Honest guarantee: the author cannot see requester data (nothing is sent), and the requester cannot be charged without an authorized hold. Non-guarantee: a requester can extract and reuse the pack offline; revenue relies on token gating, updates, evals, trust.

### Fraud and abuse
- Fake runs / wash trading (author buys own pack to inflate rank): stars and "verified runs" bound to capture ID; ignore captures where payer id equals author/host payee id, same funding source, or same device/IP cluster; minimum price and non-refundable platform fee make washing cost money; weight by distinct payers and payer age; rate-limit per payer per pack. PayPal payer identifiers in capture responses: UNVERIFIED field names, check in sandbox.
- Sybil stars: only paid, captured, accepted runs can star; one star per payer per pack version; stars decay across pack versions; ranking uses eval score from our harness (reproducible benchmark run by the hub) more than stars.
- Refund/reject abuse (take the result, reject, get void): objective acceptance checks, host compute fee always captured on completed run, requester rejection-rate score, deposit or lower cap for new requesters, result released only after capture where feasible (Hosted: hub holds result until accept window ends or accept).
- Chargebacks: 180-day buyer window; holdback on payouts (for example 14-30 days for new authors, shorter for established), reserve percentage, dispute evidence = hash-chained audit + signed quote + run receipts, with the label that host-signed logs are self-attested.
- Fake authors / malicious packs: pack hash and signature, install-time static scan, sandbox, active-defense kill (see topic 1-7 notes); a quarantined pack's pending authorizations are voided automatically and payouts frozen.
- Double-spend / replay: unique quote nonce, `PayPal-Request-Id` idempotency, one capture per run ID in our ledger.

## Recommendation
Demo (PayPal cut, sandbox only):
1. Fixed cap per task in both modes. One Hosted run and one Pull run, same marketplace, same ledger.
2. Flow: signed quote -> phone approval -> Orders AUTHORIZE -> run -> acceptance checks + requester Accept -> partial capture of actual -> Payouts to author (and a second recipient as host in Hosted) -> sandbox balances change; reject path voids in 5 seconds; stolen-context attack scene ends with auto-void and frozen payout (money consequence of active defense, strong demo beat).
3. Expose `authorize_task_payment`, `capture`, `void`, `payout` as MCP tools wrapping REST; official toolkit for reads/reporting. Agent-driven under signed cap.
4. Pull-mode metering shown via run token + receipt, plus one Subscriptions sandbox plan only if time allows (it is cheap, and "time is not a constraint").
5. State on screen what is roadmap: partner `platform_fees`, DELAYED disbursement, metered subscriptions, vault for repeat hires.

Real product:
- Move to PayPal multiparty (partner approval, seller onboarding, `platform_fees`, DELAYED disbursement with referenced payouts) so platform is no longer merchant of record for author/host funds.
- Pull packs: subscription or per-run tokens (author's choice). Hosted: per-hour metered with block authorization. Enterprise: invoiced monthly.
- Platform fee about 10-15% on harness fee, 5-10% on compute; inference passed through at cost; minimum task price to make wash trading unprofitable. These percentages are design proposals, not sourced.
- Reputation: rank by hub-run evals + captured-accepted volume + dispute rate; stars secondary.

## Risks
- Pull mode revenue leakage is inherent; do not market it as DRM.
- Merchant-of-record means money-transmission/KYC/tax exposure in production; multiparty is the answer but needs approval.
- Self-attested metering in Hosted: host can overstate hours; bounded by cap, heartbeats, requester kill switch, reputation.
- Authorization limits (3-day honor, 29-day total) constrain long jobs; sandbox behavior for amount-increasing reauthorization UNVERIFIED.
- Payouts hard to claw back after sent (recall behavior UNVERIFIED); hence holdback.
- Sandbox tokens expire in 3-8 hours (note 09); webhook and token refresh must be robust for live video.
- Devpost rules and prize descriptions unreadable (503); re-read before submitting.
- Teaching judges that "the agent pays" must not mean agents hold credentials: agents see only authorization IDs.

## Open questions
- Does sandbox allow metered/usage-based subscription billing, or must metering be our own partial captures?
- Does the sandbox expose payer id on captures reliably for sybil checks?
- Can a hackathon account get partner/multiparty sandbox credentials?
- Vault in sandbox without Expanded Checkout approval?
- What exactly is the allowed increase on reauthorize and over-capture tolerance?
- Should Pull packs be encrypted at rest (run-token gating) given open-source-by-default expectations of the hackathon repo? A public repo implies the gating code is public; the design must not depend on secrecy of the code.
- Prize text for Best Use of Agentic Commerce / Best Demo Delivery / Most Creative (still unread).
