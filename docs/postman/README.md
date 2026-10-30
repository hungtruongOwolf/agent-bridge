# Postman collection: Agora PayPal sandbox

Eight requests that mirror what `src/bridge/payments/paypal.py` sends to the PayPal **sandbox**: token, create order
(intent AUTHORIZE, 0.40 USD), a manual approval step, authorize, partial capture of 0.25 (`final_capture: false`), void the
rest, refund, and a payout. Test money only.

## Import
1. In Postman choose **Import** and select `agora-paypal-sandbox.postman_collection.json` and `agora-paypal-sandbox.postman_environment.json`.
2. Select the environment "Agora PayPal sandbox".

## Credentials (never commit them)
Create a sandbox app at https://developer.paypal.com (Apps & Credentials, Sandbox; see `../paypal-setup.md`). In Postman, fill the
environment's `client_id`, `client_secret` and `payout_receiver_email` (a sandbox account email) in the **current value** column only.
The files in this repo keep every value empty. The collection talks to `https://api-m.sandbox.paypal.com` only.

## Run
Send the requests in order. Each test script checks the status code and saves the next id (`access_token`, `order_id`,
`authorization_id`, `capture_id`, `payout_batch_id`). Step 2 prints the approval link in the Postman console; open it and approve as
the sandbox buyer (step 3, manual), then continue. Step 6 voids what is left after the capture; step 7 refunds the capture.

With the Postman CLI (after `postman login`):

```
postman collection run docs/postman/agora-paypal-sandbox.postman_collection.json -e docs/postman/agora-paypal-sandbox.postman_environment.json
```

A full automated run stops at the manual approval (step 4 fails with ORDER_NOT_APPROVED), so use the app, or approve the order in a browser between two runs.

## What was confirmed
Checked against PayPal's published OpenAPI schemas (developer.paypal.com/docs/api/.../schema.json): paths and request fields for create order
(`intent` AUTHORIZE, `purchase_units[].amount`, `application_context` return_url / cancel_url / user_action / shipping_preference), authorize,
capture (`final_capture`), void, refund, and create payout (`sender_batch_header`, `items[]` with `recipient_type`, `receiver`, `sender_item_id`;
response `batch_header.payout_batch_id`). Not confirmed: anything live. The collection has not been run against the sandbox, so the status codes and
values in the test scripts are expectations from the docs.
