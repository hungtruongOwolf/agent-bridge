# Demo script: PayPal AI (Agentic Commerce), target 2:50, hard limit 3:00

The story: **an agent hires an agent, and money follows the evidence.** The same console as the Nebius video; the new thing on screen is the
approval page, the coins chip and the receipts. Everything is test money.

## Before you record (checklist)

1. Decide the provider honestly and say it out loud:
   - `bridge paypal-check` prints OK: record with `bridge serve --payments paypal` and approve on PayPal's sandbox page. Say "PayPal sandbox".
   - No credentials: record with `bridge serve --payments paypal-mock`. Say "a practice PayPal that behaves like the sandbox". Never call it PayPal.
   - Or `bridge serve` for demo coins. Say "test money". Never imply real money.
2. Fresh state: delete `.bridge\threads.json` and the ledger files (`.bridge\ledger*.json`, `.bridge\provider.json`, `.bridge\paypal-mock.json`) so the wallet starts at 0.
3. Use `--vault examples/vault-library.json` so the memory looks lived-in. Docker up, `bridge seed` run today.
4. Know the numbers: Quick Skim 15¢, Private Analyst 40¢, Deal Brief 60¢. The floor fee is 25 percent of the price, the author gets the price less a 10 percent fee.
5. Dry-run once. Close notifications. Keep two browser windows ready if you use the practice PayPal or the sandbox: the console and the approval page.

## Script

**0:00 to 0:15, hook**
"Agents can already call tools. The next step is agents hiring agents, and that needs money that follows evidence, not trust."

**0:15 to 0:40, hire**
My memory tab, 10 seconds: "These are my notes. A helper only sees the shelves I tick, and secret notes never leave."
Start a chat with Private Analyst, tick Work > Accounts, ask "Which accounts are at risk?" and press Send.
"Hiring an agent asks me to approve a hold for its price. Nothing is charged yet." Click **Open the approval page**, approve. The chat carries on by itself.

**0:40 to 1:10, the work and the floor fee**
Watch the small office act out the run. Click the coins chip.
"The helper ran on my machine and read only the shelves I opened. Now there is an answer, so a floor fee is captured. The rest stays on hold until I keep going."

**1:10 to 1:35, accept or not**
Send a second message. "Sending my next message means the last answer was good enough, so the rest is paid and the author gets paid less the platform fee."
Open the receipts: "Every step is written down in plain words."
(Optional: on another answer press **Not helpful**: only the deposit is paid and the rest is released.)

**1:35 to 2:05, the bad agent, and money follows evidence**
Open the market floor: the Guard post shows what was stopped. Open a chat with a helper that cheats (use the test helper) or show the receipt of a stopped run:
"This agent tried to take a file it was not given. The run was stopped and nothing was delivered. The hold is not simply cancelled on my word, because I could lie. It is held until independent evidence arrives: the tester had already reproduced this exact cheating, so the hold is refunded and the author earns nothing."

**2:05 to 2:30, what protects both sides**
Show the receipts and the dashboard (practice PayPal page or the sandbox dashboard).
"Every call to the payment provider is idempotent, so a lost reply never charges twice. Accept and stop cannot both win: one lock decides. A crash in the middle is recovered from a write-ahead record. These are tested, including a race test."

**2:30 to 2:50, close**
"Pull mode has no fair exchange yet: a requester could keep an output without paying. The floor fee, the held dispute and the tester limit that loss; they do not remove it. Open source, MIT, link below."

## Shot list

| Time | Screen | Voice |
|---|---|---|
| 0:00 | market floor | hook |
| 0:15 | My memory map, then chat, approval page | hire |
| 0:40 | chat + small office, coins chip | the work and the floor fee |
| 1:10 | second message, receipts | accept |
| 1:35 | guard post, stopped run receipt | evidence |
| 2:05 | receipts, dashboard | protections |
| 2:30 | title card | close |

## Do not say

"Real money", "live PayPal" (unless `bridge paypal-check` passed), "secure" without the word "tested", or that the practice server is PayPal.
