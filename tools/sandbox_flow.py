"""Runs the whole money flow once against PayPal's own SANDBOX (test money), with the real client code.

    .venv/Scripts/python tools/sandbox_flow.py [--refund]

1. places a hold of 40 cents (Orders v2, intent AUTHORIZE) and prints the approval link;
2. waits for you to approve it on PayPal's sandbox page, logged in as the sandbox buyer (your own step);
3. captures 25 cents of it (partial capture, final_capture false) and voids the rest;
4. with --refund it refunds the capture (the "certifier flagged the helper" path); otherwise it pays the author 23 cents
   (Payouts) to PAYPAL_AUTHOR_EMAIL from .env.

Reads PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET and PAYPAL_AUTHOR_EMAIL from .env and prints none of them: only order,
authorization, capture and payout ids, which are test ids. Nothing real moves; the client refuses any non-sandbox host.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bridge.payments.paypal import PayPalSandbox, load_paypal_credentials  # noqa: E402
from bridge.payments.provider import ProviderError  # noqa: E402


def author_email(env: Path) -> str:
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("PAYPAL_AUTHOR_EMAIL="):
            return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    refund = "--refund" in sys.argv
    env = ROOT / ".env"
    cid, secret = load_paypal_credentials(env)
    client = PayPalSandbox(cid, secret)
    run = f"flow-{int(time.time())}"
    try:
        order = client.authorize(40, run + "-hold", run)
        print(f"1. hold requested: order {order.auth_id} (40 cents)", flush=True)
        print(f"   APPROVE IT HERE (sandbox buyer): {order.approve_url}", flush=True)
        auth = None
        for _ in range(90):  # up to about 7 minutes
            try:
                auth = client.confirm(order.auth_id, run + "-confirm")
                break
            except ProviderError as e:
                if "has not approved" not in str(e):
                    raise
                time.sleep(5)
        if auth is None:
            print("   no approval within 7 minutes; stopped (nothing was charged)", flush=True)
            return 3
        print(f"2. approved: authorization {auth.auth_id} for {auth.amount} cents", flush=True)
        cap = client.capture(auth.auth_id, 25, run + "-capture")
        print(f"3. captured 25 cents: capture {cap.capture_id}", flush=True)
        client.void(auth.auth_id, run + "-void")
        print("4. voided the rest of the hold (15 cents released)", flush=True)
        if refund:
            client.refund(cap.capture_id, run + "-refund")
            print("5. refunded the capture (the flagged-helper path)", flush=True)
        else:
            to = author_email(env)
            if "@" not in to:
                print("5. payout skipped: PAYPAL_AUTHOR_EMAIL is not set in .env", flush=True)
            else:
                batch = client.payout(to, 23, run + "-payout")
                print(f"5. paid the author 23 cents: payout batch {batch}", flush=True)
    except ProviderError as e:
        print(f"STOPPED: {e}", flush=True)
        return 2
    print("sandbox flow complete", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
