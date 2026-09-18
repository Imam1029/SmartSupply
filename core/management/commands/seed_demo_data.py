from django.core.management.base import BaseCommand

from accounts.models import Address, Role
from catalog.models import Product
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create demo users and products so you can click around the app immediately."

    def handle(self, *args, **options):
        if not User.objects.filter(phone="01700000000").exists():
            User.objects.create_superuser(
                username="admin", phone="01700000000", password="admin12345", role=Role.ADMIN
            )
            self.stdout.write(self.style.SUCCESS("Superuser created: phone=01700000000 password=admin12345"))

        if not User.objects.filter(phone="01900000001").exists():
            User.objects.create_user(
                username="01900000001",
                phone="01900000001",
                password="staffpass123",
                first_name="Rahim",
                role=Role.DELIVERY_STAFF,
                is_phone_verified=True,
            )
            self.stdout.write(self.style.SUCCESS("Staff created: phone=01900000001 password=staffpass123"))

        if not User.objects.filter(phone="01800000001").exists():
            cust = User.objects.create_user(
                username="01800000001",
                phone="01800000001",
                password="custpass123",
                first_name="Karim",
                role=Role.CUSTOMER,
                is_phone_verified=True,
            )
            Address.objects.create(
                user=cust, label="Home", full_address="House 12, Road 4, Chattogram", is_default=True
            )
            self.stdout.write(self.style.SUCCESS("Customer created: phone=01800000001 password=custpass123"))

        if not Product.objects.exists():
            Product.objects.create(
                name="19L Water Jar", bottle_size_liters=19, water_price=100, bottle_price=500, available_stock=100
            )
            Product.objects.create(
                name="10L Water Jar", bottle_size_liters=10, water_price=60, bottle_price=350, available_stock=100
            )
            self.stdout.write(self.style.SUCCESS("Demo products created."))

        # Granular RBAC demo users -- is_staff=True so they can log into
        # /admin/, but core.admin_mixins.RoleBasedAdminMixin restricts what
        # they can actually see/edit there based on `role`.
        rbac_demo_users = [
            ("01500000001", "accountantpass", Role.ACCOUNTANT, "Accountant Demo"),
            ("01500000002", "vieweronlypass", Role.VIEW_ONLY, "Viewer Demo"),
            ("01500000003", "opsmanagerpass", Role.OPERATIONS_MANAGER, "Ops Manager Demo"),
        ]
        for phone, password, role, name in rbac_demo_users:
            if not User.objects.filter(phone=phone).exists():
                User.objects.create_user(
                    username=phone, phone=phone, password=password, first_name=name,
                    role=role, is_phone_verified=True, is_staff=True,
                )
                self.stdout.write(self.style.SUCCESS(f"{role.label} created: phone={phone} password={password}"))

        # Demo B2B corporate client
        if not User.objects.filter(phone="01450000001").exists():
            from b2b.models import CorporateClient

            corp_contact = User.objects.create_user(
                username="01450000001", phone="01450000001", password="corppass123",
                first_name="ABC Bank - Office Admin", role=Role.CUSTOMER, is_phone_verified=True,
            )
            billing_addr = Address.objects.create(
                user=corp_contact, label="Office", full_address="ABC Bank HQ, GEC Circle, Chattogram",
                is_default=True,
            )
            CorporateClient.objects.create(
                company_name="ABC Bank Ltd.", contact_person=corp_contact, billing_address=billing_addr,
                credit_limit=20000, payment_terms_days=15,
            )
            self.stdout.write(self.style.SUCCESS(
                "Corporate client created: phone=01450000001 password=corppass123 (login then visit /b2b/dashboard/)"
            ))

        self.stdout.write(self.style.SUCCESS("Seed complete."))
