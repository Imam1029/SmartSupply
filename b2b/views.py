from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CorporateOrderForm
from .models import CorporateClient
from .services import place_corporate_order


@login_required
def corporate_dashboard_view(request):
    clients = CorporateClient.objects.filter(contact_person=request.user, is_active=True)
    if not clients.exists():
        messages.info(request, "আপনার সাথে যুক্ত কোনো Corporate Account নেই। Admin-এর সাথে যোগাযোগ করুন।")
        return redirect("core:home")
    client = clients.first()
    invoices = client.invoices.all()
    return render(request, "b2b/dashboard.html", {"client": client, "invoices": invoices})


@login_required
def corporate_order_create_view(request, client_id):
    client = get_object_or_404(CorporateClient, pk=client_id, contact_person=request.user, is_active=True)

    if request.method == "POST":
        form = CorporateOrderForm(request.POST, client=client)
        if form.is_valid():
            order, error = place_corporate_order(
                client=client,
                address=client.billing_address,
                product=form.cleaned_data["product"],
                quantity=form.cleaned_data["quantity"],
                placed_by=request.user,
            )
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f"Corporate অর্ডার তৈরি হয়েছে (Postpaid)। Order ID: {order.order_uid}")
                return redirect("b2b:dashboard")
    else:
        form = CorporateOrderForm(client=client)

    return render(request, "b2b/order_create.html", {"form": form, "client": client})


@login_required
def invoice_detail_view(request, pk):
    client = get_object_or_404(CorporateClient, contact_person=request.user)
    invoice = get_object_or_404(client.invoices, pk=pk)
    return render(request, "b2b/invoice_detail.html", {"invoice": invoice})
