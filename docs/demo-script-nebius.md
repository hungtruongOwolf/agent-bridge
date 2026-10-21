# Demo script: Nebius x NVIDIA (target 2:50, hard limit 3:00)

Record screen plus voice. One take per scene, cut together. Everything below is real except where marked
**recorded**; say so on screen for those scenes.

## Before you record (checklist)

1. Docker engine up in WSL: `wsl -d Ubuntu-22.04 -u root -- /usr/bin/docker info` prints without error.
2. Fresh state: delete `.bridge\vault.json` so no accepted memory is left over, keep the rest of `.bridge\`.
3. `bridge seed` was run today (scores on screen must match the README claims). Note the numbers it prints.
4. `bridge serve`, open http://127.0.0.1:8787 at 1568 px wide, browser zoom 100%, dark theme, bookmarks bar hidden.
5. Keys in `.env`. Check the Nebius balance is enough for about 10 runs.
6. Close other windows and notifications. Do one dry run of every scene.

## Script

**0:00 to 0:15, hook** (voice over the empty console)
"No single agent setup is best at everything. But you cannot borrow someone else's without giving them your data.
agent-bridge lets you run a stranger's agent on your own machine, and it cannot take anything you did not share."

**0:15 to 0:40, the marketplace**
Show the ranked list. Point at one certified card and its evidence line, then at the two flagged cards.
"Packs are signed, and a Certifier scores them on a hidden suite. Stars cannot buy rank. Two packs here are flagged:
they failed a security trap."

**0:40 to 1:10, honest run, real Nemotron**
Select `private-analyst`. Untick nothing; show records marked *kept private*. Run.
"It reads only the shared records. Inference runs on NVIDIA Nemotron through Nebius Token Factory. The Result Guard checks
the answer before I see it." Open the audit log for two seconds: "every step is in a hash-chained journal."

**1:10 to 1:55, malicious run, live**
Select `quick-insights`. Run (no simulation). The three blocked attempts appear.
"This pack hides real code. It tried to open a socket, start a program and write a file, all inside a sealed cell with no network.
All blocked, the run is stopped, nothing was delivered, and my records were never exposed. The Certifier flagged it by behaviour,
not by name."

**1:55 to 2:20, memory that stays yours**
Select `deal-brief`, run. A suggestion appears under *Waiting for your decision*. Click *Remember*.
"A pack can only suggest. Nothing is saved unless I accept. The saved record carries its origin, and I can undo the whole run."
Click undo to show it goes away.

**2:20 to 2:42, how packs improve** (**recorded**, label it "recorded run")
Show the terminal output of `bridge improve deal-brief` and `bridge approve deal-brief`.
"A pack improves by measurement. Variants are scored on a public dev suite, a typed diff proves only the instruction changed,
and the owner approves before it is scored on the hidden suite: 0.39 to 0.55." Say once: "the dev-suite gain was bigger,
so part of it is overfitting."

**2:42 to 2:50, close**
"Tavily powers a web step that is not allowed to see your data. Pull mode has no fair exchange yet; payments are next.
Open source, MIT, link below."

## Shot list for the cut

| Time | Screen | Voice |
|---|---|---|
| 0:00 | console, empty run panel | hook |
| 0:15 | marketplace, cursor on scores and flags | marketplace |
| 0:40 | run private-analyst, audit log opens | honest run |
| 1:10 | run quick-insights, scroll to the red banner | malicious run |
| 1:55 | deal-brief, Remember, then Undo | memory |
| 2:20 | terminal, improve and approve | improvement |
| 2:42 | README limits section | close |

## Do not claim

"Nothing can ever leak", "certified means safe", "payments work", or anything about Hosted mode. Say "evaluated on a suite"
and "Pull mode". If a scene is recorded or simulated, say so.
