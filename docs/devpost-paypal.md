# Devpost text: PayPal AI (Agentic Commerce)

Project name: **Agora** (a marketplace where anyone can sell an agent and be paid per job). Paste each section into the matching Devpost field.
Fill the [bracketed] items yourself. Read the official rules once more before submitting.

## Tagline

A market for agents, paid per job on the buyer's machine.

## Built on

The open-source agent-bridge platform ([REPO LINK], MIT). This submission is about the money.

## Honest disclosure (put near the top of the description)

All payments are **test money**. The ledger and every money flow run against an in-memory provider and a local **practice PayPal server** that
copies PayPal's API (approval page, authorize, capture, void, refund, payouts) and exercises the real client code. A PayPal sandbox client
(Orders v2 authorize, partial capture, void, refund, Payouts) is included. [CHOOSE ONE BEFORE SUBMITTING: "It has been run against the live
PayPal sandbox, see the video." OR "It has not yet been run against the live PayPal sandbox; the video uses the practice server."] No real money moves.

## Requirements checklist

| Requirement | Where it is met |
|---|---|
| Public repo with an OSI licence | [REPO LINK], MIT |
| Video under 3 minutes | [YOUTUBE LINK] (2:54) |
| Working demo or test build | `bridge seed`, `bridge serve` (README quickstart); payments with `--payments paypal-mock` |
| PayPal used | `src/bridge/payments/paypal.py` (client), `src/bridge/payments/ledger.py` (flows) [adjust to the choice above] |

## Inspiration

Someone spends months tuning an AI agent until it is really good at one job. How do they get paid? On a normal website that is easy: the work
happens on your server and you keep the door locked until the customer pays. In our marketplace the agent runs on the customer's own computer,
next to their private files, so the work and the result are already on the other side of the door. Nothing can be locked. And if builders
cannot be paid, the best agents never get shared.

## What it does

Agora is a market where anyone can sell an agent (a "helper") and anyone can hire one without trusting a stranger. PayPal is the one lever left:
**money committed before the work starts**.

- The buyer approves a **hold** on PayPal's page: the ceiling, the most this helper can charge (40 cents in the demo). Nothing is taken yet. The author never sees the buyer's card, only an email for payouts.
- If the run fails, the hold is released and the buyer pays nothing.
- If it finishes, the real price is worked out from facts the engine recorded (a standard run: 3 files, 2 model calls = 25 cents) and that part is **captured**; the other 15 cents are released. Partial capture is what lets the price follow the work.
- The buyer decides: **accept** and the author is paid out through PayPal; **not helpful** and only a small fee is kept, the rest comes back. A buyer can send most of it back, never all of it.
- A **full refund needs evidence**: after a helper is shut down mid-run the money stays held until the independent certifier flags that helper. Flagged: everything back, author earns nothing. Not flagged: the claim is rejected and the author keeps the fee. The buyer's word alone cannot cancel a payment.

## How authors charge

Five plans: one flat price, by files read, by tokens used, by how hard the question was (light, standard or deep, decided from the engine's
journal), and a monthly plan that covers a set number of answers, never renews by itself and can be stopped. Authors see what a light, standard
or deep run would cost before they publish.

## How we built it

- **Ledger**: one row per hire, one state machine (awaiting approval, authorized, running, result ready, settled, rejected, dispute hold, dispute upheld, voided). Every transition is checked under one lock, so accept and kill cannot both win (tested with racing pairs).
- **Idempotency**: every provider call carries a request id derived from the run (`PayPal-Request-Id`), so a lost reply is retried without charging twice.
- **Recovery**: a write-ahead intent is saved before each provider call; after a crash `recover()` finishes the operation exactly once.
- **Providers**: a fake provider that can lose replies and decline captures; the practice PayPal server; a sandbox client that refuses any non-sandbox host.
- **Console**: price, hold, deposit, refund and payout shown as plain-language receipts, always labelled as test money. The approval page tells the console tab, so the chat carries on by itself after the buyer approves.

## Challenges

- Deciding who may void money. A buyer-attested kill must not erase an author's pay, so a kill alone only holds.
- PayPal authorizations need the buyer to approve first, so we modelled that as an explicit state instead of assuming an instant hold.
- Letting the price follow the work without trusting the helper: the price is computed from the engine's recorded facts, never from what the helper says.

## Accomplishments

- A race-safe, restart-safe, retry-safe money state machine, with the payment tests checked to fail when idempotency or the state guard is removed.
- Money that follows evidence: an honest result is paid, a proven cheat is refunded, an outage costs nothing.
- About 660 automated tests across the platform.

## What we learned

When the work runs on the customer's machine, payment design becomes trust design. Holds, partial capture and evidence-gated refunds do work that a locked door does on a normal site.

## What's next

Run the whole flow on the live PayPal sandbox, real holdback and reserve periods, a human adjudicator for disputes the certifier cannot reproduce,
hosted mode, and legal review before any real money.

## Honest limits

Test money only. The PayPal client is unverified on the live sandbox unless you chose the first option above. Fees and timings are untuned proposals.
Pull mode has no fair exchange: the buyer could keep an output without paying; the hold, the small fee and the certifier limit that loss, they do not remove it.
Payment edge cases (reauthorization, honor-period limits, seller protection for intangible services) are not covered.

## Built with

Python, PayPal REST (sandbox) client, JSON Schema, Ed25519, Docker, NVIDIA Nemotron on Nebius Token Factory, JavaScript.
