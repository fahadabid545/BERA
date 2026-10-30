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
