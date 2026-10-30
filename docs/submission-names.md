# Two submissions, two angles (names, taglines, video text)

Same repo and same code, but each hackathon gets its own name and its own story, so the two entries do not read as copies.
Paste these into Devpost and YouTube. Thumbnails: `docs/video/thumbnails/thumb-nebius.png`, `thumb-paypal.png` (1920x1080).

## Nebius x NVIDIA

- **Project name:** agent-bridge (subtitle: bring the expert to your data)
- **Tagline (under 60 chars):** The expert's setup runs on your machine, not the other way round.
- **Short description:** Your most useful files are the ones you cannot upload. In Pull mode an expert's agent setup runs on your own
  machine, reads only the shelves of memory you tick, and thinks with NVIDIA Nemotron on Nebius Token Factory using your own key.
  An independent certifier scores every setup on the same questions with the same model (the same Nemotron went from 9 to 14 of 16
  with only the setup changed), and a helper that cheats is stopped in a sealed room.
- **Focus of the write-up:** data safety, the Memory Broker, what was sent to the model (and placeholders), the certifier, the sealed cell.
- **YouTube title:** Bring the expert to your data: agent-bridge Pull mode (Nebius x NVIDIA)
- **YouTube description:** Same model, three setups, 9 vs 14 of 16 right. agent-bridge runs an expert's agent setup on your machine,
  on the memory shelves you open, with NVIDIA Nemotron on Nebius Token Factory. Built for the Nebius x NVIDIA hackathon.
  Code: [REPO LINK] (MIT). Payments in the demo use test money.

## PayPal AI

- **Project name:** Payceiling: agents paid per job, even on your machine  (alternatives: Runfee, Settled)
- **First line of the description:** Built on the open-source agent-bridge platform.
- **Tagline (under 60 chars):** Get paid per job, even when the agent runs on your PC.
- **Short description:** An agent running on the buyer's machine cannot lock its result, so the only lever left is money committed
  first. The buyer approves a PayPal hold (the ceiling, 40 cents in the demo); when the run ends the real price is captured
  (25 cents for a standard run), the rest is released, "not helpful" keeps only a small fee, and a full refund needs the certifier's
  evidence. Authors choose flat, per-file, per-token, by-complexity or monthly pricing. Built on a practice server that copies
  PayPal's API; test money only.
- **Focus of the write-up:** authorize, partial capture, void, refund, payout; the dispute rule; the five pricing plans; idempotency and recovery.
- **YouTube title:** Paid per job, even on someone else's machine: agent-bridge Pay (PayPal AI)
- **YouTube description:** A market for agents needs a way to pay builders when the work happens on the customer's computer.
  agent-bridge holds the money first with PayPal and settles by what the run did. Test money on a practice server that copies
  PayPal's API. Built for the PayPal AI hackathon. Code: [REPO LINK] (MIT).

## Keep apart

- Nebius entry: do not lead with payments; mention PayPal only as "buyers pay per use, test money".
- PayPal entry: do not lead with Nemotron or the memory shelves; the privacy design is context, the money flow is the story.
- Disclose in both that the repo is shared, and that payments were verified on the practice server, not the live PayPal sandbox
  (unless that changes before 11-11).
