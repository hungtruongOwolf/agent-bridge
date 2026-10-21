# Console design plan: the agent office

This replaces the first plan (a technical schematic). That version was readable by developers and by nobody else, and it ignored the
reference UIs the project owner had already chosen. This one is for ordinary people and follows those references.

## References, and what we take from each

| Reference | Taken from it |
|---|---|
| munder-difflin (HarnessMD, MIT) | The whole visual language: an office floor where each agent is a small character at a desk, letters that fly between desks, status badges on characters, cream panels with ink borders and hard shadows, pixel headings (Press Start 2P) over a readable body face (Inter), one accent colour per character. Its `DESIGN.md` principles: pixel-snapped, chunky, information through motion, limited palette, short human copy. Colour values and fonts are reused with attribution (see `NOTICE`). Characters and buildings are drawn by our own code. |
| PersonalJarvis | Talking to an assistant instead of filling forms: "hire the best one". Voice may browse and choose; **paying stays a button press**, as in its own risk levels (ask-level actions need a human). A typed box works the same as the microphone. |
| OpenClaw / ClawHub | The marketplace shape: ranked agents with stars (here "fans"), versions, and a trust score from verified checks. |

## Audience and job

Someone who is not a developer and wants a helper to do a job with some of their private files, without the helper being able to keep or leak them.
Every word on screen is plain language. No "broker", "sidecar", "digest", "hash", "lens" or "journal".

## The idea in one picture

You are the boss in your office. Your private files are in a **safe with labelled drawers**. A hired helper works in a **glass room**: you can see
everything, and it cannot reach out. A **security guard** checks everything that leaves the room. Your **assistant** carries letters to the
**Brain** (the model), the **Web library** and the **Bank**. The helper never leaves the room and never touches a phone.

```
┌─ Agent Bridge ───────── Tell your assistant… [mic] ───────────── test coins ─┐
├────────────┬───────────────────────────────────────────┬─────────────────────┤
│ 1 Who      │ ┌ Your office ┐ ┌ Glass room ─┐  Guard    ┌Brain ┐              │ Job status          │
│   to hire  │ │ safe ▤▤▤▤   │ │  helper     │ ▶ desk    │      │              │ Report              │
│ 2 What     │ │ you @ desk  │ │   at desk   │           │Library│              │ Coins               │
│   they may │ └─────────────┘ └─────────────┘  assistant │ Bank │              │ Remember this?      │
│   look at  │  what is happening right now (caption)                          │ Past jobs           │
│ 3 [Start]  │                                                                 │                     │
└────────────┴───────────────────────────────────────────┴─────────────────────┘
```

## What moves, and what it means

| On the floor | In plain words | Underneath |
|---|---|---|
| Coins fly into the jar by your desk | Your money is on hold, nothing is paid yet | hold on the payment provider |
| Guard checks a badge, the helper walks in | Its signature is genuine | pack signature and digest check |
| Drawers open, folders fly to the helper's desk | It was given only the files you chose | memory read through the lens |
| Padlocked drawer shakes, guard says no | It asked for something private and was refused | blocked off-lens read |
| Assistant carries a letter to the Brain | The helper is thinking (through the assistant, never directly) | model call from the sidecar |
| Paper plane bounces off the glass | Its code tried to send something out and could not | network attempt blocked in the cell |
| Guard stamps the report and it slides to your desk | The result passed inspection | result guard released the answer |
| Siren, red stamp, helper escorted out | Caught: nothing left the room | kill, nothing delivered |
| Sticky note "Remember this?" | It suggested a memory; you decide | quarantine proposal |

## Design tokens (from munder-difflin's tokens, MIT)

cream 50/100/200/300 `#FFFDF5 #FFF8E7 #F4E9C7 #E8D9A0`; ink 900/700/500/300/100 `#1A1320 #3D2E4A #6B5878 #A899B5 #D9CFE0`;
accents coral `#D96A62`, mint `#5CA97A`, sky `#4F9FAF`, lemon `#DCAB3C`, lilac `#9482D3`, peach `#D99168`;
floor wood `#E5C896 / #C9A66B`, grass `#D4EAB0 / #B5D589`, wall `#8B6F47`.
Panels: 2 px ink border, hard shadow `3px 3px 0`, title bar with the only allowed gradient (cream 100 to 200).
Type: Press Start 2P for small titles (8 to 12 px, Title Case), Inter 14 px for reading. One weight.

## Principles

1. Motion is the explanation. A walking character is the status; there is no progress bar.
2. Everything a user must decide is a big, labelled button. Paying is never done by voice.
3. Pixel art is drawn in a 320 by 200 world and scaled by whole numbers so edges stay crisp; text is drawn at screen resolution so it stays readable.
4. Reduced motion: the story plays instantly and the end state is shown.
5. Copy is short, active, sentence case; errors say what happened and what to do; empty states invite the next step.
6. The animation replays the real run record, and the page says it is a replay.

## Quality floor

Keyboard operable (drawers are also checkboxes), visible focus, 4.5:1 text contrast on cream, works from 360 px wide, canvas has a text alternative that
updates, all dynamic text is set with `textContent`.
