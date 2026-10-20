# 12 Ledger state machine

Status: open
Milestone: M3
Blocked by: 11

One row per hire with compare-and-swap on a revision. States: ORDER_CREATED, AUTHORIZED, FLOOR_CAPTURED, OUTCOME_CAPTURED, VOIDED, DISPUTE_HOLD, PAID. Rules from design (SM s3): floor fee captured when the result is ready, outcome fee only on accept or auto-accept, a killed run goes to DISPUTE_HOLD (never a final void of delivered work), silence after start captures the floor, accept/kill/cancel race resolves to exactly one outcome, every provider call is idempotent and recorded in an outbox.

Done when: tests cover kill-vs-accept race, lost response retry (one capture), hub restart mid-flow (one payout), and silence.
