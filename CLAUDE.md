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
