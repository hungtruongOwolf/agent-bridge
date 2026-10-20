# agent-bridge

A marketplace of **agent + harness** packs. Owners publish a pack with a price; requesters run it
on their own machine (Pull mode) or on someone else's (Hosted mode).

The hard problem is trust: a third-party pack must be able to *read* the data it is granted,
but nothing may be *sent* to it, and any sign of context or memory theft must stop the run.

## Status

Early. Design is written, code is being built in small steps.

- Design: [`.scratch/agent-bridge/architecture-v2.1.md`](.scratch/agent-bridge/architecture-v2.1.md)
- Harness as a workflow: [`.scratch/agent-bridge/design-harness-workflow.md`](.scratch/agent-bridge/design-harness-workflow.md)
- State machines: [`.scratch/agent-bridge/design-state-machines.md`](.scratch/agent-bridge/design-state-machines.md)

## License

MIT, see [LICENSE](LICENSE).
