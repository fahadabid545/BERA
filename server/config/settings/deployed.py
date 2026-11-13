"""What staging and production share beyond the base settings: real email through SMTP."""

from config.environment import parse_sender_address, parse_web_base_url, require_settings

_email = require_settings(
    ["EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "EMAIL_FROM_ADDRESS", "WEB_BASE_URL"]
)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = _email["EMAIL_HOST"]
EMAIL_HOST_USER = _email["EMAIL_HOST_USER"]
EMAIL_HOST_PASSWORD = _email["EMAIL_HOST_PASSWORD"]
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_FROM_ADDRESS = parse_sender_address(_email["EMAIL_FROM_ADDRESS"])
DEFAULT_FROM_EMAIL = f"Bera <{EMAIL_FROM_ADDRESS}>"
WEB_BASE_URL = parse_web_base_url(_email["WEB_BASE_URL"])

# Uploaded files live in a private Cloudflare R2 bucket (see privatefiles/r2.py).
_r2 = require_settings(["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"])
FILE_STORAGE_BACKEND = "r2"
R2_ACCOUNT_ID = _r2["R2_ACCOUNT_ID"]
R2_ACCESS_KEY_ID = _r2["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = _r2["R2_SECRET_ACCESS_KEY"]
R2_BUCKET = _r2["R2_BUCKET"]
