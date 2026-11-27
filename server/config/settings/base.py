import os
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
    "emailing",
    "platform_settings",
    "signin",
    "twostep",
    "audit",
    "activity",
    "plans",
    "usage",
    "notifications",
    "announcements",
    "contact",
    "datarequests",
    "feedback",
    "support",
    "projects",
    "ai",
    "cvs",
    "backups",
    "monitoring",
    "launch",
    "apikeys",
    "chatbot",
    "assistant",
    "freeaccess",
]

# Development only (see development.py): the country the sign-up form pretends the visitor is in.
DEVELOPMENT_PRETEND_COUNTRY = ""

# Only strong, slow, one-way hashes. Company users and admin users each keep theirs in their
# own table (companies, adminusers); Django's own user table is not used.
# Only used to write emails (emailing/templates); the product has no server-rendered pages.
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True}]

# System emails (see emailing/). The sender is one configurable address; links in emails
# point only to WEB_BASE_URL. Development saves messages in .dev-inbox instead of sending.
EMAIL_TIMEOUT = 10
EMAIL_BACKEND = "emailing.backends.DevInboxBackend"
EMAIL_FILE_PATH = BASE_DIR.parent / ".dev-inbox"
# Where uploaded files are kept in development ("local"); staging and production use R2.
FILE_STORAGE_BACKEND = "local"
# Never served directly.
PRIVATE_FILES_ROOT = Path(os.environ.get("PRIVATE_FILES_ROOT") or BASE_DIR.parent / "local_storage")
EMAIL_FROM_ADDRESS = os.environ.get("EMAIL_FROM_ADDRESS", "").strip() or "bera@example.test"
# The sender's display name is the platform name setting, added when each email is sent.
DEFAULT_FROM_EMAIL = EMAIL_FROM_ADDRESS
# The AI provider key. Without one every AI call reports "unavailable" and the screens fall
# back to manual entry.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
# The payment provider's secret key. Test mode only for now: `plans/stripe_client.py` refuses
# any key that is not a test key.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
# Live keys are accepted only when production sets this on purpose (config/environment.py).
STRIPE_ALLOW_LIVE_KEYS = False
# Signs the payment provider's notifications; one that does not match is rejected.
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
WEB_BASE_URL = os.environ.get("WEB_BASE_URL", "").strip().rstrip("/") or "http://localhost:3000"

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
    # How many background processes: staging and production set their own (see deploy/).
    "workers": int(os.environ.get("Q_CLUSTER_WORKERS", "2")),
    # One CV is a read and a score, each with its own AI call of up to `ai.request_timeout_seconds`;
    # the task may run longer than one call, but less than `processing.stuck_minutes`, so a task
    # the queue stops is recovered by the sweep and never run twice at once. `retry` must exceed it.
    "timeout": 240,
    "retry": 300,
    "queue_limit": 50,
    # Seconds between looks at the queue table (the default, 0.2, asks the database five times a
    # second all day for nothing).
    "poll": 2,
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

# Database backups (see backups/). Production sets all of these; development may use a local
# folder (BACKUP_LOCAL_FOLDER) instead of the backup bucket.
BACKUP_DATABASE_URL = os.environ.get("BACKUP_DATABASE_URL", "").strip()
RESTORE_TEST_DATABASE_URL = os.environ.get("RESTORE_TEST_DATABASE_URL", "").strip()
BACKUP_ENCRYPTION_KEY_ID = os.environ.get("BACKUP_ENCRYPTION_KEY_ID", "").strip()
BACKUP_ENCRYPTION_KEY = os.environ.get("BACKUP_ENCRYPTION_KEY", "").strip()
BACKUP_PREVIOUS_KEYS = os.environ.get("BACKUP_PREVIOUS_KEYS", "").strip()
BACKUP_R2_ACCESS_KEY_ID = os.environ.get("BACKUP_R2_ACCESS_KEY_ID", "").strip()
BACKUP_R2_SECRET_ACCESS_KEY = os.environ.get("BACKUP_R2_SECRET_ACCESS_KEY", "").strip()
BACKUP_R2_BUCKET = os.environ.get("BACKUP_R2_BUCKET", "").strip()
BACKUP_LOCAL_FOLDER = os.environ.get("BACKUP_LOCAL_FOLDER") or BASE_DIR.parent / ".dev-backups"

# Heartbeat pings (see monitoring/heartbeat.py): addresses of an outside dead-man service. Each is a
# secret, because it names our check. Required in production; optional (and separate) in staging.
HEARTBEAT_URL = os.environ.get("HEARTBEAT_URL", "").strip()
BACKUP_HEARTBEAT_URL = os.environ.get("BACKUP_HEARTBEAT_URL", "").strip()
