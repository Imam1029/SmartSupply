"""
Bangladeshi mobile number validation, used everywhere a phone number is
collected (registration, login, password reset, guest checkout, OTP). This
platform's entire identity/auth system runs on phone + OTP, so a malformed
number here isn't just a bad-data problem -- it means the OTP SMS has
nowhere real to go, silently breaking login/registration for that account.

Valid local mobile format: 01[3-9]XXXXXXXX (11 digits total, third digit
3-9 covers all current operator prefixes -- 013 Grameenphone, 014 Banglalink,
015 Teletalk, 016 Airtel, 017 Grameenphone, 018 Robi, 019 Banglalink).
Landlines and other formats are intentionally not accepted -- this platform
only ever contacts customers by SMS OTP.
"""
import re

from django.core.exceptions import ValidationError

BD_PHONE_PATTERN = re.compile(r"^01[3-9]\d{8}$")


def normalize_bd_phone(value: str) -> str:
    """
    Canonical storage format is local 01XXXXXXXXX (11 digits, no country
    code) -- accepts +880/880/0 prefixes as input and folds them all to the
    same thing, so a customer typing +8801... and one typing 01... for the
    same number resolve to the same account instead of silently creating
    two. Also strips spaces/dashes some people paste in from their contacts
    app (e.g. "017-1234-5678").
    """
    v = re.sub(r"[\s-]", "", (value or "").strip())
    if v.startswith("+880"):
        v = "0" + v[4:]
    elif v.startswith("880"):
        v = "0" + v[3:]
    return v


def validate_bd_phone(value: str) -> None:
    """Raises ValidationError if `value` isn't an 11-digit BD mobile number
    in the normalized 01XXXXXXXXX form. Call `normalize_bd_phone` first --
    this does not normalize, only checks."""
    if not BD_PHONE_PATTERN.match(value or ""):
        raise ValidationError(
            "সঠিক বাংলাদেশি মোবাইল নম্বর দিন -- ফরম্যাট: 01XXXXXXXXX (১১ ডিজিট), "
            "যেমন 017XXXXXXXX। +880 দিয়েও লেখা যাবে।",
            code="invalid_bd_phone",
        )


def clean_bd_phone(raw: str) -> str:
    """Convenience for form clean_<field> methods: normalize then validate,
    returning the canonical value or raising forms.ValidationError (which is
    the same exception class as core's) on a bad format."""
    phone = normalize_bd_phone(raw)
    validate_bd_phone(phone)
    return phone
