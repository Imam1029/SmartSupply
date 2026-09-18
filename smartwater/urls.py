from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("products/", include("catalog.urls")),
    path("orders/", include("orders.urls")),
    path("payments/", include("payments.urls")),
    path("staff/", include("delivery.urls")),
    path("b2b/", include("b2b.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
