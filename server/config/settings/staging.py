from config.environment import (
    parse_origins,
    parse_proxy_count,
    require_settings,
    staging_email_folder,
    stripe_live_allowed,
)

from .base import *  # noqa: F403
from .deployed import *  # noqa: F403

APP_ENV = "staging"
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

# Staging sends no real email: every message is saved as a readable file in this folder
# (`python manage.py list_staging_emails` shows them) and it takes no real payments.
EMAIL_BACKEND = "emailing.backends.DevInboxBackend"
EMAIL_FILE_PATH = staging_email_folder()
STRIPE_ALLOW_LIVE_KEYS = stripe_live_allowed("staging")
