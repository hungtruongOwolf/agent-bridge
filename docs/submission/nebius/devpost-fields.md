# agent-bridge (Nebius x NVIDIA): what to paste into each Devpost field

Project name: **agent-bridge** (subtitle: bring the expert to your data). Order on the form: Project overview, **About the project** (story below), **Built with**, **Try it out links**, **Image gallery**, **Video**, then Additional info.

Before pasting:
1. The GitHub repo must be **public** (story images load from `raw.githubusercontent.com/.../main/docs/submission/nebius/...`; until it is public they show as broken links).
2. Upload the video to YouTube (public or unlisted) and put the link where `[YOUTUBE LINK]` appears.
3. If the form has a demo URL field, use `[DEMO URL after deploy]` (the static replay in `demo-site/`, once you have deployed it) or `https://github.com/hungtruongOwolf/agent-bridge#quickstart`.

---

## Project overview

- Project name: `agent-bridge: bring the expert to your data` (43 characters, fits a 60 limit)
- Elevator pitch (under 200 characters): `Run an expert's AI agent on your own machine, on the memory shelves you open, with NVIDIA Nemotron on Nebius. Independent scores rank agents; a cheat is stopped in a sealed room.`

---

## 1. About the project (paste everything between the two lines)

---
## Inspiration

The most useful things an AI agent could do are the things we can't let it see: your medical records, your company's accounts, your private code.

![The best help wants your most private files. Today you choose: upload everything, or do without.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/nebius/story/nd1-problem.png)

So today you pick. Upload everything to someone else's cloud and hope, or keep it safe and do without the help. Either way, the work that matters most is the work the best agents never touch.

There is a second problem, and it surprised us. **You can't tell which agent is good.** We measured it. One helper, the same model (NVIDIA Nemotron), the same sixteen questions, three versions: **9, 13 and 14 right.** Only the setup around the model changed: its instructions and its checks. From the outside you can't see a setup, so you choose blind, and to try one you have to hand over your data.

![Same model, three setups: 9, 13 and 14 right out of 16.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/nebius/story/nd2-same-model.png)

## What it does

agent-bridge flips the direction. In **Pull mode** the expert's setup (we call it a *helper*) **comes to your machine**. Its steps run there, the model call uses your own Nebius key, and it only sees what you open for it.

![Pull mode: memory shelves, the broker, the sealed room, Nemotron on Nebius.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/nebius/story/nd3-pull-mode.png)

- **You tick the shelves.** My memory is a library of about 140 notes on shelves. Before you hire a helper you tick the shelves it may read. A **secret** note stays home even if you tick its shelf.
- **A gatekeeper, not a search box.** The helper can't search your notes. The **memory broker** hands it only what is on the shelves you ticked, counts every read, and plants decoys that only an out-of-bounds query could reach.
- **Nemotron on Nebius Token Factory does the thinking**, with your key, which the helper never sees.
- **You see what left.** Every answer lists the notes it used, which files were sent to the model and how much text. Emails, phone numbers and account numbers are swapped for placeholders before the model call and put back in the answer on your machine.
- **Independent scores, not stars.** A **certifier** runs every helper on the same questions with the same Nemotron model and ranks them. A helper with 14 right ranks above one with 9.
- **A cheat is stopped in a sealed room.** Code a helper brings runs with no network, a read-only disk and no extra powers. In our tests a helper that tried to send my data out was killed with nothing delivered, and so was one that reached for a bait note I never shared. Hard evidence in a live run takes the helper off the market at once.
- **Anyone can sell a setup.** In the studio you arrange the steps, set a price and publish. Before it goes on sale the platform checks that its web lookups can't read private data. Buyers pay per use, with test money in this demo, and the author never sees their notes.

