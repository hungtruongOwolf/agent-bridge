# Console design plan

Written before building, following the frontend-design guidance: pick a direction from the subject's own world,
make type and colour deliberate, spend motion in one place, and make every border, number and label carry information.

## Subject, audience, job

Subject: running a stranger's agent inside a sealed room on your own machine.
Audience: someone deciding whether to hand a task and some private records to an agent they do not know.
Job of the screen: let them *see* what the agent can touch, what it did, what was blocked, and where the money is,
as it happens. The previous console was a form with cards. This one is a live schematic.

## Vernacular

A glovebox or airlock: a transparent chamber you can look into but cannot reach into, with a few labelled doors.
So the hero is a **schematic of the run**: other people's machines on the outside, your machine in the middle, a sealed
cell with glass walls, and only three doors out (memory broker, model, web). Traffic along those doors animates.
Nothing else on the page competes with it.

## Tokens

| Name | Light | Dark | Used for |
|---|---|---|---|
| Paper | #EEF1F2 | #0F1519 | page |
| Sheet | #FAFBFB | #172026 | panels and schematic fills |
| Ink | #101C28 | #E4EAEC | text, schematic linework |
| Vault | #0B6B63 | #3FBFB0 | what is yours and allowed: shared records, released result |
| Signal | #D9480F | #FF8A4C | live traffic on a door |
| Breach | #B3261E | #FF6B61 | blocked attempts, stopped runs |
| Hold | #8A6100 | #E0B04A | money on hold, test-money badge |

Type: two clearly different families plus mono for hashes.
Headings: a serif (Iowan Old Style, Palatino, Georgia). Body: the system sans (Segoe UI, system-ui). Mono: ui-monospace.
Scale: 13 / 15 / 18 / 26 px, headline 26 px serif.

## Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ⌒ agent-bridge   Rent a stronger agent. Keep your data.   Test money  $… │
├────────────┬─────────────────────────────────────────────┬───────────────┤
│ Agents     │ Stage: the live schematic                   │ Outcome       │
│ 1 name  $  │  Author ─signed pack─▶ ┌ Your machine ───┐   │ result        │
│ 2 name  $  │  Hub                   │ vault▦ │broker│  │   │ Payment       │
│ ! flagged  │                        │   ┌cell┐ guard │──▶ Delivered       │
│            │  Payments              │   └─┬──┘        │   │ To remember   │
│ May read   │                        │  sidecar ─▶ Nebius│  │ Audit log     │
│ [x] note   │                        └───────────────────┘  │ Past runs     │
│ [Run]      │ plain-language log of what just happened    │               │
└────────────┴─────────────────────────────────────────────┴───────────────┘
```
Below 1180 px the stage comes first, then the list, then the outcome.

## Principles

1. The schematic is the only large graphic. No card grid, no stat tiles.
2. Rank is a sequence, so it is numbered. Everything else uses plain rows and rules that mean something (a rule separates
   what you control from what you do not).
3. Colour carries state, never decoration: teal is yours and allowed, orange is traffic on a door, red is blocked, ochre is held money.
4. One orchestrated moment: the run replay. Hover and press states respond to the user. `prefers-reduced-motion` turns the replay into instant states.
5. Copy is plain, active, sentence case. Errors say what happened and what to do. Empty states invite the next action. No all-caps labels,
   no eyebrow labels, no middle-dot metadata strings.
6. The replay is of the real audit journal, and the page says so.

## Quality floor

Keyboard reachable controls with a visible focus ring, text contrast on both themes, layout works from 360 px to wide screens,
all dynamic text set with `textContent`, no network requests except to the local API.
