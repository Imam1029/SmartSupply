from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.utils import send_otp

from .forms import AddressForm, ForgotPasswordForm, LoginForm, OTPForm, RegisterForm, ResetPasswordForm
from .models import OTP, Address, Referral, Role

User = get_user_model()


def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            request.session["pending_registration"] = {
                "full_name": form.cleaned_data["full_name"],
                "phone": form.cleaned_data["phone"],
                "password": form.cleaned_data["password"],
                "referral_code": form.cleaned_data.get("referral_code"),
            }
            send_otp(form.cleaned_data["phone"], OTP.Purpose.REGISTRATION)
            messages.info(request, "আপনার মোবাইলে OTP পাঠানো হয়েছে (console log দেখুন - dev mode)।")
            return redirect("accounts:verify_registration_otp")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


def verify_registration_otp_view(request):
    pending = request.session.get("pending_registration")
    if not pending:
        return redirect("accounts:register")

    if request.method == "POST":
        form = OTPForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            otp = (
                OTP.objects.filter(phone=pending["phone"], purpose=OTP.Purpose.REGISTRATION, is_used=False)
                .order_by("-created_at")
                .first()
            )
            if otp and otp.is_valid() and otp.check_code(code):
                otp.is_used = True
                otp.save()
                names = pending["full_name"].split(" ", 1)
                user = User.objects.create_user(
                    username=pending["phone"],
                    phone=pending["phone"],
                    password=pending["password"],
                    first_name=names[0],
                    last_name=names[1] if len(names) > 1 else "",
                    role=Role.CUSTOMER,
                    is_phone_verified=True,
                )

                referral_code = pending.get("referral_code")
                if referral_code:
                    referrer = User.objects.filter(phone=referral_code).first()
                    if referrer and referrer.pk != user.pk:
                        Referral.objects.create(referrer=referrer, referred_user=user)

                del request.session["pending_registration"]
                auth_login(request, user)
                messages.success(request, "রেজিস্ট্রেশন সম্পন্ন! স্বাগতম।")
                return redirect("core:home")
            messages.error(request, "OTP সঠিক নয় বা মেয়াদ শেষ হয়ে গেছে।")
    else:
        form = OTPForm()
    return render(request, "accounts/verify_otp.html", {"form": form, "phone": pending["phone"]})


def login_view(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request, username=form.cleaned_data["phone"], password=form.cleaned_data["password"]
            )
            if user is not None:
                auth_login(request, user)
                messages.success(request, "লগইন সফল হয়েছে।")
                if user.role == Role.DELIVERY_STAFF:
                    return redirect("delivery:staff_dashboard")
                return redirect("core:home")
            messages.error(request, "মোবাইল নম্বর বা পাসওয়ার্ড ভুল।")
    else:
        form = LoginForm()
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    messages.info(request, "লগআউট হয়ে গেছেন।")
    return redirect("core:home")


def forgot_password_view(request):
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data["phone"]
            request.session["password_reset_phone"] = phone
            send_otp(phone, OTP.Purpose.PASSWORD_RESET)
            messages.info(request, "আপনার মোবাইলে OTP পাঠানো হয়েছে।")
            return redirect("accounts:reset_password")
    else:
        form = ForgotPasswordForm()
    return render(request, "accounts/forgot_password.html", {"form": form})


def reset_password_view(request):
    phone = request.session.get("password_reset_phone")
    if not phone:
        return redirect("accounts:forgot_password")

    if request.method == "POST":
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            otp = (
                OTP.objects.filter(phone=phone, purpose=OTP.Purpose.PASSWORD_RESET, is_used=False)
                .order_by("-created_at")
                .first()
            )
            if otp and otp.is_valid() and otp.check_code(code):
                otp.is_used = True
                otp.save()
                user = User.objects.get(phone=phone)
                user.set_password(form.cleaned_data["new_password"])
                user.save()
                del request.session["password_reset_phone"]
                messages.success(request, "পাসওয়ার্ড পরিবর্তন হয়েছে। এখন লগইন করুন।")
                return redirect("accounts:login")
            messages.error(request, "OTP সঠিক নয় বা মেয়াদ শেষ হয়ে গেছে।")
    else:
        form = ResetPasswordForm()
    return render(request, "accounts/reset_password.html", {"form": form, "phone": phone})


@login_required
def dashboard_view(request):
    orders = request.user.orders.select_related("delivery_address").prefetch_related("items")[:20]
    addresses = request.user.addresses.all()
    held_bottles = request.user.bottle_holdings.filter(quantity__gt=0).select_related("product")
    return render(
        request,
        "accounts/dashboard.html",
        {"orders": orders, "addresses": addresses, "held_bottles": held_bottles},
    )


@login_required
def address_list_view(request):
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            if address.is_default:
                request.user.addresses.update(is_default=False)
            address.save()
            messages.success(request, "নতুন ঠিকানা যোগ হয়েছে।")
            return redirect("accounts:addresses")
    else:
        form = AddressForm()
    addresses = request.user.addresses.all()
    return render(request, "accounts/addresses.html", {"form": form, "addresses": addresses})


@login_required
def address_edit_view(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            updated = form.save(commit=False)
            if updated.is_default:
                request.user.addresses.exclude(pk=address.pk).update(is_default=False)
            updated.save()
            messages.success(request, "ঠিকানা আপডেট হয়েছে।")
            return redirect("accounts:addresses")
    else:
        form = AddressForm(instance=address)
    return render(request, "accounts/address_edit.html", {"form": form, "address": address})


@login_required
def notifications_list_view(request):
    from django.core.paginator import Paginator

    if request.method == "POST" and request.POST.get("mark_all_read"):
        request.user.notifications.filter(is_read=False).update(is_read=True)
        messages.success(request, "সব নোটিফিকেশন পড়া হয়েছে বলে চিহ্নিত হলো।")
        return redirect("accounts:notifications")

    all_notifications = request.user.notifications.all()
    paginator = Paginator(all_notifications, 15)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "accounts/notifications.html", {"page_obj": page_obj})


@login_required
def address_delete_view(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.delete()
    messages.info(request, "ঠিকানা মুছে ফেলা হয়েছে।")
    return redirect("accounts:addresses")
