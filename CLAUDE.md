# agent-bridge

Part of a hackathon hub. Shared context: `../HACKATHONS.md` (targets, deadlines, decisions).

## Where context lives
- Spec: `.scratch/agent-bridge/spec.md`
- Tickets: `.scratch/agent-bridge/issues/NN-<slug>.md` (each has a `Status:` line)
- To resume work: read the spec, then open tickets whose Status is not resolved; take the lowest number that is unblocked.

## Hand-off log
Update this section whenever you stop working. One line per entry: date, what changed, what's next.

- (empty)
- 2026-10-03: planning only. decisions in agent-bridge/.scratch/decisions.md. Next: finish grilling, then /to-spec and /to-tickets.
- 2026-10-20: built vertical slice (code, 138 tests): pack workflow parser, digest, signing, Memory Broker with decoy canaries, Result Guard, flowd engine + journal, Docker Cell (no network, via WSL), Nebius Nemotron client, registry, Certifier + ranking, web console (`bridge seed`, `bridge serve`). Spikes: Nemotron tool calling OK, no-NIC Cell OK. Repo: github.com/hungtruongOwolf/agent-bridge (private). Next: more packs, Tavily public step, PayPal sandbox, README/demo script, make repo public before 30/10 submission. No spec.md/tickets yet (design lives in .scratch/agent-bridge/architecture-v2.1.md).
- 2026-10-20 (later): M1 and M2 done, M3 done on test money, M4 docs written. Code: 312 tests. Built since the first slice: memory write path (quarantine, accept, revert), Tavily public step, Cell sensor, harder Certifier suite, improvement loop (`bridge improve` / `approve`), run history and audit view, payment ledger + fake provider + PayPal sandbox client (UNVERIFIED live), approval step. Docs: README, docs/architecture.md, demo scripts and Devpost texts for both hackathons. Tickets 01-07, 09 (except public flip), 12-14 resolved; 08, 10, 15, 16 ready-for-human; 11 waits for PayPal sandbox credentials. Next for the owner: confirm making the repo public, record both videos, provide PayPal sandbox credentials, submit Nebius by 2026-10-29 and PayPal by 2026-11-11.

