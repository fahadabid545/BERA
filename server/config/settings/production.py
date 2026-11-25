from config.environment import (
    parse_origins,
    parse_proxy_count,
    refuse_staging_email_folder,
    require_settings,
    stripe_live_allowed,
)

from .base import *  # noqa: F403
from .deployed import *  # noqa: F403

APP_ENV = "production"
DEBUG = False
ALLOWED_HOSTS = [
    host.strip() for host in require_settings(["ALLOWED_HOSTS"])["ALLOWED_HOSTS"].split(",")
]
# Only the real website addresses (https) may use the API from a browser.
ALLOWED_ORIGINS = parse_origins(require_settings(["ALLOWED_ORIGINS"])["ALLOWED_ORIGINS"])
TRUSTED_PROXY_COUNT = parse_proxy_count(
    require_settings(["TRUSTED_PROXY_COUNT"])["TRUSTED_PROXY_COUNT"]
)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000  # one year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Production sends real email through SMTP and never saves it to a folder.
refuse_staging_email_folder()
_smtp = require_settings(["EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"])
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = _smtp["EMAIL_HOST"]
EMAIL_HOST_USER = _smtp["EMAIL_HOST_USER"]
EMAIL_HOST_PASSWORD = _smtp["EMAIL_HOST_PASSWORD"]
EMAIL_PORT = 587
EMAIL_USE_TLS = True
# Real card payments need an explicit decision (STRIPE_ALLOW_LIVE_KEYS=true); see README.
STRIPE_ALLOW_LIVE_KEYS = stripe_live_allowed("production")
