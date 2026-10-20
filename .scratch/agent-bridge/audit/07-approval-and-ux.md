# Audit 07: approval and human-in-the-loop UX flows

Date 2026-10-07. Scope: architecture-v2.md sections 3.3, 4.3, 5.3, 6, 7.2-7.3 plus research-v3/02 (workflow gates, F5) and research/08 (relay and phone pairing). No external facts were fetched this round; items that rely on outside knowledge are marked UNVERIFIED. Statements about what the design "does not say" mean: not found in architecture-v2.md or research-v3/02.

## 1. Actors and the state each holds

| Actor | Holds | Notes |
|---|---|---|
| Human requester (H) | Desktop session, phone | Approves cards, gates, Q items, results |
| Local requester agent (LA, Nemotron) | Reads vault in full, picks pack, proposes lens, runs Disclosure Compiler | Reads author-written listing text. Acts as a delegate of H |
| Supervisor (SUP) | Kill / quarantine / revoke, run state, signed checkpoints | Authority for run state |
| Vaultd | U, Q, journal, Merkle checkpoints | Staging and rollback |
| Sidecar + Detectors | Broker, Result Guard, D1-D14 | |
| Phone PWA (PH) | Phone keypair, cached card previews | Paired to desktop key (research/08 section 4) |
| Relay | Ciphertext, metadata, queues | Honest-but-curious, can delay, drop, reorder |
| Hub | Quotes, run tokens, PayPal authorization, ranking | |
| Pack author (AU) / pack owner | Pack, price, acceptance_checks, improvement loop | Free-text fields in card.json |
| Host operator | Root on Hosted host | No consent step exists in v2 flow |
| PayPal | Authorization hold (honor period UNVERIFIED) | Time-bounded |

Three UIs named or implied: requester console and phone PWA (requester), Pack Studio dashboard (owner/author), host daemon (Hosted). Only the requester console is described.

## 2. Flow as numbered sequence with states

Run state machine (requester side). States: DRAFT -> CARD_SHOWN -> APPROVED -> AUTHORIZED -> STAGING -> RUNNING -> (GATE_WAIT | PAUSED) -> RETURNED -> GUARDED -> ACCEPT_WAIT -> CAPTURED | VOIDED; terminal side exits: KILLED, QUARANTINED, REVOKED, CANCELLED(undefined), EXPIRED(undefined).

1. H gives task to LA. LA calls hub browse, reads card.json (author text), selects pack, proposes lens. (state DRAFT)
2. Disclosure Compiler builds byte-exact lens preview; card = digest, mode, lens, budget, driver tier. Shown on desktop and relayed to phone. (CARD_SHOWN)
3. H approves on desktop or phone. Phone sends signed approval via relay. (APPROVED)
4. Hub issues run token and PayPal AUTHORIZE at cap. (AUTHORIZED)
5. Vaultd stages snapshot to /in, mints Biscuit, driver starts Cell. (STAGING -> RUNNING)
6. Workflow steps run; gates may pause for H (GATE_WAIT); detectors may pause (PAUSED) awaiting confirmation; timeout default may kill.
7. Result Guard, acceptance checks, H Accept. Capture. Q proposals to Q.
8. Digest later: H approves profile/procedural changes and Q items.
9. Incident path: ladder 4-9 including rollback of U to pre-task checkpoint.

## 3. Step-by-step failure questions (condensed)

| Step | Failure / race | Finding |
|---|---|---|
| 1 | Author text in card.json reaches LA | F7 |
| 2 | Preview is of bytes at T0; staging at T1; lens is also a query-time semantic filter | F2 |
| 2 | Card "once per tuple": is the approval reusable | F2, F10 |
| 3 | Phone approve + desktop approve concurrently; replay; stolen phone; offline desktop; queued approval executes late | F3 |
| 4 | Price or quote changes between card and AUTHORIZE; hold expires during long run | F5 |
| 5 | Driver changed between card and start; driver tier shown from listing not machine | F8 |
| 6 | User cancels while gate approval in flight; laptop sleeps; D6 confirm timeout kills honest run | F5, F3 |
| 7 | 200-file patch; author-declared acceptance_checks; Accept couples money, rank, apply | F6 |
| 8 | Digest approval makes foreign text tier 3; approval days after run | F1 |
| 9 | Rollback to checkpoint discards user's concurrent legit writes | F4 |

## 4. Consistency with other flows and the guarantees text

- Guarantees text headline "no network interface" omits that every run sends lens text to Nebius (3.3 lists it only as a non-guarantee).
- B5 says the hub enables ZDR "at account level" but the Model Proxy "holds key" of the requester in Pull; the hub cannot set an account setting on the requester's Nebius account. The card must not claim ZDR unless verified per run.
- Section 6.2 step 4 stages a snapshot to /in, while 4.4 serves memory.search via Broker over a lens that is a query-time filter. Preview can be byte-exact only for the staged part.
- Round 1 decision "owner sees preview of the result before it leaves the machine" has no counterpart in Hosted (6.3) where the host runs the pack.
- Demo scene 0:45-1:15 "accept one proposed memory item" demonstrates the exact promotion that F1 shows is a trust-laundering step.

## 5. Findings

See the structured output returned with this audit (F1-F12). Ranking: F1 trust laundering, F2 approval not bound to what runs, F3 phone approval protocol, F4 rollback destroys legit writes, F5 no cancel/timeout/hold terminal table, F6 result acceptance, F7 author text into agent and card, F8 downgrade dead end and Windows setup, F9 guarantee comprehension, F10 fatigue and version re-approval, F11 Hosted actors and missing UIs, F12 long-run visibility and accessibility.