![Independent scores, and a room a cheat can't leave.](https://raw.githubusercontent.com/hungtruongOwolf/agent-bridge/main/docs/submission/nebius/story/nd4-trust.png)

Imagine a helper for your tax papers, one for your contracts, one that reads your whole codebase. The same room and the same rules, whatever is on your shelves.

## How we built it

- **Workflow engine (`flowd`).** A small closed language (tool, model call, code, gate, return). Every step goes into a hash-chained journal, so what happened can't be quietly rewritten.
- **Memory broker.** The only way a helper reads notes; stages records from ticked shelves, counts reads, serves decoys to off-lens queries.
- **Result guard.** Bounds the only exit: schema, size, decoy values, verbatim copies of your records. Schemas that allow unbounded text are rejected when a helper is published.
- **Sealed cell.** Code steps run in a Docker container with no network, a read-only filesystem and no capabilities, with a sensor that records attempts to use the network, start a process or write outside scratch space.
- **Inference.** NVIDIA Nemotron (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) on Nebius Token Factory, with bounded retries, and a **masker** that replaces emails, phone numbers and account numbers with placeholders before the call.
- **Web (Tavily bonus).** Tavily lookups are allowed only in steps that can't read private data; the platform checks that before a helper can be published.
- **Certifier.** Same questions, same model, Wilson lower-bound scoring (a helper that passes 3 of 3 scores lower than one that passes 28 of 30, on purpose), signed results and a security trap.
- **Console.** A pixel-art market floor where each chat is a stall, a memory library, and a studio where you draw a helper as a picture and publish it.

## Challenges

- **Making "the helper can't send anything out" a property of the runtime, not a promise.** We went through two designs before settling on a closed language plus a no-network container.
- **Being honest about the model service.** The model service does read what a helper's steps send it. We can't change that, so we show exactly what was sent, mask what we can, and say what we can't.
- **Nemotron's empty replies.** Nemotron reasons in a hidden field and can use its whole token budget before it answers, which looked like empty replies. We found it by reading `finish_reason`, turned thinking off (complete answers in about 40 tokens instead of 300 to 1,200), retried, and made the certifier ignore infrastructure failures.
- **Honest evaluation.** Our first suite gave every helper full marks. A harder suite spread them out.

## Accomplishments

- A measurable result: three versions of one helper, the same Nemotron, the same sixteen questions, scoring 9, 13 and 14. The ranking shows setups, not models.
- A helper with real malicious code is stopped live, and a second one that reaches for a bait note is caught by behaviour.
- About 660 automated tests, and a README quickstart.

## What we learned

A marketplace for agents only works if quality is measured independently, and privacy only works if it is a property of *where the code runs* and not a promise. The safe design is the boring one: a small language the platform can reason about beats a flexible one it can't.

## What's next

Hosted mode on someone else's machine, sealed enclaves, multi-device memory, and verified PayPal sandbox payments.

## Honest limits

- The model service reads what a helper's steps send it (minus placeholders). Information already shown to a helper can't be taken back.
- Detection is evidence, not proof. A slow leak through allowed output may not trip anything.
- The certifier suite is small. Scores say "evaluated on this suite", never "safe".
- Pull mode has no fair exchange: the buyer's machine could keep an output without paying. Payments limit the loss; they don't remove it.
- Payments in the demo are test money only.

**Demo video:** [YOUTUBE LINK]
---

## 2. Built with (plain text, space separated)

```
python nvidia-nemotron nebius-token-factory tavily docker javascript html5 css json-schema pyyaml cryptography ed25519 ai-agents privacy sandbox
```

## 3. Try it out links

- `https://github.com/hungtruongOwolf/agent-bridge` (code, MIT licence, README quickstart)
- `[YOUTUBE LINK]` (2:54 demo video)
- `[DEMO URL after deploy]` (static replay, once deployed)

## 4. Image gallery (3:2, upload in this order; the first is the cover)

All in `docs/submission/nebius/gallery/` (1920 x 1280).

| # | File | Shows |
|---|---|---|
| 1 | `ng01-cover.png` | Cover: "Bring the expert to your data", same model 9 to 14 of 16 |
| 2 | `ng02-shelves.png` | Memory shelves, "Secret: never shared" |
| 3 | `ng03-what-went.png` | "What went to the model": files sent to Nebius Token Factory |
| 4 | `ng04-placeholders.png` | Placeholders, restored on my machine |
| 5 | `ng05-ranking.png` | Ranked helpers; a cheat flagged for everyone |
| 6 | `ng06-market.png` | The market floor |
| 7 | `ng07-studio.png` | The studio: arrange steps, set a price, publish |

The story uses different pictures (the four diagrams in `story/`).

## 5. Feedback for Nebius ("Most Valuable Feedback" field, if the form has one)

Based on what we observed, not guesses:

- `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` and `nvidia/nemotron-3-super-120b-a12b` called a single tool correctly 5 of 5 times at temperature 0.
- We saw chat completions with empty `content`. Nemotron writes reasoning to a separate field and can hit `max_tokens` (`finish_reason: "length"`) before it writes an answer. With `max_tokens` 1200 about half of our calls were empty on one prompt. `chat_template_kwargs: {"enable_thinking": false}` gave complete answers in about 40 completion tokens instead of 300 to 1,200. We did not find this in the model card or API reference; documenting the switch next to the model would have saved us a day.
- Turning thinking off changes quality, so scores are only comparable at the same setting.
- Identical prompts at temperature 0 did not always return identical answers, so measurements needed several runs per task.
- The OpenAI-compatible endpoint made integration quick. Per-model guidance on JSON-mode reliability would help.
- We could not find speech models in the catalogue; a voice front end would need another provider.

## 6. Additional info (answers, if the form asks the same questions as the PayPal one)

| Question | Answer |
|---|---|
| New, or existed before the start date? | New. First commit 2026-10-20. (CONFIRM against this hackathon's start date on the form.) |
| Requirement: Nebius Token Factory API at runtime | Yes: `src/bridge/engine/nebius.py` calls `https://api.tokenfactory.nebius.com/v1/chat/completions` with `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` for every helper's model step and for the certifier. |
| NVIDIA open model | NVIDIA Nemotron 3 Nano 30B A3B |
| Bonus: Tavily | Used: `src/bridge/engine/tavily.py`, a public web step in a helper that can't read private data (live call verified). |
| Repo | `https://github.com/hungtruongOwolf/agent-bridge` (MIT) |
| AI tools used to build it | Claude Code (Anthropic Claude) for most of the code, tests, docs and video tooling, with the owner directing and reviewing; ElevenLabs for the voice-over. In the product: Nemotron on Nebius. (CONFIRM.) |
| Testing instructions | Needs a Nebius Token Factory key and a Tavily key in `.env` (see `.env.example`): clone, `pip install -e ".[dev]"`, `bridge seed` (a few minutes), `bridge serve`, open http://127.0.0.1:8787. No-key check: `pytest tests/payments -q` (80 tests) and the 2:54 video. (CONFIRM from a clean clone before pasting.) |
