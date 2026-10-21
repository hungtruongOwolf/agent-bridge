# 14 Payouts and holdback

Status: resolved (2026-10-20), proven on the fake provider; PayPal sandbox run pending ticket 11
Milestone: M3
Blocked by: 12

Author payout after capture, minus platform fee, behind a holdback label ("demo holdback 0 s, production N days"). Sandbox Payouts if the account allows it; otherwise a ledger entry labelled sandbox. Payout only by payer-bound destination recorded at publish.

Done when: an accepted run shows a payout record and a killed run shows none.
