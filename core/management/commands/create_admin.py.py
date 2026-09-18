"""Creates (or updates) an initial superuser from DJANGO_SUPERUSER_* env
vars. Exists because Render's free tier has no Shell access, so
`python manage.py createsuperuser` can't be run interactively after
deploy -- this runs automatically from build.sh on every deploy instead.

Safe to run repeatedly: a no-op when the env vars aren't set (e.g. local
dev, or any deploy that isn't meant to auto-provision an admin), and
idempotent when the user already exists (updates the password/role
instead of failing on the unique constraint).
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Role


class Command(BaseCommand):
    help = "Create or update the initial superuser from DJANGO_SUPERUSER_* environment variables."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        phone = os.environ.get("DJANGO_SUPERUSER_PHONE")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")

        if not username or not password or not phone:
            self.stdout.write("DJANGO_SUPERUSER_* env vars not fully set -- skipping admin creation.")
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"phone": phone, "email": email},
        )
        user.phone = phone
        user.email = email or user.email
        user.role = Role.SUPER_ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated existing superuser '{username}'."))