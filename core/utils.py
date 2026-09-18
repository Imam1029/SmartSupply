"""Small shared helpers used by multiple apps."""

from accounts.models import OTP


def log_action(actor, action, model_name="", object_id="", **details):
    """Write one row to core.AuditLog. Call this at any sensitive/important
    state change (order status, payment, bottle write-off, cash handover)
    so there's a trail of who did what and when."""
    from .models import AuditLog

    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        model_name=model_name,
        object_id=str(object_id),
        details=details,
    )


def send_otp(phone, purpose):
    """Create the OTP row and 'send' it via the (demo) SMS gateway.

    Swap `core/sms_gateway.py::send_sms` for a real provider later --
    nothing here needs to change since it already goes through that one
    function. The raw code only ever exists here and in the SMS text
    itself -- the DB only ever stores its hash (see OTP.set_code).
    """
    from .sms_gateway import send_sms

    raw_code = OTP.generate_code()
    otp = OTP(phone=phone, purpose=purpose, expires_at=None)
    otp.set_code(raw_code)
    otp.save()
    send_sms(phone, f"আপনার Smart Water OTP কোড: {raw_code} (৫ মিনিটের জন্য বৈধ)", purpose=f"OTP_{purpose}")
    return otp
