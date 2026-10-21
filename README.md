# agent-bridge

**Rent a stronger agent. Keep your data.**

agent-bridge is a marketplace of *agent + harness* packs. A pack is a signed workflow (prompts, tools,
checks) written by someone else. You run it **on your own machine**, in a sealed run: it can read only
the records you choose to share, it has no network, and if it tries to take anything it was not given,
the run is stopped and nothing is delivered. Packs are evaluated by a Certifier and ranked by evidence,
not by popularity.

Built for the Nebius x NVIDIA hackathon (Personal AI track): inference runs on **NVIDIA Nemotron via
Nebius Token Factory**, web lookups use **Tavily**.

## See it in two minutes

The console is a **market floor**. Every chat you have open is a small stall with its own helper, all on one picture, so you can see who is
working, who is waiting for you and who was stopped by the guard. Click a stall to walk into that chat's **small office**: a safe with
your shelves, a glass room where the helper works, a guard, and your assistant, acting out the real record of each answer.

1. **Pick who to talk with** from a ranked list, or tell the assistant what you need (typed or spoken) and it suggests helpers by their own skills.
2. **Open shelves.** My memory is a library: shelves inside shelves, each with a count and the words it is about, so a very large memory is
   searched by walking down the tree (only the shelves that fit your question are opened, and the walk is shown). A new chat shares
   **nothing** until you open a shelf. **Secret** files can never be shared, even if you tick them. There is no privacy dial: one rule.
3. **Chat.** The helper gets only the opened shelves and the last few messages. Each answer says which files it came from and how it was made.

4. **Build and publish your own helper** in **My helpers**: edit its steps as a picture, practise on your own shelves, publish it with your signature and a price. A tester then scores it and tries to catch it cheating; the score, not your claim, ranks it.

Two of the helpers are malicious on purpose. One reaches for the secret drawer. The other ships real code that tries to send a
message out of the room, open another program and write outside its notebook. The glass stops all of it, the guard sounds the alarm,
nothing reaches your desk, and your coins come back. Everything on the floor replays the job's real record.

## Quickstart

Requirements: Python 3.11+, a Nebius Token Factory key, a Tavily key. Docker is needed only for packs
that contain code (on Windows, Docker Engine inside a WSL2 Ubuntu distro; see below).

```bash
git clone https://github.com/hungtruongOwolf/agent-bridge && cd agent-bridge
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                                    # then put your two keys in .env
bridge seed                                             # publishes the demo packs and certifies them (a few minutes)
bridge serve                                            # open http://127.0.0.1:8787
```

Other commands:

```bash
bridge run examples/packs/private-analyst --vault examples/vault.json --types note,contact
bridge improve deal-brief      # propose better instructions, measured on a public dev suite
bridge approve deal-brief      # owner approval: publish the candidate, certify it on the held-out suite
bridge paypal-check            # optional: verify PayPal sandbox credentials (creates one uncharged test order)
bridge serve --payments paypal-mock # optional: a local practice PayPal with an approval page (no credentials)
bridge serve --payments paypal # optional: the real PayPal sandbox (needs credentials, see docs/paypal-setup.md)
pytest                         # ~310 tests; the container tests are skipped if no engine is found
```

**Containers.** Code steps run in a container with no network. On Linux and macOS the default is
`docker`. On Windows the engine is reached through WSL (`wsl -d Ubuntu-22.04 -u root -- /usr/bin/docker`).
Set `BRIDGE_DOCKER` to use something else (for example `podman`). Without an engine, `bridge seed` still
works: packs that need a cell are published but left *uncertified*, and never shown as safe.

## Payments (test money)

Each run is a hire. The requester places a hold for the pack's price, the pack runs, and money moves only through a
ledger state machine: a **floor fee** is captured when a result exists, the **outcome fee** only when you accept
(or when the accept window passes), and a rejected result keeps only the floor. A run that is stopped for theft is
**held, not voided**; the hold is refunded when the Certifier independently reproduces the violation for that exact
pack. Outages and crashes release the hold with no charge. The author is paid after a platform fee; the demo holdback
is 0 seconds and the console says so. Everything is labelled as test coins.

## How it works

```
 requester machine                                                         hub (local demo)
┌──────────────────────────────────────────────────────────────┐        ┌───────────────────┐
│ console ── runner ── flowd (workflow engine, journal)        │        │ registry (signed) │
│                         │                                    │        │ Certifier         │
│        ┌────────────────┼──────────────────┐                 │        │ ranking           │
│        ▼                ▼                  ▼                 │        └───────────────────┘
│  Memory Broker     Model client      Cell (container,        │
│  (lens, canaries,  (Nemotron via     no network, sensor)     │
│   accounting)      Nebius)                                   │
│        │                                                     │
│  vault ◀── Quarantine (proposals wait for you)               │
│        Result Guard ── the only way a result leaves          │
└──────────────────────────────────────────────────────────────┘
```

A **pack** is a directory: `pack.yaml` (identity, result schema) and `workflow.yaml` (a program in a small
closed language: `tool`, `llm`, `code`, `gate`, `return`). The engine runs it; the pack never gets a
socket, a file handle or the model key. Anything it wants goes through the Broker, the model client or the Cell.

## What is guaranteed, and the test that proves it

