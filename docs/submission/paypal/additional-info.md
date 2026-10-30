# Agora (PayPal AI): "Additional info" page, field by field

Nothing here is entered for you. Fields marked CONFIRM are about you or your choices; only you can say them.
Every claim below was checked against the repo on 2026-10-30 (git history, README, `docs/paypal-setup.md`, `pytest tests/payments`: 92 passed).

## The PayPal sandbox: done (2026-10-30), use Text A

The rules ask for the PayPal developer platform **using the free sandbox**. What is true today: the PayPal client
(`src/bridge/payments/paypal.py`) is written for the sandbox and is selectable (`bridge serve --payments paypal`), but it has only been
run against our local practice server, never against PayPal's own sandbox. The video says so. (Historical note, now resolved.) Before the deadline (11-11 for us), run:

```
bridge paypal-check
```

(needs `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` in `.env`; see `docs/paypal-setup.md`). It asks the sandbox for a token and makes one
uncharged 1-cent order. If it prints `PayPal sandbox check OK`, use **Text A** below. If not, use **Text B** and do not claim a live sandbox.
Do not mix them: the form is signed with a statement that the information is true.

---

## Short fields

| Field | Answer |
|---|---|
| Upload a File | Leave empty (optional). |
| Submitter Type | Individual (CONFIRM: only if you have no teammates on the Devpost team) |
| Country of Residence | United States (CONFIRM) |
| Province (Canada) | N/A |
| Organization Name | N/A |
| New, or existed before Oct 1, 2026? | **New.** The first commit is 2026-10-20 (186 commits, all dated 2026-10-20 to 2026-10-30). |
| If it existed before, explain | N/A |
| Additional sponsor tools | **AG Grid** (the Earnings ledger and chart, Community edition) and **Channel3** (the Deal Finder helper; no live call yet, see the note in the answer). Do not tick Render until it is actually deployed. **Postman** (the collection was run with Postman's newman runner against the practice server: 13 assertions passed; see docs/postman/README.md). Do not tick Zapier: the webhook was built but not run through Zapier. |
| Public code repository URL | `https://github.com/hungtruongOwolf/agent-bridge` (must be public with the MIT licence by submission; the README now has a "How it uses PayPal and AI" section) |
| Working demo / test build URL | `https://agora-replay.vercel.app`: the interactive replay in `demo-site/` (deploy steps in `demo-site/README.md`). If you do not deploy it, use `https://github.com/hungtruongOwolf/agent-bridge#quickstart`. |
| APIMatic Context Plugin | Leave empty (not used). |
| AG Grid | Leave empty (not used). |
| Contact about PayPal feedback | Yes (CONFIRM: your choice; "Yes" costs nothing and judges may value it) |
| Age of majority / eligible jurisdiction / not an employee of the promotion entities | Tick all three only if each is true for you and any teammates (CONFIRM). |
| Level of learning | The highest option offered (it is accurate: PayPal authorize / partial capture / Payouts, idempotency and crash recovery were all new to this project). |
| Gained AI value for your career? | Yes |

## Explain how your project meets the main technology requirement

**Text A** (use only after `bridge paypal-check` prints OK and you have run one real sandbox hold):

> **PayPal tools (free sandbox):** OAuth client credentials; Orders v2 with intent AUTHORIZE for the buyer's hold (the ceiling, 40 cents in the demo); capture of part of the authorization (`final_capture: false`) for the real price (25 cents); void for the released remainder; refund when the independent certifier has flagged a helper; Payouts to pay the author. Every call carries a `PayPal-Request-Id`, so a lost reply is retried without charging twice. Code: `src/bridge/payments/paypal.py` (client, refuses any non-sandbox host) and `ledger.py` (one state machine per hire). Run with `bridge serve --payments paypal`; credentials go in `.env`.
>
> **AI tools:** NVIDIA Nemotron (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) on Nebius Token Factory runs the helpers' thinking steps, and the same model scores every helper in the certifier whose flag decides whether a full refund is allowed. The price of a run is worked out from what the engine recorded (files read, model calls), never from what the helper says. Code: `src/bridge/engine/nebius.py`.
>
> **Run on the sandbox:** on 2026-10-30 `tools/sandbox_flow.py` ran the whole flow on PayPal's own sandbox with the same client: a 0.40 USD hold approved by a sandbox buyer on PayPal's page (order 72976802Y2886202H), a partial capture of 0.25 (capture 8KM340019E533435E, COMPLETED), a void of the remaining hold (authorization 938379318G574340P, VOIDED) and a Payouts payment of 0.23 to the author (batch 2BAZVTRQ8LG34, item SUCCESS), each read back from the sandbox API afterwards. The refund path and the in-app approval redirect have only been exercised on the practice server. For repeatable recording the demo video and the hosted demo use the practice server (same client code, `--payments paypal-mock`). All money is test money.

**Text B** (use if the live sandbox check has not passed; this is the true state today):

> **PayPal tools:** Orders v2 with intent AUTHORIZE for the buyer's hold (the ceiling, 40 cents in the demo); capture of part of the authorization (`final_capture: false`) for the real price (25 cents); void for the released remainder; refund when the independent certifier has flagged a helper; Payouts to pay the author; OAuth client credentials; and a `PayPal-Request-Id` on every call so a lost reply never charges twice. Code: `src/bridge/payments/paypal.py` (a sandbox client that refuses any non-sandbox host) and `ledger.py` (one state machine per hire).
>
> **How it was verified, stated plainly:** the client has been exercised end to end against a local practice server that copies PayPal's API (approval page, authorize, capture, void, refund, payouts), with about 720 automated tests (92 of them cover payments) that need no keys (`pytest tests/payments`). It has **not yet been run against PayPal's own sandbox**; that mode (`bridge serve --payments paypal`, see `docs/paypal-setup.md`) is included and selectable but unverified. No real money moves anywhere.
>
> **AI tools:** NVIDIA Nemotron (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) on Nebius Token Factory runs the helpers' thinking steps, and the same model scores every helper in the certifier whose flag decides whether a full refund is allowed. The price of a run comes from what the engine recorded, never from what the helper says. Code: `src/bridge/engine/nebius.py`.

## Testing instructions or credentials the judges need

> No credentials are needed to check the PayPal part, and none are shared.
>
> **Fast check (about 1 minute, no keys):** `git clone https://github.com/hungtruongOwolf/agent-bridge && cd agent-bridge`, then `python -m venv .venv`, activate it, `pip install -e ".[dev]"`, `pytest tests/payments -q`. This runs 92 tests of the money flow (hold, partial capture, void, refund, payouts, lost replies, crash recovery, racing accept and kill) against the practice PayPal server.
>
> **Full demo:** needs a Nebius Token Factory API key for the helpers' model (put it in `.env`; see `.env.example`). Then `bridge seed` and `bridge serve --vault examples/vault-library.json --payments paypal-mock`, open http://127.0.0.1:8787, start a chat, press "Open the approval page", press "Approve the hold" on the practice PayPal page, and click the coins chip in the top bar to read each receipt. `docs/paypal-setup.md` has the steps for PayPal's own sandbox.
>
> **Interactive replay, no setup:** https://agora-replay.vercel.app. It plays a real recorded run on the practice PayPal server (hire the helper, tick a shelf, approve the 40¢ hold on the practice PayPal page, read the answer and the receipt, accept, say "Not helpful"). It is a recording, and the page says so. The 2:54 video shows the same flow.

(CONFIRM that `bridge seed` and the commands above work from a clean clone on your machine before pasting: the README quickstart was verified earlier, not re-run today.)

## Overall experience rating (1 to 10)

Pick **7** (the live sandbox flow worked). Do not pick 9 or 10: they would not match the feedback you give.

## Rating: please share why

> The API design maps well to what we needed: an authorization is a natural "ceiling", and partial capture plus void let the real price be set after the work. The documentation of intent AUTHORIZE with a buyer approval step, partial capture and Payouts was enough to build a full client and a practice server from. What cost us time: an authorization needs the buyer's approval first, so we had to model "waiting for approval" as its own state and carry the buyer from the app to PayPal's page and back; and authorization honor periods and the rules for capturing less than the full amount are spread over several pages. We ran the whole flow on the sandbox: token, a 0.40 hold approved on PayPal's page, a partial capture, a void and a payout all worked at the first real attempt, and reading each object back from the API made it easy to check the result. [Add anything that annoyed you while creating the sandbox app or accounts, in your own words.] We would like a single page that shows the lifecycle of an authorization (approve, authorize, partial capture, void, expiry) with the exact status values at each step.

(Edit the bracket to your real experience. The paragraph above only claims what we did: read the docs, built the client and practice server, ran 92 tests. It does not claim sandbox runtime problems we did not observe.)

## Which AI tools have you leveraged while working on this project?

> **In the product:** NVIDIA Nemotron (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) served by Nebius Token Factory (helpers' thinking steps and the certifier).
> **To build it:** Claude Code (Anthropic Claude) for most of the code, tests, documentation and the video tooling, with the owner directing and reviewing; ElevenLabs for the video voice-over.

(CONFIRM the list: add any other tool you used, drop any you did not.)

## Describe the level of learning (if there is a text box instead of a menu)

> We started this project with no experience of PayPal's authorize and capture flow and learned it by building it: a hold as a spending ceiling, partial capture so the price follows the work, void and refund, and why a refund rule must depend on evidence and not on the buyer's word. We also learned practical payment engineering we did not expect to need: idempotency keys, write-ahead intents so a crash finishes an operation exactly once, and one lock-guarded state machine so accept and kill cannot both win.

## Did you gain AI value you can use in your career?

> Yes: building and certifying agents on an open model (Nemotron via Nebius), measuring that the same model scored 9, 13 and 14 of 16 depending only on the setup around it, and designing payment and trust rules for agents that run on someone else's machine.
