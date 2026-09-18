from django import forms

from catalog.models import Product

from .models import CorporateClient


class CorporateOrderForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.filter(is_active=True))
    quantity = forms.IntegerField(min_value=1, initial=20, help_text="B2B ক্লায়েন্টরা সাধারণত ২০-১০০ বোতল একসাথে অর্ডার করে।")

    def __init__(self, *args, client=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
