# agent-bridge: an agent can be paid per job, even on someone else's machine

PayPal AI. One line to remember: **Money committed first, settled by what the run did.**

Estimated voice: 3:23 as read, 2:49 after the 1.2x speed-up (limit 3:00). Scene pictures add a short pause between scenes, so expect about 2:58 in total. The real numbers come from the audio files.

| Scene | What it is | Voice (est., final) | Words |
|---|---|---|---|
| p01 The door you cannot lock | Animation (Claude Design) | 29s | 89 |
| p02 Money first | Animation (Claude Design) | 16s | 51 |
| p03 The ceiling | Screen recording (real console) | 20s | 62 |
| p04 The real price | Screen recording (real console) | 25s | 76 |
| p05 My call | Screen recording (real console) | 16s | 49 |
| p06 A full refund needs evidence | Animation (Claude Design) | 21s | 66 |
| p07 How authors charge | Screen recording (real console) | 20s | 63 |
| p08 A market for agents | Animation (Claude Design) | 22s | 69 |

## p01. The door you cannot lock

**Animation (Claude Design)**

**On screen:** A builder at a desk with an agent. Normal website: the agent works on the builder's server behind a door that stays locked until a coin arrives. Then agent-bridge: the agent works inside the customer's laptop; the result is already on the customer's side; the door has no lock. Text: and if builders cannot be paid, the best agents never get shared.

**Caption:** On the customer's machine, nothing can be locked.

**Voice (89 words):**

> Someone spends months tuning an AI agent until it's really good at one job. How do they get paid? On a normal website, that's easy. The work happens on your server, and you keep the door locked until the customer pays. But in our marketplace, agent-bridge, agents run on the customer's own computer, next to their private files. The work and the result are already on the other side of the door. You can't lock anything. And if builders can't get paid, the best agents never get shared.

## p02. Money first

**Animation (Claude Design)**

**On screen:** A coin icon marked 40 enters a PayPal-style hold above the laptop. The agent works. The result arrives. Part of the coin is captured, the rest released. A small tag: practice server that copies PayPal's API, test money.

**Caption:** Hold first. Settle after. Test money.

**Voice (51 words):**

> That leaves one lever: money committed before the work starts. PayPal can do that. It holds the money first, the agent does the work, and the real price is settled afterwards. We call these agents helpers. What you'll see runs on a practice server that copies PayPal's API, with test money.

## p03. The ceiling

**Screen recording (real console)**

**On screen:** A chat with a helper priced up to 40 cents. Send a question; the approval card shows 'hold of 40 cents'. Click to open the practice approval page, approve; the chat continues by itself. Caption on the card: the most this helper can charge.

**Caption:** I approve a hold of 40 cents. That's my ceiling.

**Voice (62 words):**

> Let me be the buyer. I ask a question, and PayPal asks me to approve a hold of forty cents, the most this helper can charge. I approve it on PayPal's page. The author never sees my card. They only give an email for payouts. That forty cents is my ceiling. The helper can't charge more, and nothing has been taken yet.

## p04. The real price

**Screen recording (real console)**

**On screen:** The run plays in the office. The answer arrives. Open the receipt: 3 files, 2 model calls, Standard, 25 cents; 15 cents released. A second small clip: a failed run releasing the whole hold.

**Caption:** 25 cents, not 40. The rest is released.

**Voice (76 words):**

> The helper works on my machine, and the money waits. If the run fails, the hold is released and I pay nothing. This one finished. It read three files and made two model calls, so it's a standard run: twenty-five cents. That's what the author earns if I accept. The other fifteen are released back to me. PayPal can capture part of a hold, and that's what lets the price be set after the work.

## p05. My call

**Screen recording (real console)**

**On screen:** On an answer, click Accept: receipt shows the author paid out. Another answer: click 'Not helpful': receipt shows only the small fee kept, the rest released.

**Caption:** Helped: author paid. Not helpful: small fee only.

**Voice (49 words):**

> Now it's my call. If the answer helped, I accept, and the author gets paid out through PayPal. If it didn't, I say so, and only a small fee is kept. The rest comes back to me. I can send most of it back, but never all of it.

## p06. A full refund needs evidence

**Animation (Claude Design)**

**On screen:** A state diagram draws itself: Result ready, Stopped, Hold kept, then two arrows from 'independent certifier': 'flagged' leads to Refunded, author earns nothing; 'not flagged' leads to Claim rejected, author keeps the fee. A hand tries to press cancel and is refused: my word alone is not evidence.

**Caption:** My word alone can't cancel a payment.

**Voice (66 words):**

> A full refund needs more than my word. Say a helper cheats and gets shut down mid-run. I can't just say so, because anyone could. So the money stays held until the certifier, our independent tester, has flagged that helper. If it has, I get everything back and the author earns nothing. If it hasn't, my claim is rejected and the author keeps the fee.

## p07. How authors charge

**Screen recording (real console)**

**On screen:** My helpers studio, Publish panel: the plan picker (flat, by files, by tokens, by complexity, monthly) with the preview of light, standard and deep. Then the wallet showing a monthly plan with answers left.

**Caption:** Flat, per file, per token, by complexity, or monthly.

**Voice (63 words):**

> Authors pick how to charge. One flat price, or a price that follows the work: files read, model calls, or whether the run was light, standard or deep. There's also a monthly plan that covers a set number of answers. It doesn't renew by itself, and it can be stopped. Before publishing, authors see what a light, standard or deep run would cost.

## p08. A market for agents

**Animation (Claude Design)**

**On screen:** A coin splitting: ceiling 40, price 25, released 15, small fee, payout to the author. Then a row of helpers each with a price tag, a buyer picking one. End card: agent-bridge, on PayPal. Test money.

**Caption:** 

**Voice (69 words):**

> That's what a market for agents needs. A builder gets paid per job, even when the agent runs on someone else's machine. I set the ceiling, the price follows the work, a bad result costs a small fee, and a proven cheat costs nothing. Anyone with a good agent can sell it, and anyone can hire one without trusting a stranger. That's agent-bridge, on PayPal, with test money.
