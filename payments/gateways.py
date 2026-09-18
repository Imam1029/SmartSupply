"""
Placeholder payment gateway integrations.

Real bKash / Nagad merchant API credentials are not wired up yet.
When you're ready to go live:
  1. Put credentials in environment variables / settings
     (BKASH_APP_KEY, BKASH_APP_SECRET, BKASH_USERNAME, BKASH_PASSWORD, ...)
  2. Replace the body of `initiate_payment` / `verify_payment` below with
     real HTTP calls to the gateway's API (requests library).
  3. Nothing else in the codebase needs to change -- views call these
     two functions only.
"""

import uuid
from dataclasses import dataclass


@dataclass
class GatewayResult:
    success: bool
    transaction_id: str
    raw_response: dict


def initiate_payment(method: str, amount, order_uid) -> GatewayResult:
    """Start a payment session with bKash/Nagad. Currently a dummy stub."""
    if method not in ("BKASH", "NAGAD"):
        raise ValueError(f"initiate_payment only supports BKASH/NAGAD, got {method}")

    fake_txn_id = f"{method}-DUMMY-{uuid.uuid4().hex[:10].upper()}"
    return GatewayResult(
        success=True,
        transaction_id=fake_txn_id,
        raw_response={
            "note": f"PLACEHOLDER {method} integration - no real API call made.",
            "amount": str(amount),
            "order_uid": str(order_uid),
        },
    )


def verify_payment(method: str, transaction_id: str) -> GatewayResult:
    """Verify a payment with the gateway. Currently always returns success (dummy)."""
    return GatewayResult(
        success=True,
        transaction_id=transaction_id,
        raw_response={"note": f"PLACEHOLDER {method} verification - always succeeds in dev mode."},
    )
