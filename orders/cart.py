"""
Session-based cart -- lets a customer add multiple products before
checking out (previously an "order" could only ever contain one product).
Deliberately not a DB model: a cart is pre-commitment scratch state, not a
business record: nothing worth auditing/reporting on happens until it
becomes an actual Order at checkout, so a DB table (with cleanup, orphaned
rows from abandoned carts, etc.) would be overhead for no real benefit here.
"""

SESSION_KEY = "cart"


class Cart:
    def __init__(self, request):
        self.session = request.session
        self._data = self.session.get(SESSION_KEY, {})

    def _save(self):
        self.session[SESSION_KEY] = self._data
        self.session.modified = True

    def add(self, product_id: int, quantity: int = 1):
        key = str(product_id)
        self._data[key] = self._data.get(key, 0) + max(1, quantity)
        self._save()

    def set_quantity(self, product_id: int, quantity: int):
        key = str(product_id)
        if quantity <= 0:
            self._data.pop(key, None)
        else:
            self._data[key] = quantity
        self._save()

    def remove(self, product_id: int):
        self._data.pop(str(product_id), None)
        self._save()

    def clear(self):
        self._data = {}
        self._save()

    def __len__(self):
        return sum(self._data.values())

    def __bool__(self):
        return bool(self._data)

    def raw_items(self):
        """{"<product_id>": quantity} exactly as stored -- for internal use."""
        return dict(self._data)

    def line_items(self):
        """
        Resolved cart lines with live Product objects and pricing --
        products that were deleted/deactivated since being added are
        silently dropped (and removed from the session) rather than
        crashing the cart page.
        """
        from catalog.models import Product

        product_ids = [int(pid) for pid in self._data]
        products = {p.pk: p for p in Product.objects.filter(pk__in=product_ids, is_active=True)}

        lines = []
        changed = False
        for pid_str, qty in list(self._data.items()):
            product = products.get(int(pid_str))
            if product is None:
                del self._data[pid_str]
                changed = True
                continue
            lines.append({
                "product": product,
                "quantity": qty,
                "water_subtotal": product.water_price * qty,
                "bottle_subtotal": product.bottle_price * qty,
            })
        if changed:
            self._save()
        return lines
