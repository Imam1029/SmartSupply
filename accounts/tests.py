"""Tests for the OTP model's hashed-code handling."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import OTP


class OTPHashingTests(TestCase):
    def test_correct_code_checks_out(self):
        raw = OTP.generate_code()
        otp = OTP(phone="01800000009", purpose=OTP.Purpose.REGISTRATION, expires_at=timezone.now() + timedelta(minutes=5))
        otp.set_code(raw)
        otp.save()
        self.assertTrue(otp.check_code(raw))

    def test_wrong_code_fails(self):
        raw = OTP.generate_code()
        wrong = "000000" if raw != "000000" else "111111"
        otp = OTP(phone="01800000009", purpose=OTP.Purpose.REGISTRATION, expires_at=timezone.now() + timedelta(minutes=5))
        otp.set_code(raw)
        otp.save()
        self.assertFalse(otp.check_code(wrong))

    def test_raw_code_is_never_stored_in_the_database(self):
        raw = OTP.generate_code()
        otp = OTP(phone="01800000009", purpose=OTP.Purpose.REGISTRATION, expires_at=timezone.now() + timedelta(minutes=5))
        otp.set_code(raw)
        otp.save()
        self.assertNotEqual(otp.code_hash, raw)
        self.assertNotIn(raw, otp.code_hash)

    def test_used_otp_is_no_longer_valid(self):
        otp = OTP.objects.create(
            phone="01800000009", purpose=OTP.Purpose.REGISTRATION,
            is_used=True, expires_at=timezone.now() + timedelta(minutes=5),
        )
        self.assertFalse(otp.is_valid())

    def test_expired_otp_is_no_longer_valid(self):
        otp = OTP.objects.create(
            phone="01800000009", purpose=OTP.Purpose.REGISTRATION,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.assertFalse(otp.is_valid())