| Claim | Mechanism | Test |
|---|---|---|
| A pack reads only the records you shared | Closed staged set; no list-everything call | `tests/memory/test_broker.py` |
| Touching a decoy record kills the run | Per-run decoys served only on off-lens queries | `tests/memory/test_broker.py`, `tests/engine/test_flowd.py` |
| Pack code has no network | Container `--network none`, read-only fs, no capabilities | `tests/sandbox/test_cell.py` |
| Trying the network or a process kills the run | In-cell audit-hook sensor, evidence kept in the journal | `tests/sandbox/test_engine_cell.py` |
| What leaves is bounded | Schema, size cap, canary and verbatim-copy scan | `tests/guard/test_result_guard.py` |
| Nothing is remembered without you | Quarantine, typed proposals, user-only accept, per-run revert | `tests/memory/test_quarantine.py`, `tests/web/test_server.py` |
| Your records cannot ride a web search | Static taint rule plus a runtime query check | `tests/pack/test_workflow.py`, `tests/engine/test_flowd.py` |
| You run the bytes that were signed | Raw-byte digest, Ed25519, purpose-bound signatures | `tests/pack/test_digest.py`, `tests/pack/test_signing.py` |
| Scores cannot be forged or bought | Signed attestations; stars never lift a pack above a certified one | `tests/hub/test_certifier.py`, `tests/hub/test_market.py` |
| A new version cannot quietly gain powers | Capability set; widening needs a major version | `tests/pack/test_caps.py`, `tests/hub/test_registry.py` |
| The run record cannot be edited | Hash-chained journal, torn-tail recovery | `tests/engine/test_journal.py` |
| One hire makes one hold, one capture, one payout | State machine under one lock, idempotent provider calls, write-ahead recovery | `tests/payments/test_ledger.py` |
| A kill never voids delivered work on its own | Kill goes to a held dispute; only independent evidence refunds | `tests/payments/test_ledger.py`, `tests/web/test_server.py` |
| You are not charged for a result you never got | Floor fee only when a result exists; outage or crash voids the hold | `tests/payments/test_ledger.py` |
| Another website cannot start runs | Local bind, host check, per-process token | `tests/web/test_server.py` |

## Honest limits

- **Pull mode has no fair exchange.** The requester's machine runs the pack and could keep the output
  without paying. The payment design (a hold, a floor fee, dispute handling) limits the loss; it does not remove it.
- **Money is test money.** Payments run through a ledger with three providers: demo coins, a **practice PayPal** (a local emulator
  of the sandbox, run through the real client code and shown with an approval page and receipts), and the PayPal sandbox client. The
  client has been tested against the practice server only; it has **not been run against the live sandbox yet** (see `docs/paypal-setup.md`
  for what the owner needs to provide). Nothing real moves in any mode.
- **Detection is evidence, not proof.** A slow leak of information inside the shared records, through the
  allowed output, may not trip anything. The guarantee is that the pack sees only what you shared and the
  output channel is bounded, not that detectors catch every theft.
- **The Certifier suite is small.** Three quality tasks plus a security trap. A pack with 3 of 3 passes scores
  lower than one with 28 of 30 on purpose. Scores say "evaluated on this suite", never "safe".
- **The honest helpers now tie.** On the current six-question suite (contact lookup, follow-up using the chat, and admitting there is nothing to go on were added) all four honest example helpers pass 24 of 24 with Nemotron, so ties are broken by the lower price. The suite separates cheaters and sloppy answers, not good helpers from slightly better ones.
- **Improvement partly fits the dev suite.** In our earlier live run (older suite and pack versions) `deal-brief` moved from 0.35 to 0.57 on the public
  dev suite and from 0.39 to 0.55 on the held-out suite. The dev gain is larger, so part of it is fitting to that suite.
- **The model needed care.** Nemotron reasons in a hidden field and can spend its whole token budget before it
  writes an answer, which looked like empty replies. The client turns thinking off (complete answers in about 40
  tokens instead of 300 to 1,200), retries up to three times, and the Certifier does not count infrastructure
  failures against a pack. Thinking off also changes scores, so every number here was measured with it off.
- **Built in this repo:** the workflow engine, Memory Broker, Result Guard, sealed Cell, registry, Certifier,
  ranking, payment ledger (test money), local console. **Designed, not built:** Hosted mode on someone else's
  machine, sealed enclaves, multi-device sync, key management, verified PayPal sandbox payments, legal review. See `.scratch/agent-bridge/architecture-v2.1.md`.
- The "test mode" switch in the console makes the helper's model misbehave and is a simulation. The code-based malicious pack is not.
- Windows needs WSL2 for the Cell. The console's narrow-screen layout is written but was not visually verified.

## Layout

```
src/bridge/pack/      workflow language, digest, signing, capabilities
src/bridge/engine/    flowd engine, journal, Nebius and Tavily clients
src/bridge/memory/    vault, Memory Broker, Quarantine
src/bridge/guard/     Result Guard
src/bridge/sandbox/   container Cell and its sensor
src/bridge/hub/       registry, Certifier, marketplace ranking
src/bridge/web/       local console
examples/             demo vault and 6 demo packs (4 honest, 2 malicious)
.scratch/             design notes, spec and tickets
```

## License

MIT, see [LICENSE](LICENSE). Third-party notices are in [NOTICE](NOTICE).
