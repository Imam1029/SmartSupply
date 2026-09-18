# Generated manually 2026-09-16
# Multi-item cart support: OrderItem now tracks refill/first-purchase per
# item (a mixed cart can have both), and Order.order_type gains a MIXED
# choice for order-list display purposes -- delivery views read
# OrderItem.is_refill now, not this field.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0004_order_placed_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='is_refill',
            field=models.BooleanField(
                default=False,
                help_text='Per-item refill vs first-purchase (multi-item cart means one order can mix both) -- '
                          'set at order creation, read by delivery views instead of the old whole-order Order.order_type.',
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='order_type',
            field=models.CharField(
                choices=[('FIRST_PURCHASE', 'First Purchase'), ('REFILL', 'Refill'), ('MIXED', 'Mixed (Multi-item)')],
                max_length=20,
            ),
        ),
    ]
