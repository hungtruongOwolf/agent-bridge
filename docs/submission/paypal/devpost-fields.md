# Agora (PayPal AI): what to paste into each Devpost field

Order on the Devpost page: **About the project** (the story below), **Built with**, **Try it out links**, **Image gallery**, **Video**.
Do these first, once:

1. Make the GitHub repo **public** (images in the story load from it: `raw.githubusercontent.com/.../main/docs/submission/paypal/...`).
   Until it is public the pictures show as broken links.
2. Upload the video to YouTube (public or unlisted) and paste its link in the video field.
3. Replace the one `[YOUTUBE LINK]` in the story.

---

## 1. About the project (paste everything between the two lines)

---
## Inspiration

Someone spends months tuning an AI agent until it is really good at one job, say reading a pile of account notes and saying which customers are about to leave. How do they get paid?

On a normal website that is easy. The work happens on your server, and you keep the door locked until the customer pays.

![The problem: on a normal site you lock the door until they pay. Here there is no door to lock.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/paypal/story/d1-problem.png)

We build a marketplace where the agent runs on the **customer's own computer**, next to their private files, because that is the only way people will let a stranger's agent near their data. But then the work and the result are already on the other side of the door. You can't lock anything. And if builders can't get paid, the best agents never get shared.

So we asked what lever is left. One: **money committed before the work starts.** That is exactly what a PayPal authorization is.

## What it does

**Agora** is a market where anyone can sell an agent (we call it a *helper*) and anyone can hire one without trusting a stranger. PayPal is how the money moves, step by step.

![Hold first. Do the work. Settle by what the run did.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/paypal/story/d2-money-flow.png)

1. **The ceiling.** The buyer asks a question, and PayPal asks them to approve a **hold of 40 cents**: the most this helper can charge. It is approved on PayPal's page. The author never sees the card, only an email for payouts. Nothing has been taken yet.
2. **The work.** The helper runs on the buyer's machine. If it fails or the service has an outage, the hold is released and the buyer pays nothing.
3. **The real price.** When the run finishes, the price is worked out from facts the engine recorded, never from what the helper says about itself. This run read 3 files and made 2 model calls, so it is a *standard* run: **25 cents**. We **capture 25 cents** of the 40 and **release the other 15** back to the buyer. Partial capture is what lets the price be set after the work.
4. **The buyer's call.** If the answer helped, the buyer accepts and the author is paid out through PayPal. If not, they press *Not helpful* and only a small deposit is kept (a quarter of the price; 6 cents here). They can send most of the money back, never all of it.
5. **A full refund needs evidence.** Say a helper cheats and gets shut down mid-run. The buyer can't just say so, because anyone could. The money stays held until the **certifier**, our independent tester, has flagged that helper. If it has, the buyer gets everything back and the author earns nothing. If it hasn't, the claim is rejected and the author keeps the fee.

