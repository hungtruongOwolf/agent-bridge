# PayPal AI hackathon (Agora): what is left to do

Deadline: submit by 2026-11-11 (the form closes 2026-11-12 3:00pm EST). Nebius is a separate, earlier deadline (2026-10-30 10:00 PT).
Written 2026-10-30. Tick items off as they are done.

## A. Must do (the rules or the judging depend on it)

- [ ] **A1. Run the PayPal sandbox for real.** The rules require the free sandbox; today the client is only verified against our practice server.
  Owner: put `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_AUTHOR_EMAIL` in `.env` (steps in `docs/paypal-setup.md`), run `bridge paypal-check`,
  and send the error text if it fails (never paste the secret). Rotate the secret that was pasted earlier. Then one approved hold, capture, void and payout
  against the sandbox. Afterwards: change the "Text B" answer in `additional-info.md` to "Text A" and the README/Devpost wording from "not run on the live sandbox".
- [ ] **A2. A functional demo judges can run.** The rules reject static prototypes. The Vercel replay (`demo-site/`) is only a quick look. Needed: a hosted real app
  (see B1) or setup instructions a judge can follow without our Nebius key (a no-key mode, see B3). Re-run the quickstart from a clean clone and fix anything that fails.
- [ ] **A3. Repo public** with the MIT licence visible in the About section; README explains how PayPal and AI are used (done: "How it uses PayPal and AI").
- [ ] **A4. Video** uploaded to YouTube (public), no third-party music or trademarks (our music is synthesized; check the logos on screen), link into the form.
- [ ] **A5. Fill the form** from `devpost-fields.md` and `additional-info.md`, replace `[YOUTUBE LINK]` and `[DEMO URL after deploy]`.

## B. Raise the score (the criteria: implementation, design, impact, innovation, presentation)

- [ ] **B1. Host the real app on Render** (sponsor prizes: Render credits). A Dockerfile and `render.yaml`; bind to `0.0.0.0` through an env switch, allow the public host
  in the Host-header check (keep the token and CSRF rules), Nebius key as a Render secret with a spending cap per visitor, workflow helpers only (no Docker-in-Docker).
  With a public URL the PayPal sandbox return page also works the way PayPal expects.
- [ ] **B2. Author ledger with AG Grid** (sponsor prizes up to $5,000). A "Earnings" view: receipts, holds, captures, refunds, payouts; sort, filter, group by helper.
  Read official AG Grid docs first; use the community edition.
- [ ] **B3. No-key demo mode**: a deterministic local model for the payment flow so judges can run the money flow without a Nebius key.
- [ ] **B4. Zapier webhook** on settled / paid out (for example an email to the author). Cheap. No prize of its own.
- [ ] **B5. Postman collection** of the PayPal sandbox calls we use (helps diagnose A1 and doubles as documentation). No prize of its own.
- [ ] **B6. Cap on "Not helpful"** presses (a known product gap): a buyer can press it as often as they like. Build the cap or document it as a limit.
- [ ] **B7. Targets for the special prizes** "Best Use of PayPal + AI" and "Best Use of Agentic Commerce": make the agent-to-agent hire visible in the video and the write-up.

## C. Skip (not a fit): Bryntum, Channel3, Elastic, KERNEL, Astropods, APIMatic (low value for the effort).

## D. Housekeeping

- [ ] Update `docs/video/PRODUCTION.md` and the CLAUDE.md hand-off with the version 2 video work, the submission images (`tools/submission`) and `demo-site/`.
- [ ] Update the README "~310 tests" figure; re-run `pytest` and put the real number in both Devpost texts ("About 660").
- [ ] If the sandbox works, re-record the money scenes (p03 to p05) against it, or add a short sandbox clip to the video.
