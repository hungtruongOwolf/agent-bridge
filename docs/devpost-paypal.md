# Devpost text: PayPal AI (Agentic Commerce)

Paste into the Devpost form. Fill the bracketed items. Read the official rules once more before submitting: we have only
verified the dates and a few requirements, not every criterion.

## Tagline

Agents hire agents. Money follows the evidence.

## Honest disclosure (put this near the top of the description)

All payments in the demo are **test money**. The ledger and every money flow are implemented and tested against an in-memory
provider and against a local **practice PayPal** server that emulates the sandbox (approval page, authorize, capture, void, refund, payouts)
and runs the real client code. A PayPal sandbox client (Orders v2 authorize, capture, void, refund, Payouts) is included. [CHOOSE ONE BEFORE SUBMITTING:
"It has been run against the live PayPal sandbox, see the video." OR "It has not yet been run against the live PayPal sandbox; the video uses the
built-in test money."] No real money moves anywhere.

## Requirements checklist

| Requirement | Where it is met |
|---|---|
| Public repo with an OSI licence | [REPO LINK], MIT |
| Video under 3 minutes | [YOUTUBE LINK] |
| Working demo or test build | `bridge seed`, `bridge serve` (README quickstart, verified from a clean clone) |
| PayPal used | `src/bridge/payments/paypal.py` (sandbox client), `src/bridge/payments/ledger.py` (flows) [adjust to match the choice above] |

## What it does

agent-bridge is a marketplace where an agent can hire another agent without handing over its data. A pack runs on the requester's machine, sees
only the records the requester shares, and cannot send anything out. This submission is about the money.

Each run is a hire. The requester places a **hold** for the pack's price. When a result exists, a **floor fee** is captured. The
**outcome fee** is captured only when the requester accepts, or automatically when the accept window passes. Rejecting keeps only the floor.
If the run is stopped for theft, the hold is **held in dispute, not voided**: the requester's own claim cannot erase an author's pay, because
the requester could lie. It is refunded only when independent evidence arrives, here the Certifier having reproduced the same violation for that pack.
Outages and crashes release the hold with no charge.

## How we built it

- **Ledger**: one row per hire, one state machine (AWAITING_APPROVAL, AUTHORIZED, RUNNING, RESULT_READY, SETTLED, SETTLED_REJECTED,
  DISPUTE_HOLD, DISPUTE_UPHELD, VOIDED). Every transition is checked under one lock, so accept and kill cannot both win (tested with 40 racing pairs).
- **Idempotency**: every provider call carries a request id derived from the run, so a lost response is retried without charging twice.
- **Recovery**: a write-ahead intent is saved before each provider call; after a crash, `recover()` finishes the operation exactly once.
- **Silence rule**: if the requester goes quiet after the run started, the floor is captured and the outcome falls to auto-accept, so an author is not unpaid
  just because the requester never reported back.
- **Providers**: a fake provider that can lose replies, decline captures and require buyer approval; a PayPal sandbox client that refuses any non-sandbox host.
- **Integration**: the console shows price, hold, floor, outcome, refund and the author payout as plain-language receipts (click the coins chip), always labelled as test or practice money. The approval page tells the console tab, so the chat carries on by itself once the buyer approves.

## Challenges

- Pull mode has no fair exchange: the requester can keep an output without paying. The floor fee, held disputes and the Certifier limit that loss; they
  do not remove it, and we say so.
- Deciding who may void money. A requester-attested kill must not be able to erase an author's pay, so a kill alone only holds.
- PayPal authorizations need the buyer to approve first; we modelled that as an explicit state rather than assuming an instant hold.

## Accomplishments

- A race-safe, restart-safe, retry-safe money state machine with about 50 payment tests. We checked by hand that removing idempotency or the state guard makes them fail.
- Money that follows evidence: an honest result pays, a caught thief is refunded, an outage costs nothing.

## What's next

Run the full flow against the live PayPal sandbox, add real holdback and reserve periods, a human adjudicator for disputes the Certifier cannot reproduce,
Hosted mode on another person's machine, and legal review before any real money.

## Honest limits

Test money only. The PayPal client is unverified unless you chose the first option above. Fees (25% floor, 10% platform) and timings are untuned proposals.
Pull mode has no fair exchange. Payment edge cases (reauthorization, honor-period limits, seller protection for intangible services) are not covered.

## Built with

Python, PayPal REST (sandbox) client, JSON Schema, Ed25519, Docker, NVIDIA Nemotron on Nebius Token Factory, Tavily.
