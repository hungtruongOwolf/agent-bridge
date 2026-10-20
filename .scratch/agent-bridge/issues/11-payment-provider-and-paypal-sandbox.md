# 11 Payment provider interface and PayPal sandbox client

Status: open
Milestone: M3
Blocked by: owner provides PayPal sandbox client id and secret in .env (PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)

A `PaymentProvider` interface (authorize, capture, void, payout) with a fake in-memory provider for tests and a PayPal Orders v2 client for the sandbox: create order with AUTHORIZE intent, authorize, capture, void, idempotent by `PayPal-Request-Id`. Sandbox host only; refuses a live host.

Done when: the same contract tests pass against the fake and against the sandbox, and the client rejects any non-sandbox base URL.
