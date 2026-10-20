# Audit 03: payment and escrow flow (against real PayPal semantics)

Date 2026-10-07. Audited text: architecture-v2.md sections 3.2 B6, 3.4, 5.4, 6.2, 6.3, 7.2, 9, 10 phase 12; research/09, research-v2/08.
Primary sources fetched this session:
- Authorize/capture rules: https://developer.paypal.com/docs/checkout/standard/customize/authorization/ (29-day hold; 3-day honor period; "capture is subject to risk and money availability"; reauthorization creates a NEW authorization id and restarts the 3 days; reauthorization is NOT allowed during the initial 3-day honor period; reauth on day 27 yields only 2 days of honor).
- Payments v2 reference: https://developer.paypal.com/docs/api/payments/v2/ (auth statuses CREATED, CAPTURED, PARTIALLY_CAPTURED, VOIDED, EXPIRED, PENDING; capture statuses PENDING, COMPLETED, DECLINED; capture fields amount, final_capture, invoice_id; refunds within 180 days of capture; PayPal-Request-Id idempotency; error codes REAUTHORIZATION_NOT_ALLOWED, AUTHORIZATION_VOIDED, AUTH_CAPTURE_NOT_ALLOWED).
- Payouts: https://developer.paypal.com/docs/payouts/standard/integrate-api/ (sender_batch_id dedupes; retry after 5xx with same sender_batch_id within 30 days; item statuses incl. UNCLAIMED, FAILED; cross-currency applies conversion fees; the page documents NO recall/reversal of a submitted payout).
Not verified (marked UNVERIFIED below): exact over-capture tolerance, seller protection for intangible services, dispute fees, refund fee retention, unclaimed-payout return period, PayPal ToS on marketplaces, money-transmission law.

## 1. Flow as an explicit state machine

Actors and the state each holds:
- R-Agent / R-UI (requester machine): approval, Accept click, requester device key.
- R-Supervisor (requester machine, requester-controlled): detectors, kill, receipt signer. Adversary-capable toward hub and author in Pull.
- Hub Escrow (AWS): ledger (run state, auth id, captures, payouts), PayPal credentials, run-token issuer.
- PayPal: order, authorization (payer funding source), captures, payout batches.
- Author (pack owner), Host (Hosted only).

Run states (hub ledger, proposed; architecture-v2 has no explicit ledger states):
QUOTED -> ORDER_CREATED -> APPROVED_BY_PAYER -> AUTHORIZED(auth_id, t0) -> TOKEN_ISSUED -> RUNNING -> RESULT_READY -> {ACCEPTED | REJECTED | TIMEOUT | KILLED}
ACCEPTED -> CAPTURED(partial/final) -> HOLDBACK -> PAYOUT_SUBMITTED -> PAYOUT_SETTLED
REJECTED/TIMEOUT -> VOIDED (or partial capture of non-refundable fee)
KILLED -> VOIDED + PAYOUT_FROZEN (architecture-v2 7.2)
Any time after CAPTURED: REFUNDED, DISPUTED (PayPal side, up to 180 days).

Numbered sequence (Pull), with what can go wrong at each step:
1. Quote signed by author key + requester key. Risk: quote nonce replay; currency not fixed.
2. Hub creates order intent=AUTHORIZE. Payer approves in PayPal (redirect). Risk: abandoned approval, order expiry; phone relay approval vs PayPal approval = two separate approvals not distinguished in text.
3. Hub calls authorize -> auth_id. Hub issues run token (6.2 step 3 says both together). Risk: token issued before authorization is confirmed, or authorization voided/failed after token issue.
4. Run on requester machine, hub not in the loop (pack on requester disk). Risk: hub cannot observe, cannot stop, cannot meter.
5. Result Guard, acceptance checks, Accept. Risk: timeouts undefined.
6. Capture (partial/final), holdback, payout, receipt (6.2 step 9).
7. Kill path (7.2): VOID + payout freeze, decided by R-Supervisor.

## 2. Step-by-step failure analysis (failed, repeated, out-of-order, concurrent, timeout, malicious, offline, state-changed)

