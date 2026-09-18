from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .validators import validate_bd_phone


class Role(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
    ADMIN = "ADMIN", "Admin"
    OPERATIONS_MANAGER = "OPERATIONS_MANAGER", "Operations Manager"
    DELIVERY_MANAGER = "DELIVERY_MANAGER", "Delivery Manager"
    DELIVERY_STAFF = "DELIVERY_STAFF", "Delivery Staff"
    WAREHOUSE_STAFF = "WAREHOUSE_STAFF", "Warehouse Staff"
    ACCOUNTANT = "ACCOUNTANT", "Accountant"
    VIEW_ONLY = "VIEW_ONLY", "View Only"
    CUSTOMER = "CUSTOMER", "Customer"


class User(AbstractUser):
    """Custom user: phone-first identity, role based access control."""

    phone = models.CharField(max_length=20, unique=True, validators=[validate_bd_phone])
    is_phone_verified = models.BooleanField(default=False)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.CUSTOMER)
    is_guest = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.phone})"

    @property
    def is_customer(self):
        return self.role == Role.CUSTOMER

    @property
    def is_delivery_staff(self):
        return self.role == Role.DELIVERY_STAFF


class Address(models.Model):
    """A customer can save multiple delivery addresses."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=50, default="Home")  # Home, Office, etc.
    house_name = models.CharField(
        max_length=150, blank=True,
        help_text="ফ্ল্যাট/বাড়ির নাম বা নম্বর (যেমন: বাড়ি ১২, ফ্ল্যাট ৩বি)",
    )
    full_address = models.TextField()
    landmark = models.CharField(
        max_length=200, blank=True,
        help_text="নিকটস্থ পরিচিত স্থান (যেমন: আল-ফালাহ মসজিদের পাশে) -- ম্যাপে সবসময় নির্ভুলভাবে ঠিকানা পাওয়া যায় না, তাই এটা staff-কে খুঁজে পেতে সাহায্য করে।",
    )
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.label} - {self.user}"

    def display_lines(self):
        """Ordered list of the non-empty address parts, for templates that
        want to show house name / landmark distinctly rather than mashed
        into one paragraph (staff dashboard, receipt, order detail)."""
        return [p for p in (self.house_name, self.full_address, self.landmark and f"ল্যান্ডমার্ক: {self.landmark}") if p]


class OTP(models.Model):
    """Phone OTP for registration / login / important action verification.

    The code is generated with secrets.randbelow (cryptographically secure,
    unlike random.randint) and stored hashed via Django's own password
    hasher -- never in plaintext -- so a DB read (or a stray log line)
    can't hand out a valid code. Use set_code()/check_code(), never read or
    compare code_hash directly.
    """

    class Purpose(models.TextChoices):
        REGISTRATION = "REGISTRATION", "Registration"
        LOGIN = "LOGIN", "Login"
        GUEST_ORDER = "GUEST_ORDER", "Guest Order"
        ACTION_VERIFY = "ACTION_VERIFY", "Important Action"
        PASSWORD_RESET = "PASSWORD_RESET", "Password Reset"

    phone = models.CharField(max_length=20, validators=[validate_bd_phone])
    code_hash = models.CharField(max_length=128)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["phone", "purpose", "is_used"])]

    def set_code(self, raw_code: str) -> None:
        from django.contrib.auth.hashers import make_password
        self.code_hash = make_password(raw_code)

    def check_code(self, raw_code: str) -> bool:
        from django.contrib.auth.hashers import check_password
        return check_password(raw_code, self.code_hash)

    @staticmethod
    def generate_code() -> str:
        import secrets
        return f"{secrets.randbelow(1_000_000):06d}"

    def save(self, *args, **kwargs):
        if not self.code_hash:
            self.set_code(self.generate_code())
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=5)
        super().save(*args, **kwargs)

    def is_valid(self):
        return (not self.is_used) and timezone.now() <= self.expires_at

    def __str__(self):
        return f"OTP for {self.phone} ({self.purpose})"


class Referral(models.Model):
    """Referral & loyalty program (Phase 2): refer a friend, earn a free refill / points."""

    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals_made")
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referred_by"
    )
    reward_points = models.PositiveIntegerField(default=0)
    is_reward_granted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.referrer} referred {self.referred_user}"


class LoyaltyPoint(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="loyalty_points")
    points = models.IntegerField()
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user}: {self.points} pts ({self.reason})"
