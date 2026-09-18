from django import forms
from django.contrib.auth import get_user_model

from .models import Address
from .validators import clean_bd_phone, normalize_bd_phone

User = get_user_model()


class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"placeholder": "আপনার নাম"}))
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={"placeholder": "01XXXXXXXXX"}))
    password = forms.CharField(widget=forms.PasswordInput)
    referral_code = forms.CharField(
        max_length=20, required=False,
        label="রেফারেল কোড (ঐচ্ছিক)",
        help_text="কারো ফোন নম্বর দিয়ে রেফার করা হলে এখানে দিন, দুজনেই পয়েন্ট পাবেন।",
    )

    def clean_phone(self):
        phone = clean_bd_phone(self.cleaned_data["phone"])
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("এই মোবাইল নম্বর দিয়ে আগেই অ্যাকাউন্ট আছে।")
        return phone

    def clean_referral_code(self):
        code = normalize_bd_phone(self.cleaned_data["referral_code"])
        if code and not User.objects.filter(phone=code).exists():
            raise forms.ValidationError("এই রেফারেল কোড (রেফারারের ফোন নম্বর) খুঁজে পাওয়া যায়নি।")
        return code


class OTPForm(forms.Form):
    code = forms.CharField(max_length=6, widget=forms.TextInput(attrs={"placeholder": "৬-সংখ্যার OTP"}))


class ForgotPasswordForm(forms.Form):
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={"placeholder": "01XXXXXXXXX"}))

    def clean_phone(self):
        phone = clean_bd_phone(self.cleaned_data["phone"])
        if not User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("এই মোবাইল নম্বর দিয়ে কোনো অ্যাকাউন্ট পাওয়া যায়নি।")
        return phone


class ResetPasswordForm(forms.Form):
    code = forms.CharField(max_length=6, widget=forms.TextInput(attrs={"placeholder": "৬-সংখ্যার OTP"}))
    new_password = forms.CharField(widget=forms.PasswordInput, label="নতুন পাসওয়ার্ড")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="পাসওয়ার্ড আবার লিখুন")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") and cleaned.get("new_password") != cleaned.get("confirm_password"):
            raise forms.ValidationError("দুটি পাসওয়ার্ড মিলছে না।")
        return cleaned


class LoginForm(forms.Form):
    phone = forms.CharField(max_length=20)
    password = forms.CharField(widget=forms.PasswordInput)

    def clean_phone(self):
        # Normalize only -- don't hard-reject a malformed number here. If
        # it's wrong, no account will match and authentication just fails
        # with the normal "invalid credentials" message, which is the
        # right failure mode for a login form (don't help an attacker
        # distinguish "bad format" from "wrong password" for a real account).
        return normalize_bd_phone(self.cleaned_data["phone"])


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["label", "house_name", "full_address", "landmark", "latitude", "longitude", "is_default"]
        widgets = {
            "full_address": forms.Textarea(attrs={"rows": 3, "placeholder": "রোড, এলাকা, থানা, জেলা"}),
            "house_name": forms.TextInput(attrs={"placeholder": "যেমন: বাড়ি ১২, ফ্ল্যাট ৩বি"}),
            "landmark": forms.TextInput(attrs={"placeholder": "যেমন: আল-ফালাহ মসজিদের পাশে"}),
        }


class GuestOrderPhoneForm(forms.Form):
    phone = forms.CharField(max_length=20)

    def clean_phone(self):
        return clean_bd_phone(self.cleaned_data["phone"])
