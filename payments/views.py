from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.utils import log_action

from .gateways import verify_payment
from .models import Payment


@login_required
def gateway_demo_page_view(request, pk):
    """Simulates the redirect to bKash/Nagad's own payment page.

    In production this view disappears entirely -- `initiate_payment()` in
    gateways.py would return the *real* bKash/Nagad redirect URL and the
    user would leave our site, then come back to a callback URL. This page
    stands in for that round-trip so the whole checkout can be demoed
    without real merchant credentials.
    """
    payment = get_object_or_404(Payment, pk=pk, order__customer=request.user)
    if payment.status not in (Payment.Status.INITIATED, Payment.Status.FAILED):
        messages.info(request, "এই পেমেন্ট আগেই প্রসেস হয়ে গেছে।")
        return redirect("orders:order_detail", pk=payment.order.pk)
    if payment.status == Payment.Status.FAILED:
        payment.status = Payment.Status.INITIATED
        payment.save()
    return render(request, "payments/gateway_demo.html", {"payment": payment})


@login_required
def gateway_callback_view(request, pk):
    """Simulates the provider calling us back after the user approves/declines
    payment on their page. `outcome` would normally come from the provider's
    signed callback payload -- here it's just which demo button was clicked."""
    payment = get_object_or_404(Payment, pk=pk, order__customer=request.user)
    outcome = request.POST.get("outcome", "success")

    result = verify_payment(payment.method, payment.transaction_id)

    if outcome == "success" and result.success:
        payment.status = Payment.Status.SUCCESS
        payment.gateway_response = {**(payment.gateway_response or {}), "callback": result.raw_response}
        payment.save()
        log_action(request.user, "PAYMENT_SUCCESS", "Payment", payment.pk, method=payment.method)
        messages.success(request, f"{payment.get_method_display()} পেমেন্ট সফল হয়েছে।")
    else:
        payment.status = Payment.Status.FAILED
        payment.save()
        log_action(request.user, "PAYMENT_FAILED", "Payment", payment.pk, method=payment.method)
        messages.error(request, "পেমেন্ট ব্যর্থ হয়েছে বা বাতিল করা হয়েছে। আবার চেষ্টা করুন।")

    return redirect("orders:order_detail", pk=payment.order.pk)
