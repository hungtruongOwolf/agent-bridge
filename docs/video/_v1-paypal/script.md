# agent-bridge: agents that pay agents, on evidence

PayPal AI (Agentic Commerce). One line to remember: **Agents that pay agents, on evidence.**

Estimated voice: 2:12 as read, 1:50 after the 1.2x speed-up (limit 3:00). Scene pictures add a short pause between scenes, so expect about 2:02 in total. The real numbers come from the audio files.

| Scene | What it is | Voice (est., final) | Words |
|---|---|---|---|
| p01 Who pays? | Animation (Claude Design) | 10s | 31 |
| p02 The product in one breath | Screen recording (real console) | 10s | 32 |
| p03 Hire and hold | Screen recording (real console) | 12s | 36 |
| p04 The floor fee | Screen recording (real console) | 8s | 25 |
| p05 Accept and pay | Screen recording (real console) | 12s | 36 |
| p06 Not helpful | Screen recording (real console) | 7s | 23 |
| p07 Five ways to charge | Screen recording (real console) | 12s | 36 |
| p08 When an agent cheats | Animation (Claude Design) | 13s | 40 |
| p09 Built to be safe to repeat | Terminal recording (real command) | 13s | 39 |
| p10 Close | Animation (Claude Design) | 15s | 45 |

## p01. Who pays?

**Animation (Claude Design)**

**On screen:** An agent icon hands a task to another agent icon. A coin hovers between them with a question mark; a thumbs-down and a mask (cheating) appear. Title: money that follows evidence, not trust.

**Caption:** Money that follows evidence, not trust.

**Voice (31 words):**

> Soon, your AI agent will hire other agents. So who pays? And what happens when the work is bad, or the agent cheats? Agents need money that follows evidence, not trust.

## p02. The product in one breath

**Screen recording (real console)**

**On screen:** The market floor with stalls; quick pan over the market square and the coins chip.

**Caption:** A marketplace where agents run on your machine.

**Voice (32 words):**

> This is agent-bridge: a marketplace where you rent someone else's agent, and it runs on your machine, seeing only the notes you choose. Now let us make it a real transaction.

## p03. Hire and hold

**Screen recording (real console)**

**On screen:** New chat with Private Analyst, tick Work > Accounts, send 'Which accounts are at risk?'. The approval card appears; click 'Open the approval page', approve in the second tab; the chat continues by itself.

**Caption:** A hold, not a charge.

**Voice (36 words):**

> I ask a helper a question. First, it asks me to approve a hold for its price: forty cents. Nothing is charged yet. I approve on the payment page, and the chat carries on by itself.

## p04. The floor fee

**Screen recording (real console)**

**On screen:** The small office plays the run; the answer arrives; click the Coins chip to show 'On hold' and the floor fee captured.

**Caption:** Answer delivered: a floor fee is captured.

**Voice (25 words):**

> The helper does the work on my machine. Now there is an answer, so a small floor fee is captured. The rest stays on hold.

## p05. Accept and pay

**Screen recording (real console)**

**On screen:** Send a second message. Open the receipts: the first payment is Paid, with the author's payout less the platform fee and each step in plain words.

**Caption:** Keep going = accept. The author is paid less the platform fee.

**Voice (36 words):**

> When I send my next message, I am saying the last answer was good enough. The rest is paid, and the author is paid less the platform fee. Every step is written down in plain words.

## p06. Not helpful

**Screen recording (real console)**

**On screen:** On an answer, click 'Not helpful'. Open the receipt: 'You said not helpful: deposit only', the rest released.

**Caption:** Not helpful: deposit only.

**Voice (23 words):**

> If an answer is not helpful, I say so. The author keeps only the deposit, and the rest is released back to me.

## p07. Five ways to charge

**Screen recording (real console)**

**On screen:** My helpers > Publish tab. Click through the five plan cards: One price, By files read, By thinking used, By how hard the question was, Monthly plan. Show the live price preview.

**Caption:** One hold, the real price.

**Voice (36 words):**

> Authors choose how to charge: one price, by files read, by tokens used, by how hard the question was, or a monthly plan. The hold is always the maximum, and I only pay the real price.

## p08. When an agent cheats

**Animation (Claude Design)**

**On screen:** A state diagram draws itself: Result ready, Stopped, Hold, Evidence from independent testers, then Refunded and Author earns nothing. A hand tries to press cancel and is refused: my word alone is not evidence.

**Caption:** A claim holds the money. Evidence decides.

**Voice (40 words):**

> What if the agent cheats? My word alone cannot cancel a payment, because I could lie. So the money waits for evidence. If independent testers have already reproduced that exact cheating, the hold is refunded and the author earns nothing.

## p09. Built to be safe to repeat

**Terminal recording (real command)**

**On screen:** Terminal: pytest tests/payments -q, ending with the passing count. Overlay three captions as lines scroll: idempotent calls, one lock decides, crash recovery.

**Caption:** Tested: repeats, races, crashes.

**Voice (39 words):**

> Underneath, every payment call is safe to repeat, so a lost reply never charges twice. Accepting and stopping cannot both win. A crash in the middle is recovered from a written record. These are tested, including a race test.

## p10. Close

**Animation (Claude Design)**

**On screen:** End card: logo, 'Agents that pay agents, on evidence.', repo link, badges: PayPal, Nemotron, Nebius, MIT. A small honest line: Test money only.

**Caption:** Open source, MIT. Test money only.

**Voice (45 words):**

> We are honest about one gap: someone running an agent locally could keep its output without paying. The floor fee, the held dispute and the testers limit that loss. They do not remove it. agent-bridge is open source. Agents that pay agents, on evidence.
