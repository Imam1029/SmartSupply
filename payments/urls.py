from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("gateway/<int:pk>/", views.gateway_demo_page_view, name="gateway_demo"),
    path("gateway/<int:pk>/callback/", views.gateway_callback_view, name="gateway_callback"),
]
