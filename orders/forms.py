from django import forms

from accounts.models import Address
from accounts.validators import clean_bd_phone, normalize_bd_phone
from catalog.models import Product
from orders.models import Order


class OrderCreateForm(forms.Form):
    """Checkout form -- product/quantity now come from the session cart
    (orders/cart.py), not this form, since an order can hold multiple
    items."""
    address = forms.ModelChoiceField(queryset=Address.objects.none())
    payment_method = forms.ChoiceField(choices=Order.PaymentMethod.choices)
    is_express = forms.BooleanField(required=False, label="জরুরি ডেলিভারি (Express)")
    promo_code = forms.CharField(required=False, label="প্রোমো কোড (ঐচ্ছিক)")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["address"].queryset = user.addresses.all()


class GuestOrderForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={"placeholder": "01XXXXXXXXX"}))
    house_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={"placeholder": "ফ্ল্যাট/বাড়ির নাম (যেমন: বাড়ি ১২, ফ্ল্যাট ৩বি)"}),
    )
    full_address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3, "placeholder": "রোড, এলাকা, থানা, জেলা"}))
    landmark = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={"placeholder": "নিকটস্থ পরিচিত স্থান (যেমন: আল-ফালাহ মসজিদের পাশে)"}),
    )
    product = forms.ModelChoiceField(queryset=Product.objects.filter(is_active=True))
    quantity = forms.IntegerField(min_value=1, initial=1)
    payment_method = forms.ChoiceField(
        choices=Order.PaymentMethod.choices, initial=Order.PaymentMethod.COD,
        help_text="নতুন গ্রাহকদের জন্য Cash on Delivery সবচেয়ে সহজ।",
    )
    promo_code = forms.CharField(required=False, label="প্রোমো কোড (ঐচ্ছিক)")

    def clean_phone(self):
        return clean_bd_phone(self.cleaned_data["phone"])


class GuestOTPForm(forms.Form):
    code = forms.CharField(max_length=6, widget=forms.TextInput(attrs={"placeholder": "৬-সংখ্যার OTP"}))


class DeliveryExceptionForm(forms.Form):
    reason = forms.ChoiceField(choices=[])
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from orders.models import DeliveryException

        self.fields["reason"].choices = DeliveryException.Reason.choices


class SubscriptionForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.filter(is_active=True))
    address = forms.ModelChoiceField(queryset=Address.objects.none())
    interval = forms.ChoiceField(choices=[])
    custom_days = forms.IntegerField(
        required=False, min_value=1,
        help_text="শুধু 'Custom' interval বাছলে দিন, যেমন প্রতি ১০ দিনে।",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from orders.models import Subscription

        self.fields["interval"].choices = Subscription.Interval.choices
        if user is not None:
            self.fields["address"].queryset = user.addresses.all()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("interval") == "CUSTOM" and not cleaned.get("custom_days"):
            self.add_error("custom_days", "Custom interval-এর জন্য দিনের সংখ্যা দিতে হবে।")
        return cleaned


class AdminPlaceOrderForm(forms.Form):
    """
    Quick order entry for admin/ops staff taking a phone call from a
    customer -- no OTP step (the staff member is the one vouching for the
    customer's identity here, having just spoken to them), but the same
    phone-format validation and normalization as every other phone field.
    """

    full_name = forms.CharField(max_length=150, label="কাস্টমারের নাম", required=False)
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={"placeholder": "01XXXXXXXXX"}))
    house_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={"placeholder": "ফ্ল্যাট/বাড়ির নাম (ঐচ্ছিক)"}),
    )
    full_address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "রোড, এলাকা, থানা, জেলা"}))
    landmark = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={"placeholder": "ল্যান্ডমার্ক (ঐচ্ছিক)"}),
    )
    product = forms.ModelChoiceField(queryset=Product.objects.filter(is_active=True))
    quantity = forms.IntegerField(min_value=1, initial=1)
    payment_method = forms.ChoiceField(choices=Order.PaymentMethod.choices, initial=Order.PaymentMethod.COD)
    is_express = forms.BooleanField(required=False, label="জরুরি ডেলিভারি (Express)")
    promo_code = forms.CharField(required=False, label="প্রোমো কোড (ঐচ্ছিক)")
    use_existing_address = forms.ModelChoiceField(
        queryset=Address.objects.none(), required=False,
        label="অথবা এই কাস্টমারের আগের একটা ঠিকানা বেছে নিন",
        help_text="ফোন নম্বর মিলে যাওয়া কোনো পুরনো কাস্টমার থাকলে তার সংরক্ষিত ঠিকানা এখানে দেখাবে।",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The address queryset depends on the phone number typed into this
        # same form -- has to be set here (from raw self.data, before
        # cleaning) rather than in clean(), since ModelChoiceField validates
        # the submitted value against its queryset during per-field cleaning,
        # which runs before clean() ever sees it. A queryset set in clean()
        # would always be one submission too late.
        raw_phone = normalize_bd_phone(self.data.get("phone", "")) if self.is_bound else ""
        if raw_phone:
            self.fields["use_existing_address"].queryset = Address.objects.filter(user__phone=raw_phone)

    def clean_phone(self):
        return clean_bd_phone(self.cleaned_data["phone"])

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("use_existing_address") and not cleaned.get("full_address"):
            self.add_error("full_address", "নতুন ঠিকানা দিন অথবা উপরের থেকে একটা পুরনো ঠিকানা বেছে নিন।")

        phone = cleaned.get("phone")
        if phone:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            is_new_customer = not User.objects.filter(phone=phone).exists()
            if is_new_customer and not cleaned.get("full_name"):
                self.add_error("full_name", "এটি নতুন গ্রাহক মনে হচ্ছে, তাই নাম দিতে হবে।")
        return cleaned
