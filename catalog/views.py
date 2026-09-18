from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Product


def product_list_view(request):
    all_products = Product.objects.filter(is_active=True)

    query = request.GET.get("q", "").strip()
    if query:
        all_products = all_products.filter(Q(name__icontains=query) | Q(description__icontains=query))

    max_price = request.GET.get("max_price", "").strip()
    if max_price.isdigit():
        all_products = all_products.filter(water_price__lte=int(max_price))

    paginator = Paginator(all_products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request, "catalog/product_list.html",
        {"page_obj": page_obj, "query": query, "max_price": max_price},
    )


def product_detail_view(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    return render(request, "catalog/product_detail.html", {"product": product})
