"""
Django settings for the Smart Water Supply, Delivery & Reusable Bottle
Tracking Platform (Phase 1 MVP).
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from a .env file (if present) so DB/secret settings can be
# kept out of source control. Copy .env.example to .env and edit it.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-replace-this-in-production-please",
)

# SECURITY WARNING: don't run with debug turned on in production!
# Defaults to False (safe) now -- previously defaulted to True, which means
# forgetting to set DJANGO_DEBUG=False in a production .env would silently
# leave the site leaking full tracebacks (source code, local variables,
# this very SECRET_KEY) to any visitor who triggers an error, AND would
# skip the production security block below entirely (it's gated on
# `if not DEBUG`). Add DJANGO_DEBUG=True to your local .env for development.
DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

# Render sets this automatically to the service's *.onrender.com hostname --
# picking it up here means ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS don't need a
# manually-set env var just to get the first deploy working. A custom
# domain added later still needs DJANGO_ALLOWED_HOSTS set explicitly.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # local apps
    "accounts",
    "catalog",
    "bottles",
    "orders",
    "payments",
    "delivery",
    "core",
    "b2b",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Right after SecurityMiddleware, before everything else -- serves
    # STATIC_ROOT directly from the app process with far-future cache
    # headers, so Render (which doesn't serve static files for you the
    # way e.g. a separate static site host would) doesn't need a second
    # service just for CSS/JS.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "smartwater.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "smartwater.wsgi.application"


# Database
# Render (and most PaaS Postgres add-ons) inject a single DATABASE_URL env
# var -- when present, it wins over everything below, so a Render deploy
# needs zero DB-related settings changes, just attaching a Postgres
# instance. Local development is untouched: without DATABASE_URL it falls
# back to the existing MySQL-by-default / sqlite-fallback behavior.

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            # Render's internal Postgres connection is already private/
            # trusted; require SSL only when DEBUG is off, so a local
            # Postgres-via-DATABASE_URL setup (no SSL) still works too.
            ssl_require=not DEBUG,
        )
    }
else:
    USE_MYSQL = os.environ.get("USE_MYSQL", "True") == "True"

    if USE_MYSQL:
        import pymysql

        pymysql.install_as_MySQLdb()

        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.mysql",
                "NAME": os.environ.get("DB_NAME", "smartwater_db"),
                "USER": os.environ.get("DB_USER", "root"),
                "PASSWORD": os.environ.get("DB_PASSWORD", ""),
                "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
                "PORT": os.environ.get("DB_PORT", "3306"),
                "OPTIONS": {
                    "charset": "utf8mb4",
                },
            }
        }
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }


# Custom user model
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization

LANGUAGE_CODE = "bn"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True


# Static & media files

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise: hashed filenames + far-future cache headers, with a fallback
# to the plain file when a referenced asset wasn't actually collected
# (missing manifest entries would otherwise hard-crash the request).
# Only used when DEBUG=False -- the manifest variant requires
# `collectstatic` to have already run and generate staticfiles.json, which
# local runs (runserver, manage.py test) never do, so keep the plain
# storage there or every static tag 404s/errors until you remember to run
# it by hand.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# NOTE for Render: a web service's disk is ephemeral -- wiped on every
# deploy/restart -- so files saved here (product images via ImageField)
# will disappear. Fine for a first deploy / demo, but before real product
# images matter, switch MEDIA storage to Cloudinary/S3 (e.g.
# django-cloudinary-storage) or add a Render persistent disk.

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Business config (simple constants for Phase 1; move to DB-driven Admin
# settings later if needed)
EXPRESS_DELIVERY_FEE = 100
STANDARD_DELIVERY_CHARGE = 0


# ---------------------------------------------------------------------------
# Production security hardening (only active when DEBUG=False)
# NOTE: these assume the site is served over HTTPS. If you deploy behind
# nginx/Cloudflare terminating TLS, also set SECURE_PROXY_SSL_HEADER below,
# otherwise Django won't realise the request was already secure and will
# redirect in a loop.
# ---------------------------------------------------------------------------

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # Start HSTS small (e.g. 3600) and raise it once you're sure HTTPS is
    # stable -- browsers remember this and you cannot take it back early.
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False

    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

    # Render (and most PaaS) terminate TLS at their own proxy and forward
    # to gunicorn over plain HTTP with this header set -- without telling
    # Django to trust it, SECURE_SSL_REDIRECT above sees every request as
    # "not secure" and redirects forever (an infinite redirect loop, not
    # a clean failure). Only trusted when RENDER is set (Render sets this
    # automatically) so a bare-metal/self-hosted deploy behind no proxy
    # doesn't blindly trust a spoofable header.
    if os.environ.get("RENDER"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # Django needs the full scheme+host of the live site to accept POSTs.
    CSRF_TRUSTED_ORIGINS = [
        o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
    ]
    if RENDER_EXTERNAL_HOSTNAME:
        CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

    if SECRET_KEY.startswith("django-insecure-"):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is still the development default. Generate one with:\n"
            "  python -c \"from django.core.management.utils import get_random_secret_key as k; print(k())\"\n"
            "and put it in your .env before running with DEBUG=False."
        )
