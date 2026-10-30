from pathlib import Path

import dj_database_url

from config.database import URL_SETTING_BY_ROLE, database_role
from config.environment import require_field_keys, require_settings, require_signing_secrets

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATABASE_ROLE = database_role()
_database_url_setting = URL_SETTING_BY_ROLE[DATABASE_ROLE]
_required = require_settings(["DJANGO_SECRET_KEY", _database_url_setting])
SECRET_KEY = _required["DJANGO_SECRET_KEY"]
# Company and admin tokens use different secrets, so neither can open the other's routes.
TOKEN_SIGNING_SECRETS = require_signing_secrets()
# Keys that encrypt personal data and make it searchable by hash.
FIELD_KEYS = require_field_keys()
DATABASES = {"default": dj_database_url.parse(_required[_database_url_setting], conn_max_age=60)}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "rest_framework",
    "django_q",
    "core",
    "companies",
    "adminusers",
    "platform_settings",
    "signin",
]

# Only strong, slow, one-way hashes. Company users and admin users each keep theirs in their
# own table (companies, adminusers); Django's own user table is not used.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]

MIDDLEWARE = [
    "core.middleware.RequestContextMiddleware",
    # Before the middlewares that can refuse a request, so refusals carry its headers too.
    "django.middleware.security.SecurityMiddleware",
    "core.browser_protection.SecurityHeadersMiddleware",
    "core.browser_protection.OriginPolicyMiddleware",
    "core.middleware.RequestSizeLimitMiddleware",
    "django.middleware.common.CommonMiddleware",
]

# Headers added by Django's SecurityMiddleware on every response. (nosniff and the
# same-origin opener policy are on by default; HSTS is switched on in staging and production.)
SECURE_REFERRER_POLICY = "no-referrer"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# How many of our own proxies sit in front of the server (they add to X-Forwarded-For).
# 0 means visitors connect directly. See core/client_address.py.
TRUSTED_PROXY_COUNT = 0

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "core.exception_handler.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # Private by default: a route is open to visitors only when it is on the public list
    # (core/public_routes.py) and says so with PublicAccess. The token ticket adds the
    # authentication classes that make a valid sign-in possible.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    # Django's own user model is not installed (accounts live in companies and adminusers).
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_PERMISSION_CLASSES": ["core.permissions.IsSignedIn"],
    # Every view has the general per-user limit; views with their own limits add to it.
    "DEFAULT_THROTTLE_CLASSES": ["core.throttles.OtherRequestsThrottle"],
}

# Background jobs run in a separate worker process, queued in PostgreSQL.
Q_CLUSTER = {
    "name": "bera",
    "orm": "default",
    "workers": 2,
    "timeout": 60,
    "retry": 120,
    "queue_limit": 50,
}

# One log format for everything. Handlers on the named loggers replace Django's
# defaults so no unfiltered output remains.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_context": {"()": "core.logging_setup.RequestContextFilter"}},
    "formatters": {"standard": {"()": "core.logging_setup.RedactingFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_context"],
            "formatter": "standard",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": [], "level": "INFO", "propagate": True},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
