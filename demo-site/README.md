# agent-bridge replay (static site)

An interactive replay of the real console. Judges can click through the payment flow (hire Account Brief, tick a shelf, approve a hold of 40¢ on the
practice PayPal page, read the answer and the receipt, accept, say "Not helpful") with **no server, no keys and no model**.

It is a recording, not a live app, and the site says so at the bottom of every screen:
*Replay of a real run recorded on the practice PayPal server. Test money. Nothing here talks to PayPal or a model.*

## How it works

- `static/` is a copy of the console's own front end (`src/bridge/web/static`), unchanged, so the screens are the real ones.
- `shim.js` replaces `fetch` for `/api/*` and answers from `fixtures/replay.json`, a recording of a real session against the console running with the
  practice PayPal server. It is a small state machine (hold to approve, running, answered, accepted, not helpful), kept in `localStorage`, so a reload or
  the approval page in another tab sees the same story.
- `approve.html` imitates the practice PayPal approval page and tells the chat tab the same way the console's own return page does. `practice.html` imitates
  the practice server's order list.
- Anything the recording does not cover (your own questions, other helpers, publishing) answers with a plain sentence. Typed questions are ignored: the
  replay always plays the recorded ones ("Which accounts are at risk?" then "And which one is the biggest?"). There is a "Fill in the question" button.

## Deploy (static, no build step)

Either, from this folder:

```
cd demo-site
npx vercel --prod
```

(answer the prompts: link to a new project, no build command, output directory `.`), or on vercel.com import the GitHub repo and set
**Root Directory = demo-site**, Framework Preset = Other, no build command. `vercel.json` sends every unknown address to `index.html`, because the
console is a single-page app (`/chats/...`, `/memory`, `/helpers`). Any static host works the same way (Netlify, Cloudflare Pages, GitHub Pages with a
404 fallback).

## Re-record or re-check

```
bridge serve --state .bridge-replay --vault examples/vault-library.json --payments paypal-mock --port 8795   # a fresh state: no earlier chats or receipts
node demo-site/tools/capture.mjs http://127.0.0.1:8795      # drives the real console, writes fixtures/trace.json
node demo-site/tools/build-fixtures.mjs                      # trace.json -> fixtures/replay.json
node demo-site/tools/copy-static.mjs                         # refresh static/ and index.html from the console
node demo-site/tools/smoke.mjs --shots video-out/replay      # clicks through the whole replay; exit code 1 if anything is off
```

## Known limits

- Only the Account Brief flow is recorded. Ticking other shelves changes the side panel but not the answer.
- The console's narrow-screen layout was never verified; the replay is usable at 390 px wide (the smoke test checks that nothing breaks) but not polished.
- The recording was made on the practice PayPal server, not on PayPal's own sandbox.