![Who decides what: the buyer's word moves a little money, only evidence moves all of it.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/paypal/story/d3-decisions.png)

### Authors choose how to charge

Five plans: one flat price; by files read; by thinking used (tokens); by how hard the question was (light 10¢, standard 25¢, deep 40¢, decided from the engine's own journal); or a monthly plan for a set number of answers that never renews by itself and can be stopped. Whatever the plan, the buyer sees the most one answer can cost *before* starting, and the hold is exactly that. Before publishing, authors see what a light, standard or deep run would cost.

![Five ways to charge.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/paypal/story/d4-plans.png)

### What you see in the demo

![Receipts: 25 cents charged out of a 40 cent hold; not helpful keeps only the deposit.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/paypal/gallery/05-receipts.png)

Every answer has a receipt in plain words: *"Standard: 2 thinking steps, 3 files read: 25¢ of the 40¢ hold."* The author's payout shows 23 cents because of a small platform fee. Everything is labelled as test money.

### Verified on PayPal's own sandbox

On 2026-10-30 we ran the whole flow on PayPal's sandbox with the same client the app uses: a hold of 0.40 USD approved by a sandbox buyer on PayPal's page, a partial capture of 0.25, a void of the remaining hold and a Payouts payment of 0.23 to the author. Each object was read back from the sandbox API afterwards (order COMPLETED, capture COMPLETED, authorization VOIDED, payout SUCCESS). The refund path and the in-app approval redirect have so far been exercised on our practice server only.

![The whole flow ran on PayPal's own sandbox; each step read back from the API.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/paypal/story/d5-sandbox.png)

### More in the console

- **Earnings.** A ledger for authors and buyers built on **AG Grid Community** and AG Charts Community: every run with its hold, price, charge, author share, platform fee and what was given back, sortable and filterable, with a bar chart per run.
- **Deal Finder.** A shopping helper that searches product listings through **Channel3** and shortlists three with reasons and links. It reads none of your files and cannot buy anything. Run with no key it uses a small catalog labelled "Recorded product data"; we have not yet made a live Channel3 call.
- **Events for Zapier.** The ledger can send `payment.settled`, `payout.paid`, `payment.refunded` and `dispute.resolved` to a webhook URL (off by default, no private data in the payload). We documented a Zapier "Catch Hook" recipe; we have not yet run it through Zapier itself.
- **A Postman collection** of the PayPal sandbox calls the client makes (token, order, authorize, partial capture, void, refund, payout), not yet run against the live sandbox.
- **A cap on "Not helpful"**: five presses a day per buyer and helper, so the small deposit can't be dodged forever.

## How we built it

- **A ledger with one state machine.** One row per hire: awaiting approval, authorized, running, result ready, settled, rejected, dispute hold, dispute upheld, voided. Every transition is checked under one lock, so *accept* and *kill* can never both win. We tested it with many racing pairs.
- **Idempotency.** Every PayPal call carries a request id derived from the run (`PayPal-Request-Id`), so a lost reply is retried without charging twice.
- **Crash recovery.** A write-ahead intent is saved before each provider call. After a crash, `recover()` finishes the operation exactly once.
- **Three providers behind one interface.** A fake one that can lose replies and decline captures; a **practice PayPal server** that copies PayPal's API (approval page, authorize, capture, void, refund, payouts) and exercises the real client; and a PayPal sandbox client (Orders v2 AUTHORIZE, partial capture with `final_capture: false`, void, refund, Payouts) that refuses any non-sandbox host.
- **Pricing from recorded facts.** The engine keeps a hash-chained journal of each run. Price plans read files handed over, tokens used, model calls and programs run from that journal.
- **The console.** A small pixel-art market floor where each chat is a stall; the approval page tells the console tab, so the chat carries on by itself once the buyer approves.

![Each money step is one PayPal call.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/paypal/gallery/09-paypal-calls.png)

The platform underneath is the open-source **agent-bridge** project (the helper runs in a sealed room with a bounded exit, memory shelves the buyer opens, and a certifier that scores helpers on the same questions with NVIDIA Nemotron on Nebius Token Factory). This submission is about the money.

## Challenges

- **Who may void money?** A kill reported by the buyer must not be able to erase an author's pay, because the buyer could lie. So a kill alone only *holds* the money; a refund needs independent evidence.
- **PayPal wants the buyer's approval first**, so we modelled "waiting for approval" as an explicit state instead of pretending the hold is instant.
- **Setting a price without trusting the helper.** The helper could claim anything about its own work. The price comes only from what the engine recorded.
- **No fair exchange.** On the buyer's machine, a buyer could keep an output without paying. The hold, the small deposit and the certifier limit that loss; they don't remove it, and we say so.

## Accomplishments

- A money state machine that is race-safe, restart-safe and retry-safe. We checked that the payment tests really fail when idempotency or the state guard is removed.
- Money that follows evidence: an honest result is paid, a proven cheat is refunded, an outage costs nothing.
- Five pricing plans, with a preview of what each run would cost before an author publishes.
- The whole money flow run on PayPal's own sandbox (hold, partial capture, void, payout), not only on a practice server.
- A hosted, no-key judge mode: anyone can open the real app and click through the flow with test money (each visitor gets a private copy with a sample history).
- About 730 automated tests across the platform.

## What we learned

When the work runs on the customer's machine, payment design stops being a checkout page and becomes **trust design**. Holds, partial capture and evidence-gated refunds do the job a locked door does on a normal website. And a refund rule that depends on someone's word is a refund rule that depends on a liar.

## What's next

- Run the refund path and the in-app approval redirect on PayPal's own sandbox too (the hold, partial capture, void and payout have already been run there).
- Real holdback and reserve periods; a human adjudicator for disputes the certifier can't reproduce.
- Hosted mode, where the agent runs on someone else's machine, and legal review before any real money.

## Honest limits

All money in this project is **test money**. No real money moves. On PayPal's own sandbox the whole flow has been run with the real client (`tools/sandbox_flow.py`, 2026-10-30): a 0.40 USD hold approved by a sandbox buyer, a partial capture of 0.25, a void of the rest and a Payouts payment of 0.23 to the author, each read back from the sandbox API afterwards. The refund path and the in-app approval redirect have only been exercised on the practice server. The video uses the practice server so it is repeatable. Fees and timings are untuned proposals. Payment edge cases (reauthorization, honor-period limits, seller protection for intangible services) are not covered.

**Demo video:** [YOUTUBE LINK]
---

## 2. Built with (add each as a tag, 25 max)

```
python paypal paypal-rest-api paypal-orders-v2 paypal-payouts javascript html5 css docker json-schema pyyaml cryptography ed25519 nvidia-nemotron nebius-token-factory ag-grid ag-charts channel3 postman render agentic-commerce ai-agents
```

(23 tags, space separated; if Devpost only takes one tag per entry, add them one by one.)

## 3. Try it out links

- `https://github.com/hungtruongOwolf/agent-bridge` (the code, MIT licence, README quickstart)
- `[YOUTUBE LINK]` (the 2:54 demo video)

There is no hosted demo: it runs on the viewer's own machine, which is the point. `pip install -e .`, `bridge seed`, `bridge serve --payments paypal-mock` starts it with the practice PayPal server.

## 4. Image gallery (3:2, upload in this order; the first one is the cover)

All in `docs/submission/paypal/gallery/` (1920 x 1280, all under 1 MB).

| # | File (already numbered in upload order) | What it shows |
|---|---|---|
| 1 | `01-cover.png` | The cover: "Paid per job. Even on your PC." with the 40 → 25 + 15 coins |
| 2 | `02-sandbox-proof.png` | Proof: the whole flow ran on PayPal's own sandbox, each step read back |
| 3 | `03-approve-hold.png` | The real approval card: "Approve a hold of 40¢" |
| 4 | `04-paypal-approval-page.png` | The practice PayPal page: "Pay $0.40 USD, Approve the hold" |
| 5 | `05-receipts.png` | Receipts: 25¢ charged of the 40¢ hold; not helpful = deposit only |
| 6 | `06-earnings.png` | The Earnings ledger (AG Grid) on the hosted demo |
| 7 | `07-hosted-demo.png` | The hosted demo: market floor with sample history |
| 8 | `08-pricing-plans.png` | The Publish panel: plan picker with light / standard / deep prices |
| 9 | `09-paypal-calls.png` | Which PayPal call does each money step |

Select the nine files in the gallery folder (they sort in this order), or add them one at a time in this order. Files in `gallery/unused/` are not for upload.

The story uses different pictures (the five diagrams in `story/`), plus the receipts and the PayPal-calls images again.

Picture captions (same order as the table): 1 "Agora: paid per job, even on the buyer's PC". 2 "The whole flow, run on PayPal's own sandbox". 3 "The buyer approves a hold: the ceiling". 4 "Approval on the (practice) PayPal page". 5 "The receipt: 25¢ of the 40¢ hold". 6 "The Earnings ledger". 7 "The hosted demo with a sample history". 8 "Authors pick a plan". 9 "One PayPal call per money step".
