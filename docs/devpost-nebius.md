# Devpost text: Nebius x NVIDIA (Personal AI track)

Paste into the Devpost form. Fill the bracketed items yourself. Do not submit before you have read the official
rules once more (we only keyword-searched them for multi-hackathon reuse).

## Tagline

Rent a stronger agent. Keep your data.

## Requirements checklist

| Requirement | Where it is met |
|---|---|
| Runtime call to Nebius Token Factory API | `src/bridge/engine/nebius.py` calls `https://api.tokenfactory.nebius.com/v1/chat/completions` with `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` |
| NVIDIA open model | Nemotron 3 Nano 30B A3B |
| Public repo with an OSI licence | [REPO LINK], MIT |
| Working demo or test build | Clone, `pip install -e .`, `bridge seed`, `bridge serve` (README quickstart, verified from a clean clone) |
| Video under 3 minutes | [YOUTUBE LINK] |
| Tavily bonus | `src/bridge/engine/tavily.py`, a public web step in the `context-brief` pack; live call verified |
| Feedback section | See "Feedback" below |

## Inspiration

No single agent setup is best at everything, and you cannot borrow someone else's without handing them your data. A
personal AI is only as useful as the context it can read, so the real question is how to let a stranger's agent
work on your context without letting it keep or send any of it.

## What it does

agent-bridge is a marketplace of agent + harness packs. A pack is a signed workflow. You run it on your own machine in a sealed
run: it reads only the records you choose to share, it has no network, and any attempt to take something it was not given stops
the run and delivers nothing. Packs are scored by a Certifier on a hidden suite, including a security trap, and ranked by evidence.
Packs can suggest things to remember, but nothing enters your memory unless you accept it, and a whole run can be undone.

## How we built it

- **Workflow engine** (`flowd`) runs a small closed language: `tool`, `llm`, `code`, `gate`, `return`. Every step is journaled in a hash chain.
- **Memory Broker** stages a closed set of records from the lens you approve, counts every read, and plants decoy records that are served only
  to off-lens queries. Touching a decoy ends the run.
- **Sealed Cell**: pack code runs in a container with no network, a read-only filesystem and no capabilities. An in-cell sensor records
  attempts to use the network, start a process or write outside scratch space.
- **Result Guard** bounds the only exit: schema, size, decoy values, verbatim copies of your records.
- **Quarantine** holds a pack's memory suggestions until you accept them; accepted records carry an immutable origin.
- **Inference** is NVIDIA Nemotron on Nebius Token Factory with bounded retries. **Web** is Tavily, allowed only in steps that cannot read your data.
- **Certifier and ranking**: three quality tasks plus a security trap, Wilson lower-bound scores, signed attestations. Stars cannot buy rank.
- **Improvement loop**: Nemotron proposes better instructions, scored on a public dev suite, a typed diff proves only the text changed, the owner approves.

## Challenges

- Making "the pack cannot send anything" a property of the runtime, not a promise. We went through two designs before settling on a
  closed language plus a no-network container.
- Honest evaluation. Our first suite gave every pack 3 of 3. A harder suite with a "no false alarm" task spread them from 0.39 to 0.76.
- Model behaviour: Nemotron reasons in a hidden field and can use its whole token budget before answering, which looked like empty replies. We found it by reading `finish_reason`, turned thinking off, and made the client retry and the Certifier ignore infrastructure failures.

## Accomplishments

- A malicious pack with real code is caught live, and the Certifier flags it by behaviour.
- A measured improvement on a held-out suite (`deal-brief` 0.39 to 0.55, after 0.35 to 0.57 on the dev suite; measured on the earlier, harder suite and pack versions, before the packs became chat-aware), with the overfitting stated rather than hidden.
- 240 automated tests, and a clean-clone check of the quickstart.

## What we learned

Evaluation design decides whether a marketplace ranks quality or noise. And the safe design is the boring one: a small language the platform
can reason about beats a flexible one it cannot.

## What's next

Payments with a hold and dispute handling (PayPal sandbox), Hosted mode on someone else's machine, multi-device memory sync, loops and resume in the workflow engine.

## Honest limits

Pull mode has no fair exchange. Detection is evidence, not proof. The Certifier suite is small, and the improvement loop partly overfits its
dev suite. Hosted mode, payments, key management and legal review are designed, not built.

## Built with

Python, NVIDIA Nemotron, Nebius Token Factory, Tavily, Docker, Ed25519 (cryptography), JSON Schema, PyYAML.

## Feedback for Nebius (Most Valuable Feedback)

Based on what we observed, not guesses:

- `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` and `nvidia/nemotron-3-super-120b-a12b` called a single tool correctly 5 of 5 times at temperature 0.
- We saw chat completions with empty `content`. The cause: Nemotron writes its reasoning to a separate `reasoning` field and can hit `max_tokens`
  (`finish_reason: "length"`) before it writes an answer. With `max_tokens` 1200 about half of our calls were empty on one prompt. Passing
  `chat_template_kwargs: {"enable_thinking": false}` gave complete answers in about 40 completion tokens instead of 300 to 1,200. We did not find
  this in the model card or the API reference; documenting the switch next to the model would have saved us a day.
- Turning thinking off changes quality: several multi-step packs scored lower, which is useful signal but means scores are only comparable at the same setting.
- Identical prompts at temperature 0 did not always return identical answers, so pass-rate measurements needed several runs per task.
- The model catalogue is clear and the OpenAI-compatible endpoint made integration quick. It would help to see per-model guidance on JSON-mode reliability.
- We could not find speech models in the catalogue; a voice front end would need another provider.
