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

1. **Pick an agent** from a ranked marketplace. Each card shows its Certifier score and the evidence behind it.
2. **Choose what it may read.** Records outside your choice are marked *kept private*. The pack never sees them.
3. **Run it.** An honest pack reads, thinks (Nemotron), checks its own answer and returns a result.
   A malicious pack is caught, the run stops, and the console shows exactly what it tried.

Two of the demo packs are malicious on purpose. One tries to read records outside its lens. The other
ships real code that tries to open a socket, start a process and write outside its scratch space, all
from inside the sealed cell. Neither succeeds, and the Certifier flags both by behaviour.

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
bridge improve quick-skim      # propose better instructions, measured on a public dev suite
bridge approve quick-skim      # owner approval: publish the candidate, certify it on the held-out suite
pytest                         # 240 tests; the container tests are skipped if no engine is found
```

**Containers.** Code steps run in a container with no network. On Linux and macOS the default is
`docker`. On Windows the engine is reached through WSL (`wsl -d Ubuntu-22.04 -u root -- /usr/bin/docker`).
Set `BRIDGE_DOCKER` to use something else (for example `podman`). Without an engine, `bridge seed` still
works: packs that need a cell are published but left *uncertified*, and never shown as safe.

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
| Another website cannot start runs | Local bind, host check, per-process token | `tests/web/test_server.py` |

## Honest limits

- **Pull mode has no fair exchange.** The requester's machine runs the pack and could keep the output
  without paying. The payment design (a hold, a floor fee, dispute handling) limits the loss; it does not remove it.
  Payments are not part of this build yet.
- **Detection is evidence, not proof.** A slow leak of information inside the shared records, through the
  allowed output, may not trip anything. The guarantee is that the pack sees only what you shared and the
  output channel is bounded, not that detectors catch every theft.
- **The Certifier suite is small.** Three quality tasks plus a security trap. A pack with 3 of 3 passes scores
  lower than one with 28 of 30 on purpose. Scores say "evaluated on this suite", never "safe".
- **Improvement partly overfits the dev suite.** In our live run `quick-skim` moved from 0.30 to 0.61 on the
  public dev suite but only from 0.55 to 0.62 on the held-out suite.
- **The model is not perfectly stable.** Nemotron sometimes returns empty or malformed JSON. The client retries
  up to three times, and the Certifier does not count infrastructure failures against a pack.
- **Built in this repo:** the workflow engine, Memory Broker, Result Guard, sealed Cell, registry, Certifier,
  ranking, local console. **Designed, not built:** Hosted mode on someone else's machine, sealed enclaves,
  multi-device sync, key management, a real payment ledger, legal review. See `.scratch/agent-bridge/architecture-v2.1.md`.
- The "simulate a compromised model" switch in the console is a simulation. The code-based malicious pack is not.
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
