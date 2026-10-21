# PayPal: from practice to the real sandbox

There are three ways to run the money, from safest to most real. All of them are **test money**. Nothing here can move real money.

| Mode | Command | What it is |
|---|---|---|
| Demo coins | `bridge serve` | Fake provider that keeps numbers in a file. |
| Practice PayPal | `bridge serve --payments paypal-mock` | A local server that behaves like the PayPal sandbox, with its own approval page and dashboard. It runs the **real PayPal client code**. It is an emulator written from PayPal's public docs, not PayPal. |
| PayPal sandbox | `bridge serve --payments paypal` | PayPal's own sandbox. Needs the credentials below. **Not yet verified against the live sandbox.** |

Say which one you used in the video. Do not call the practice server "PayPal".

## Try the practice PayPal now (no credentials)

```
bridge serve --vault examples/vault-library.json --payments paypal-mock
```

1. Start a chat and send a message. The chat asks you to approve a hold and shows **Open the approval page**.
2. The approval page is the practice server's (port 8788 by default), labelled "Practice server". Press **Approve the hold**.
3. The console tab carries on by itself and the helper answers. Click the **coins chip** in the top bar to see every receipt.
4. The practice dashboard (`http://127.0.0.1:8788/mock/state`) shows what is on hold, captured, refunded and paid out to authors.

`bridge paypal-mock --port 9797` runs the practice server on its own.

## Get PayPal sandbox credentials (what you need to do)

1. Sign in at https://developer.paypal.com with your PayPal account and open **Apps & Credentials**, then **Sandbox**.
2. **Create App** (type Merchant). Copy the **Client ID** and **Secret**.
3. Under **Sandbox accounts** note the default **Business** account (this is the marketplace) and the default **Personal** account
   (the buyer who approves holds; its email and password are shown there, use them only on the sandbox login page).
4. In the app's settings make sure **Payouts** is enabled for the sandbox business account (so authors can be paid).
5. Put the values in `.env` (never commit it; never paste secrets into chat):

```
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_AUTHOR_EMAIL=the sandbox personal account email that should receive author payouts
```

## Check it, then run it

```
bridge paypal-check
```

This asks the sandbox for a token and creates one 1-cent order that nobody approves, so nothing is charged. If it prints
`PayPal sandbox check OK`, run the console with the sandbox:

```
bridge serve --payments paypal
```

When a chat asks for approval, **Open the approval page** goes to PayPal's own sandbox page. Log in with the sandbox personal
account and approve. The console continues by itself once PayPal sends you back.

## What is checked, and what is not

- The client is tested against the practice server (`tests/payments/test_paypal_mock.py`): token, order, approval, authorize, capture
  (partial, repeated, too large), void, refund (twice), payouts, lost-reply retries, restart.
- It has **not** been run against the live sandbox: field names and flows come from PayPal's public documentation. The first real run
  may reveal differences (for example the wording of an error, or a payout that needs a verified recipient). Treat the first run as a test.
- The client refuses any base URL except the sandbox or a practice server on this computer, so a typo cannot reach live PayPal.

## If something fails

| You see | Likely cause |
|---|---|
| "PayPal rejected the sandbox credentials" | Wrong Client ID or Secret, or you copied the **live** keys instead of **sandbox**. |
| "the hold is not approved yet" | The approval page was not completed. Open it again from the chat, approve, then press **I approved, continue**. |
| "PayPal refused: ..." on payouts | Payouts not enabled for the sandbox business account, or the recipient email is not a sandbox account. |
| The chat stays on "Waiting for you to approve" after approving | The approval tab was opened from a different address (not 127.0.0.1:8787). Press **I approved, continue**. |
