# Architecture overview

This is the short version for people who have not read the 3,000 lines of design notes in
`.scratch/agent-bridge/` (start with `architecture-v2.1.md`). It says what the system is, how a run
flows, and, just as important, what is built and what is only designed.

## The problem

No single agent setup is best at everything, and you cannot borrow someone else's setup without
handing it your data. Running a stranger's agent on your machine looks safe only if the agent cannot
see more than you intend and cannot send anything out. agent-bridge makes that a property of the
runtime instead of a promise from the author.

## Roles

| Role | Does |
|---|---|
| **Author** | Writes and signs a pack, sets a price. |
| **Requester** | Runs a pack on their own machine, on data they choose to share. |
| **Certifier** | Runs packs on fixed suites, including a security trap, and signs what it measured. |
| **Hub** | Registry of signed packs, attestations, ranking. (A local demo hub in this repo.) |

## Anatomy of a run

1. **Preflight.** The runner recomputes the pack's digest and refuses if it differs from the registered one.
2. **Stage.** The Memory Broker selects the records that match the lens you approved (type and sensitivity)
   and freezes that set. Everything else is out of reach.
3. **Execute.** `flowd` walks the workflow one step at a time. A step sees only the outputs it declared in
   `reads`, may use only the tools it was granted, and every start and commit is written to a hash-chained journal.
   - `tool` steps call the Broker (memory) or Tavily (web, public steps only).
   - `llm` steps call Nemotron through the requester's own model client. The pack never holds the key.
   - `code` steps run in a container with no network. An in-cell sensor records attempts to use the
     network, start a process or write outside scratch space; the first two end the run.
   - `gate` steps check a result against the schema before it moves on.
4. **Guard.** The Result Guard checks the final result and any memory proposals: schema, size, decoy values,
   verbatim copies of your records. A decoy value anywhere in the output ends the run as killed.
5. **Decide.** The result is delivered, or discarded. Proposals to remember go to quarantine. They enter
   your vault only if you accept them, and a run can be reverted later without touching your own records.

## Scope rule for the web

A step that reaches the web is *public*. It may not read memory, and it may not read any step that did.
Web results may flow into private steps (research, then analysis), never the other way. A runtime check
also refuses a query that repeats text from a staged record.

## How the console is built

Browser: ES modules with a client-side router (`web/static/js/`: `lib/` shared code, `views/` one file per screen,
`components/`, `pixel/`, `studio/`). Server: `web/api/` (router and transport with every safety rule), `web/routes/`
(address to service), `web/services/` (running helpers, payments), `web/server.py` (wires the parts). Data: small SQLite
databases in the state folder (`storage/`). Decisions and their reasons: `docs/adr/`.

## Certification and ranking

The Certifier runs each pack on three quality tasks (several risks, one real risk among distractors, no
false alarm when all is healthy) and one security trap that holds records outside the lens. The score is the
lower bound of a 95% Wilson interval on the pass rate. A pack that touches anything outside its lens gets no
score and is shown as *flagged*. Infrastructure failures are not counted against a pack. Stars never lift a
pack above a certified one.

## Improvement

`bridge improve` asks the model for alternative instructions for the step that produces the result, scores each on a
public development suite, and keeps the best one only if it beats the baseline by a margin. A typed diff must
show that nothing but the instruction text changed. The owner approves before the new version is published,
and only then is it scored on the held-out suite. The registry refuses any version that widens what a pack can do
unless the major version goes up.

## Built and designed

| Area | Built here | Designed in `.scratch/` only |
|---|---|---|
| Pull mode (run on your machine) | yes | |
| Memory: lens, accounting, decoys, quarantine, revert | yes | multi-device sync, crypto-shred, encrypted journal |
| Sealed code execution | container, no network, sensor | microVM tier, Sealed enclaves |
| Workflow engine | five step kinds, journal, budgets | loops, map, parallel, human nodes, resume |
| Registry, signing, Certifier, ranking | local demo hub | key hierarchy, transparency log, hub trust domains |
| Improvement loop | prompt variants | topology edits, GEPA |
| Payments | | PayPal hold, floor and outcome fees, disputes, payouts |
| Hosted mode (run on someone else's machine) | | quotes, host daemon, gateway |

## Threat model in one paragraph

We assume the pack author is hostile and the requester's machine is honest. A hostile requester can keep a
pack's output without paying; that is a property of running someone's code locally and is handled by the payment
design, not the sandbox. A compromised hub or a sandbox escape is out of scope for this build.
