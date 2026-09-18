from django.db import models


class Product(models.Model):
    """A drinking-water product (defined by bottle size)."""

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    bottle_size_liters = models.DecimalField(max_digits=5, decimal_places=2)
    water_price = models.DecimalField(max_digits=10, decimal_places=2)
    bottle_price = models.DecimalField(max_digits=10, decimal_places=2)
    available_stock = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=10)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["bottle_size_liters"]

    def __str__(self):
        return f"{self.name} ({self.bottle_size_liters}L)"

    @property
    def is_low_stock(self):
        return self.available_stock <= self.low_stock_threshold

    @property
    def first_purchase_total(self):
        return self.water_price + self.bottle_price
