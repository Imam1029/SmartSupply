"""
Demo SMS gateway.

This simulates a real SMS provider (like Alpha SMS / SSL Wireless / Twilio)
closely enough that swapping in a real one later is a one-function change:

    real provider integration -> replace the body of `send_sms()` with an
    actual `requests.post(...)` call to your provider's API, keep the same
    signature and SMSLog bookkeeping.

Every message is logged to SMSLog so you can see delivery history in Admin,
exactly like a real provider's dashboard.
"""

import uuid


def send_sms(phone: str, message: str, purpose: str = "GENERAL") -> "SMSLog":
    from .models import SMSLog

    # --- DEMO PROVIDER: no real network call, always "delivered" ---
    fake_message_id = f"DEMO-SMS-{uuid.uuid4().hex[:10].upper()}"
    log = SMSLog.objects.create(
        phone=phone,
        message=message,
        purpose=purpose,
        provider_message_id=fake_message_id,
        status=SMSLog.Status.DELIVERED,
    )
    print(f"[DEMO SMS] to={phone} msg={message!r} id={fake_message_id}")
    return log
