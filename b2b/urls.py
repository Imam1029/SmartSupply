from django.urls import path

from . import views

app_name = "b2b"

urlpatterns = [
    path("dashboard/", views.corporate_dashboard_view, name="dashboard"),
    path("<int:client_id>/order/new/", views.corporate_order_create_view, name="order_create"),
    path("invoices/<int:pk>/", views.invoice_detail_view, name="invoice_detail"),
]