- Step 2/3: payer approves order but hub crashes before authorize -> order approved, no auth; retry with a new PayPal-Request-Id creates a second order approval flow. Hub must persist intent before every PayPal call.
- Step 3: authorize succeeds but response lost (timeout). Hub retries authorize with same request id (OK within PayPal key lifetime, research/09 says 6 h, UNVERIFIED here) or after 6 h with new key -> authorize on an already authorized order returns an error; must GET order.
- Step 4: run takes longer than 3 days (Hosted per-hour, long multi-step tasks per owner feedback). Honor period ends day 3; reauth only possible after day 3 (docs). Between day 3 and reauth the capture is no longer guaranteed. Reauth may fail with changed funding source.
- Step 5: requester never presses Accept. No timeout, no default, no auto-accept rule in architecture-v2 (only research/08 mentions "auto-accept on pass or timeout"). If the authorization simply lapses at 29 days, the author is unpaid for a delivered result.
- Step 5/6: accept and kill arrive concurrently (supervisor kill while requester clicks Accept; capture call in flight while void is sent). PayPal VOID on a partially captured authorization voids only the remainder; a captured amount stays captured. Nothing in the text orders these.
- Step 6: capture repeated (client retry, hub restart). With final_capture=false a second capture with a new request id is a real second capture, up to the authorization amount.
- Step 6: hub crash after capture, before payout record. Money sits in hub balance; no outbox/reconciliation described.
- Step 6: payout recipient has no PayPal account -> UNCLAIMED; recipient email wrong or hijacked; sanctions screening absent.
- After step 6: dispute/chargeback within 180 days after payout has been sent (payout recall undocumented).
- After step 6: pack later found malicious (new Certifier suite, other requester's incident, revocation): payout already out.
- Hosted: host self-meters and self-attests; host and requester colluding or the same person.

## 3. Findings (ranked; same list returned in structured output)

F1 CRITICAL. In Pull the entity that decides VOID is the requester's own supervisor. The signed incident/receipt is signed by a key on the requester machine, so a requester can fabricate a deterministic D2/D5 "CRITICAL" verdict (or just kill the run after reading the result) and the hub voids the hold and freezes the payout: free work, plus the author is framed. Section 7.3 anti-framing protects reputation only, not money.
Fix: kill-void becomes a DISPUTE state, not a final void. Hub captures a non-refundable minimum fee at AUTHORIZE time (small separate capture); the remainder is held (not voided) pending evidence replay in a Certifier sandbox (deterministic re-execution of recorded model I/O plus canary placement log) or author appeal; per-requester kill/dispute rate feeds a requester risk score (higher deposit, lower caps); result artifacts of a killed run are never released to U or Q until adjudicated. Say in the guarantees text that kill verdicts in Pull are requester-attested.

F2 HIGH. Accept/reject/timeout semantics are undefined, and in Pull the result is already on the requester's disk before any payment decision. Requester reads output, then rejects or never accepts; the authorization is voided or lapses: free use of work. Also acceptance checks (refund.acceptance_checks in the manifest) run on the requester machine, so they are requester-attested.
Fix: define a signed accept window shorter than remaining honor period (for example min(24 h, honor_left - 6 h)); on window expiry with all manifest acceptance checks passing (checks run by supervisor and re-verifiable by hub from the result hash), auto-capture. Rejection requires a reason code from a fixed list and counts toward requester risk score. Separate a non-refundable base fee (compute/Nebius pass-through plus platform fee) captured at result-ready from the outcome-based harness fee.

F3 HIGH. Authorization expiry mechanics are mis-modelled. Docs: capture guaranteed only in the 3-day honor period; reauthorization is not allowed during it; each reauth gives a NEW auth id; capture is "subject to risk and money availability" so a valid authorization can still produce DECLINED. architecture-v2 6.2/6.3 and research/09 treat the hold as a guarantee. Scenarios: task ends day 4 with auth in honor-expired state; reauth fails (funds moved) -> author and host already spent compute; per-hour Hosted blocks > 3 days cannot be reauthorized early.
Fix: (a) before every metering interval and before RESULT_READY, GET the authorization and pause the run if status != CREATED/PARTIALLY_CAPTURED or honor expired; (b) for any task whose declared max duration > 2 days, capture in installments (partial captures with final_capture=false at interval boundaries) instead of one large hold, and schedule reauth at day 3+ with a ledger row linking old and new auth ids; (c) hub treats DECLINED capture as a loss line item and bounds exposure by cap per new requester (deposit or prepaid captured credit for new requesters); (d) max task duration in the quote must be within the honor strategy.

F4 HIGH. Void/capture/kill/accept have no serialization; double capture is possible. Scenario: R clicks Accept (capture request sent) while supervisor fires KILL (void sent). Outcomes include captured-and-frozen payout with no refund path, or void failing after a partial capture (AUTHORIZATION_VOIDED or AUTH_CAPTURE_NOT_ALLOWED errors exist for exactly this). Retried capture with a fresh PayPal-Request-Id and final_capture=false captures twice.
Fix: a single per-run ledger row with compare-and-set state transitions; every PayPal call is preceded by an intent row (outbox) and uses deterministic keys: PayPal-Request-Id = H(run_id, op, seq), capture invoice_id = run_id:seq (DUPLICATE_INVOICE_ID behaviour UNVERIFIED, test in sandbox), final_capture=true on the last capture; allowed transitions table: kill after capture issues a REFUND of captured funds (not void) and freezes the payout; capture after KILLED state is rejected by the ledger before reaching PayPal; reconciler compares ledger vs GET authorization (captures list) every N minutes. PayPal key retention is short (research/09: 6 h), so ledger idempotency, not PayPal's, must be the source of truth.

F5 HIGH. Crash between capture and payout leaves unrecorded money and no recovery. Payout also depends on available business balance (net of PayPal fee from seller_receivable_breakdown), and captures can be PENDING.
Fix: payout is a ledger-driven outbox job with sender_batch_id = H(run_id, recipient) (documented dedupe; retry within 30 days with same id), item sender_item_id likewise; payout only from captures with status COMPLETED; reconciler handles FAILED/UNCLAIMED items; solvency check (balance >= pending payouts + dispute reserve) with alarms; demo runs pre-fund.

F6 HIGH. Holdback and dispute window do not line up, and the demo contradicts the design. research/08 proposes 14-30 days holdback; PayPal buyer dispute/chargeback window is 180 days from capture (refund API window also 180 days). Payout recall is not documented, so a requester who accepts, then disputes, leaves the hub (merchant of record) paying PayPal and the author already paid. Seller protection for intangible AI services is UNVERIFIED and likely weak; PayPal dispute fees UNVERIFIED. Section 9 demo shows payout in the 0:45-1:15 scene while 6.2 says payout "after holdback": contradiction visible to judges.
Fix: rolling reserve: pay out X% after short holdback, withhold Y% until day 180 (tiered by author age/dispute history); evidence pack for disputes: requester-signed quote, requester-signed Accept (bound to PayPal payer_id captured at order approval), result hash, receipt; label the demo "holdback 0 s in demo mode, production default N days" on screen; keep an author-liability clause (author bond or reserve) so disputes net against future earnings.

F7 HIGH. Author paid, pack later malicious: no clawback and no retroactive semantics. Revocation (5.3 step 10) is forward-looking; runs already accepted/captured/paid stay "verified paid completions" in ranking (5.4), and the signed log is append-only so ranking cannot retract them. A malicious pack that passes certification and earns small payouts for weeks is rewarded; requesters who accepted cannot be made whole; accepted-then-leaked data is not fixed by a refund.
Fix: define a Revoke-with-hindsight procedure: ledger flag REVOKED_RETRO sets reserve forfeiture, refunds affected requesters from reserve/hub fund (within 180-day refund window), emits compensating "retraction" entries in the transparency log that the ranking function must apply; authors above a payout threshold need a bond; state in guarantees text that money recovery is bounded by reserve and that data leaked is not recoverable.

F8 HIGH. Payout destination is unbound to author identity. Payouts by email/phone (docs) - an author key (Ed25519) says nothing about whose PayPal it is; account takeover or typo redirects funds; UNCLAIMED when no account; no KYC/sanctions screening for third-party payees; cross-currency payouts apply conversion fees (docs) and are not accounted for in the fee model.
Fix: collect payee via PayPal OAuth (Log in with PayPal, verified payer_id), pay by PayPal ID not email; bind payer_id to author key at registration; destination change triggers 7-14 day cooling period and notifies; screen payees (OFAC lists) before first payout; settle in a single currency (USD) and expose conversion as author-borne; block payout until the account is "verified" per PayPal status where available (field UNVERIFIED).

F9 HIGH (legal, UNVERIFIED). Merchant-of-record exposure. Platform takes payments for third-party services, holds funds up to 29 days, and pays third parties via Payouts; PayPal's terms on marketplaces/platforms, money-transmission licensing (US FinCEN/state, EU PSD2) and the payment-processor exemption, sales tax/VAT on digital services, tax reporting (1099-K and similar), refund consumer-law, and sanctions are all unresearched here (the web search this session returned only old SEC-filed PayPal agreements, so nothing current is verified). research/09 says to "acknowledge in the pitch" - that is not an analysis. Also multiparty path needs partner approval (UNVERIFIED obtainable).
Fix: demo is sandbox/test money only with an on-screen label; production plan states multiparty (payee = author, DELAYED disbursement) and requires counsel review before any live funds; open item in section 11 list "payments production path" must be promoted to a blocking decision; do not claim "escrow" (legal term) - call it "payment hold".

F10 MEDIUM. Wash trading is cheap and the countermeasures are partly infeasible. Author funds a second PayPal account, buys own pack at price P, receives P minus platform fee minus PayPal fee: net cost is fees only (roughly 10-20% by the proposals, which are unsourced). "Same funding source / device cluster" checks (research/08) rely on fields PayPal may not expose (UNVERIFIED). Ranking counts "verified paid completions" at capture, but refunds and disputes later change reality while the log is append-only.
Fix: ranking counts a completion only after the dispute reserve period or with weight growing over time; payer-diversity requires distinct verified payer_id with age and prior history; cap per payer per pack per window; completions from payers with a payee/author link are zero-weighted; rank mainly on Certifier LCB (already primary) and treat paid volume as a log-scaled tiebreaker; retraction entries on refund/dispute.

F11 MEDIUM. Receipt: who signs and what it proves are unspecified, and its fields contradict the covert-channel rule. 3.4 says receipt is supervisor-generated and signed, with a "cost" field and token-count bucket; exact cost is a deterministic function of tokens, so it leaks finer counts than buckets (contradiction with "Forbidden: any counts finer than buckets"). In Pull the supervisor key lives on the requester machine, so the receipt is requester-attested; in Hosted, host-attested; neither is a proof for PayPal disputes. Hub countersignature is only meaningful for things the hub observed (auth, capture, token issue).
Fix: two-part receipt: (a) hub-signed payment receipt (auth id hash, capture ids, amounts, run token nonce, state) and (b) supervisor-signed run summary labelled attestor=requester|host; cost reported as price-tier enum or bucketed; author-bound copy contains only (a)+(b) enums. Rating binds to capture id via hub-issued single-use rating token.

F12 MEDIUM. Pull payment gating is cooperative only, so "metering anchor" (6.2 step 3) is overstated. The pack is on the requester disk, license tier may be Apache-2.0/open, and the supervisor enforcing the run token is requester-controlled: anyone can run the pack directly with no token and no payment. Escrow therefore only protects requesters who choose to pay; it provides no revenue guarantee to the author, and wash-trading/kill-abuse (F1, F10) apply on top.
Fix: state this plainly in 6.2 and in the author-facing listing; bind what the requester pays for to things that need the hub (certification attestation for the digest + model, revocation checks, signed updates, support, per-run decryption key for non-open tiers with the stated caveat that a decrypted copy can be retained); do not describe the token as metering.

## 4. Smaller items

- Currency: no currency fixed in quote; PayPal currency conversion on payer side and payout conversion fees; fix USD only for v1.
- Fees: PayPal charges a percentage plus a fixed component on small transactions (exact current rates UNVERIFIED here); for $4 runs the fixed component matters; refund may not return original fees (UNVERIFIED); model fees in the quote and set a minimum price.
- Over-capture: do not exceed authorized amount; tolerance UNVERIFIED.
- Token expiry: sandbox tokens 3-8 h (research/09); server must refresh OAuth token before each call, not rely on a pre-minted token for background jobs (reconciler, auto-capture).
- Webhooks (PAYMENT.AUTHORIZATION.VOIDED, capture, payout events) must be verified and are untrusted ordering-wise; treat as hints and re-GET.
- Hosted split capture: one authorization, payouts to two recipients; host-meter inflation and requester=host collusion; compute fee captured on host-attested completion invites fake runs. Fix: cap per host per new requester, canary spot checks (already proposed) tied to payout holdback, hold host payouts to the same reserve rules.
- Consistency: 7.2 says "payout freeze" and "slash only after second detector"; ledger needs both FROZEN and SLASHED states and an appeal clock; 6.2 step 9 says "partial/final capture" but never says which partial captures are allowed before acceptance.
- Free packs (price 0): no authorization, so ranking by paid completion excludes them (open decision 14) and kill/void machinery is a no-op; state it.
