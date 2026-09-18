from django.contrib import admin

from core.admin_mixins import RoleBasedAdminMixin
from django.contrib.auth.admin import UserAdmin

from .models import Address, LoyaltyPoint, OTP, Referral, User


@admin.register(User)
class CustomUserAdmin(RoleBasedAdminMixin, UserAdmin):
    list_display = ("username", "phone", "role", "is_phone_verified", "is_guest", "is_active")
    list_filter = ("role", "is_phone_verified", "is_guest", "is_active")
    search_fields = ("username", "phone", "email", "first_name", "last_name")
    fieldsets = UserAdmin.fieldsets + (
        ("Platform info", {"fields": ("phone", "is_phone_verified", "role", "is_guest")}),
    )


@admin.register(Address)
class AddressAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("user", "label", "is_default", "created_at")
    search_fields = ("user__username", "user__phone", "full_address", "landmark", "house_name")


@admin.register(OTP)
class OTPAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("phone", "purpose", "is_used", "created_at", "expires_at")
    list_filter = ("purpose", "is_used")


@admin.register(Referral)
class ReferralAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("referrer", "referred_user", "reward_points", "is_reward_granted", "created_at")


@admin.register(LoyaltyPoint)
class LoyaltyPointAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("user", "points", "reason", "created_at")
