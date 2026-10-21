# 0003 - Close the exits instead of detecting leaks

Status: accepted (2026-10-21)

## Context

A helper is code we do not trust. It needs the user's records to be useful, and its answer has to come back. Nobody can
detect every leak, so the design question is: *where can information leave at all, and can each door be closed or bounded?*

In Pull mode the helper runs on the requester's machine. The author is **not** a recipient: nothing the helper computes is
sent to the author. That shrinks the problem to a short list of exits. Everything below was checked against the code on
2026-10-21.

## The exits

| # | Exit | Who could receive data | Control | State |
|---|---|---|---|---|
| 1 | Web query (Tavily) | the search service, then anyone who can read its logs | A web step is *public*: it may not touch memory or read any step that did (static check at parse time). Runtime check refuses a query that repeats 25+ characters of a staged record. The query is journaled. | **Hole found and fixed**: a memory step that did not write `memory: lens` was not marked private, so its records could reach a web query through a plain llm step. Memory tools are now private by what they *do*, not by what they declare. The approval card reports memory use the same way. |
| 2 | Model call (Nebius) | the model provider | Only the requester's own key and endpoint; steps see only the outputs they `reads`. | Not yet shown to the user: the journal keeps tokens, not what was sent. Next. |
| 3 | The answer | the requester (and what they do with it) | Schema, size cap, canary and verbatim-copy scan in the Result Guard. The console draws answers as text only (no HTML, no remote images, no links built from answers), so rendering an answer cannot call anyone. | Free-text fields have no length bound unless the author writes one. Next. |
| 4 | Memory suggestions | the requester's own memory | Quarantine: nothing is written until the user accepts; copies of records are dropped. | Done. |
| 5 | Code steps | none | Cell: no NIC, read-only disk, audit hook, any probe ends the run as KILLED. | Done. |
| 6 | Payment amounts | the ledger | Prices come from the plan and the journal, not from the helper. A few bits at most. | Accepted. |
| 7 | Later steps in the same chat | other helpers | `history` is private data; a web step cannot read it. Suggestions pass through quarantine. | Done. |

## What the design guarantees, and what it does not

- **By construction:** a helper cannot choose what to look up (queries come from the user's message or from fixed text in
  the pack), cannot reach the network, and cannot send private data to a public step.
- **Bounded and shown:** what a helper may put into its answer (schema + size) and what went to the model provider.
- **Not preventable:** the model provider reads the prompt of every llm step; information already shown to a helper cannot
  be taken back. The console says so, and for the second case tells the user what to change.

## Consequences

- `pack.workflow.reads_memory(step)` is the single definition of "touches the user's records"; scope check and
  capabilities both use it.
- A cheating pack that skips the declaration still parses (the Certifier must be able to run and catch it) but can no
  longer smuggle records into a public step.
