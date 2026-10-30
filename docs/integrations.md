# Integrations: outbound webhooks and Zapier

Agora (agent-bridge) can POST a small JSON event whenever money moves, so other tools can react. All amounts are **test money**, in cents.

## Turn it on

Add to the gitignored `.env` (or set as environment variables):

```
BRIDGE_WEBHOOK_URL=https://hooks.zapier.com/hooks/catch/...
BRIDGE_WEBHOOK_SECRET=optional-long-random-string
```

Unset means off. Restart `bridge serve`.

## Events

`payment.settled` (answer kept, or marked not helpful: see `status`), `payout.paid`, `payment.refunded`, `dispute.resolved` (with `upheld`).

```json
{"event":"payment.settled","run_id":"...","helper":"deal-brief","status":"SETTLED","price":100,"captured":100,
 "refunded":0,"payout":90,"currency":"USD","test_money":true,"amounts_in_cents":true,"timestamp":"2026-10-30T10:00:00+00:00"}
```

Never included: the buyer's message, answers, emails, names of buyer or author, memory content.

## Delivery rules

Sent from a background thread after the payment is saved. 5 second timeout, 2 retries with 0.5 s then 1 s backoff, then it gives up and logs.
A broken or slow receiver never blocks or fails a payment. Delivery is at-least-once-ish, not guaranteed: do not treat it as the ledger.

## Signature (optional)

With `BRIDGE_WEBHOOK_SECRET` set, each request has `X-Agora-Signature: sha256=<hex>`, the HMAC-SHA256 of the exact body bytes.
Zapier's Catch Hook help page does not describe checking signatures (only "Catch Raw Hook" exposes headers), so Zapier recipes usually skip it; verify it in your own receiver.

## Zapier recipe

Steps below follow Zapier's help page "Trigger Zaps from webhooks" (help.zapier.com):

1. In the Zap editor, click the **Trigger** step, search for **Webhooks by Zapier**, set **Event** to **Catch Hook**, click **Continue**.
2. Leave **Pick Off A Child Key** empty (optional) and continue.
3. On the **Test** tab copy the webhook URL and put it in `BRIDGE_WEBHOOK_URL`.
4. Restart Agora and settle one test payment (mark an answer helpful or not helpful).
5. Back in Zapier press **Test trigger**; the fields (`event`, `run_id`, `helper`, `price`, ...) appear for later steps.
6. Add an action: for example Email, Slack "Send Channel Message" or Google Sheets "Create Spreadsheet Row", and map `event`, `helper`, `price`, `payout`, `timestamp`.

Not confirmed from the help page: exact names of the Email/Slack/Sheets actions' fields (they change), and whether your Zapier plan allows webhooks (check your plan).
