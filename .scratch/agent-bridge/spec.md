# agent-bridge: build spec (hackathon slice)

Status: active. Written 2026-10-20. Design background: `architecture-v2.1.md` (full vision, 27 phases). This file is the part we build and ship.

## Product in one paragraph

A marketplace of agent + harness packs. A requester runs a third-party pack on their own machine (Pull mode) inside a sealed run: the pack reads only the records the user shares, has no network, and cannot send anything out. Any sign of theft stops the run and nothing is delivered. Packs are signed, evaluated by a Certifier, ranked by evidence, and paid per accepted task through PayPal.

## Deadlines (Pacific time, verified on Devpost 2026-10-08)

| Date | Event | Submit by (our buffer) |
|---|---|---|
| 2026-10-23 | Amazon Build, Ship, Shape | **dropped** (decision 2026-10-20) |
| 2026-10-30 10:00 | Nebius x NVIDIA | 2026-10-29 |
| 2026-11-12 12:00 | PayPal AI | 2026-11-11 |

Submission needs for both: public repo with an OSI licence, video under 3 minutes, text description. Nebius also needs a runtime call to the Token Factory API and a working demo URL or test build. Nebius track: Personal AI (private assistant, persistent memory, data under the user's control) plus the Tavily bonus.

## Done before this spec (2026-10-20, 138 tests)

Workflow parser, digest, signing, Memory Broker (lens, accounting, decoy canaries), Result Guard, flowd engine + hash-chained journal, Docker Cell (no network), Nebius Nemotron client, registry, Certifier, ranking, web console, `bridge seed`, `bridge serve`.

## Milestones

### M1 - Nebius core (due 2026-10-26)

Exit test: a stranger clones the repo, runs two commands, and in the console sees a ranked marketplace of at least 4 packs, runs one honest pack on real Nemotron, watches a malicious pack get killed, accepts a memory proposal into their vault, and sees a pack improve from v0.1 to v0.2 with a measured score.

Tickets: 01 packs and ranking spread, 02 Tavily public step, 03 memory write path (proposals, quarantine, accept), 04 pack improvement loop, 05 console polish (history, audit view), 06 Cell-backed malicious pack in the console.

### M2 - Nebius submission (due 2026-10-29)

Exit test: repo public, README reproduces the demo from a clean clone on a second shell, video under 3 minutes uploaded, Devpost form filled, feedback section filled.

Tickets: 07 README, architecture overview and honest-limits page, 08 demo script and video, 09 public repo, licence and notices, clean-clone check, 10 Devpost text and Nebius feedback.

### M3 - PayPal core (due 2026-11-08)

Exit test: in PayPal sandbox, a run creates an authorized order, a completed honest run captures the floor fee and the outcome fee on accept, a killed run voids or holds, and the author payout is recorded. Console shows each money state.

Tickets: 11 payment provider interface and PayPal sandbox client (needs sandbox credentials from the owner), 12 ledger state machine (one hire, one capture, one payout; kill-vs-accept race), 13 console payment UI, 14 payouts and holdback.

### M4 - PayPal submission (due 2026-11-11)

Exit test: PayPal video under 3 minutes, Devpost form filled, repo README has the payment section.

Tickets: 15 PayPal demo script and video, 16 PayPal Devpost text.

## Cut line (if a milestone slips, cut in this order, never the deadline)

1. 05 console polish beyond the basics.
2. 04 improvement loop becomes a recorded run instead of live.
3. 14 real payouts become ledger-only entries labelled sandbox.
4. 02 Tavily (loses the $3K bonus only).

Never cut: 03 memory write path (it is the Personal AI track story), 06 malicious pack in the sealed Cell, 09 public repo, the video.

## Honest limits to print in the README

Pull has no fair exchange; the requester keeps the output. Detectors are evidence, not proof; a slow leak inside the lens may evade them. Sealed Hosted, multi-device sync, key management and legal review are designed, not built. Scores come from a small suite; 3 of 3 passes ranks below 28 of 30 on purpose.

## Working rules

One feature per commit, tests first or with it, run the suite before committing (never commit red). Keys live only in `.env`. Every user-visible claim has a test that backs it.
