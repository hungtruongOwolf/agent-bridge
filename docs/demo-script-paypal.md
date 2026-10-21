# Demo script: PayPal AI (Agentic Commerce), target 2:50, hard limit 3:00

The story for this video is **an agent hires an agent, and money follows the evidence**. Reuse the same console as the
Nebius video; the new thing on screen is the *Your coins* panel and the coins flying to the jar and the Bank. Everything is test money. If you have run the PayPal
sandbox successfully (see "Before you record"), say "PayPal sandbox"; if not, say "test money" and do not mention PayPal as
the live provider.

## Before you record (checklist)

1. Decide the provider honestly. Run `bridge paypal-check`. If it prints `OK`, record with `bridge serve --payments paypal` and
   a sandbox buyer approving on camera. If it fails or you have no credentials, record with `bridge serve` (fake provider) and
   say "test money" throughout. Never imply real money.
2. Same setup as the Nebius checklist: Docker engine up, `bridge seed` run today, fresh `.bridge\vault.json`, delete
   `.bridge\ledger.json` and `.bridge\provider.json` so the wallet starts at $0.00.
3. Know the numbers in advance: `private-analyst` costs $0.40, the floor fee is $0.10, the outcome fee $0.30, the author is paid $0.36
   after a 10% platform fee. `quick-insights` costs $0.10.
4. Dry-run each scene once. Close notifications.

## Script

**0:00 to 0:15, hook**
"Agents can already call tools. The next step is agents hiring other agents, and that needs money that follows evidence,
not trust."

**0:15 to 0:35, hire**
Select `private-analyst`. Point at the price on the Start button and the *Test coins* chip.
"Hiring an agent places a hold for its price. Nothing is charged yet." (If using PayPal: approve the hold on the sandbox page and
click continue.)

**0:35 to 1:05, the work and the floor fee**
Run. When the result appears, point at the *Your coins* panel and the jar on the floor.
"The agent ran on my machine and reached only the records I shared. Now there is a result, so a floor fee of ten cents is captured.
The other thirty cents is still on hold."

**1:05 to 1:30, accept**
Click *Good: pay in full*. Coins fly to the Bank.
"Accepting captures the rest. The author is paid thirty-six cents after the platform fee. If I did nothing, the result would be
accepted automatically at the deadline, so an author is never left unpaid by silence."

**1:30 to 2:05, the bad agent, and money follows evidence**
Select `quick-insights`, run. Three blocked attempts appear, then *Your coins* says the claim was upheld and the hold is released.
"This agent's code tried to send my data out. The run was stopped and nothing was delivered. The hold is not simply cancelled by my
say-so, because I could lie. It is held until independent evidence arrives: the Certifier had already reproduced this exact violation,
so the hold is refunded and the author earns nothing."

**2:05 to 2:30, what protects both sides**
Show *Past jobs* and the coins chip at the top.
"Every call to the payment provider is idempotent, so a lost response never charges twice. Accept and kill cannot both win: one lock
decides. A crash in the middle is recovered from a write-ahead record. These are tested, including a race test."

**2:30 to 2:50, close**
"Pull mode has no fair exchange yet: a requester could keep an output without paying. The floor fee, the held dispute and the
Certifier limit that loss; they do not remove it. Open source, MIT, link below."

## Shot list

| Time | Screen | Voice |
|---|---|---|
| 0:00 | console | hook |
| 0:15 | price on the Start button, Test coins chip | hire |
| 0:35 | run, Your coins panel with the deposit | deposit |
| 1:05 | Accept, settled line with the author payout | accept |
| 1:30 | quick-insights killed, "claim upheld" panel | evidence |
| 2:05 | Past jobs, coins chip | protections |
| 2:30 | README limits | close |

## Do not claim

Real payments, real money, "PayPal verified" if `paypal-check` did not pass, tax or legal compliance, or that the floor fee removes the
no-fair-exchange problem. Do not show your PayPal developer dashboard or any secret on screen.
