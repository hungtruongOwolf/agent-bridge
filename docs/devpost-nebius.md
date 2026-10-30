# Devpost text: Nebius x NVIDIA (Personal AI track)

Project name: **agent-bridge** (subtitle: bring the expert to your data). Paste each section into the matching Devpost field.
Fill the [bracketed] items yourself. Do not submit before you have read the official rules once more.

## Tagline

Bring the expert to your data.

## Requirements checklist

| Requirement | Where it is met |
|---|---|
| Runtime call to Nebius Token Factory API | `src/bridge/engine/nebius.py` calls `https://api.tokenfactory.nebius.com/v1/chat/completions` with `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` |
| NVIDIA open model | Nemotron 3 Nano 30B A3B |
| Public repo with an OSI licence | [REPO LINK], MIT |
| Working demo or test build | `pip install -e .`, `bridge seed`, `bridge serve` (README quickstart) |
| Video under 3 minutes | [YOUTUBE LINK] (2:54) |
| Tavily bonus | `src/bridge/engine/tavily.py`, a public web step in a helper that cannot read private data |
| Feedback section | See "Feedback for Nebius" below |

## Inspiration

The most useful things an AI agent could do are the things we cannot let it see: medical records, a company's accounts, private code.
Today you pick between uploading everything to someone else's cloud and doing without. There is a second problem too. You cannot tell
which agent is good. We measured it: the same model, NVIDIA Nemotron, the same sixteen questions, and three versions of one helper scored
9, 13 and 14 right. Only the setup around the model changed (its instructions and its checks), and from outside you cannot see a setup.

## What it does

agent-bridge flips the direction. In **Pull mode** the expert's setup (we call it a helper) comes to your machine. Its steps run there,
the model call uses your own Nebius key, and it sees only the shelves of your memory that you tick. Secret notes never leave, even if the
shelf is ticked. After every answer you can see which files were sent to Nemotron on Nebius Token Factory, how much text, and which emails
and phone numbers were swapped for placeholders before the call (and restored in the answer on your machine).

An independent **certifier** runs every helper on the same questions with the same Nemotron model and ranks them by score, not stars.
A helper that cheats is stopped in a sealed room with no network, nothing is delivered, and proven cheats are taken off the market.
Anyone can build a helper in the studio, set a price and sell it; buyers pay per use (test money in this demo).

## How we built it

- **Workflow engine** (`flowd`): a small closed language (tool, model call, code, gate, return); every step goes into a hash-chained journal.
- **Memory Broker**: the only way a helper reads your notes; it stages records from the shelves you ticked, counts every read and plants decoys that only off-lens queries can reach.
- **Result Guard**: bounds the only exit (schema, size, decoy values, verbatim copies of your records); schemas that allow unbounded text are rejected at publish.
- **Sealed Cell**: code a helper brings runs in a container with no network, a read-only filesystem and no capabilities.
- **Inference**: NVIDIA Nemotron on Nebius Token Factory. A masker replaces emails, phone and account numbers with placeholders before the call.
- **Web**: Tavily, allowed only in steps that cannot read private data; the platform checks this before a helper is published.
- **Certifier**: same questions, same model, Wilson lower-bound scoring, signed results, a security trap; hard evidence in a live run revokes the helper.
- **Console**: a pixel-art market floor that replays each run's real record, a memory library with shelves, a studio to build and price helpers.

## Challenges

- Making "the helper cannot send anything out" a property of the runtime, not a promise: we went through two designs before a closed language plus a no-network container.
- Being honest about the model service: it does read what a helper's steps send it. We show exactly what was sent, mask what we can, and say what we cannot do.
- Nemotron reasons in a hidden field and can use its whole token budget before answering, which looked like empty replies. We found it by reading `finish_reason`, turned thinking off, retried, and made the certifier ignore infrastructure failures.
- Honest evaluation: our first suite gave every helper full marks. A harder suite spread them.

## Accomplishments

- Three versions of one helper, same Nemotron, same sixteen questions: 9, 13, 14 right. The ranking shows setups, not models.
- A helper with real malicious code is stopped live, and a second one that reaches for a bait note is caught by behaviour.
- About 660 automated tests, and a README quickstart from a clean clone.

## What we learned

A marketplace for agents only works if quality is measured independently, and privacy only works if it is a property of where the code runs,
not of a promise. The safe design is the boring one: a small language the platform can reason about beats a flexible one it cannot.

## What's next

Hosted mode on someone else's machine, sealed enclaves, multi-device memory, and verified PayPal sandbox payments.

## Honest limits

- The model service reads what a helper's steps send it (minus placeholders). Information already shown to a helper cannot be taken back.
- Detection is evidence, not proof. A slow leak through allowed output may not trip anything.
- The certifier suite is small. Scores say "evaluated on this suite", never "safe".
- Pull mode has no fair exchange: the buyer's machine could keep an output without paying. Payments limit the loss; they do not remove it.
- Payments in the demo are test money only.

## Built with

Python, NVIDIA Nemotron, Nebius Token Factory, Tavily, Docker, Ed25519 (cryptography), JSON Schema, PyYAML, JavaScript.

## Feedback for Nebius (Most Valuable Feedback)

Based on what we observed, not guesses:

- `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` and `nvidia/nemotron-3-super-120b-a12b` called a single tool correctly 5 of 5 times at temperature 0.
- We saw chat completions with empty `content`. Nemotron writes reasoning to a separate field and can hit `max_tokens` (`finish_reason: "length"`) before it writes an answer. With `max_tokens` 1200 about half of our calls were empty on one prompt. `chat_template_kwargs: {"enable_thinking": false}` gave complete answers in about 40 completion tokens instead of 300 to 1,200. We did not find this in the model card or API reference; documenting the switch next to the model would have saved us a day.
- Turning thinking off changes quality, so scores are only comparable at the same setting.
- Identical prompts at temperature 0 did not always return identical answers, so measurements needed several runs per task.
- The OpenAI-compatible endpoint made integration quick. Per-model guidance on JSON-mode reliability would help.
- We could not find speech models in the catalogue; a voice front end would need another provider.
