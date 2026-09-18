from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("register/verify-otp/", views.verify_registration_otp_view, name="verify_registration_otp"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("forgot-password/", views.forgot_password_view, name="forgot_password"),
    path("reset-password/", views.reset_password_view, name="reset_password"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("notifications/", views.notifications_list_view, name="notifications"),
    path("addresses/", views.address_list_view, name="addresses"),
    path("addresses/<int:pk>/edit/", views.address_edit_view, name="address_edit"),
    path("addresses/<int:pk>/delete/", views.address_delete_view, name="address_delete"),
]
