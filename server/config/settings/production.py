from config.environment import require_settings

from .base import *  # noqa: F403

APP_ENV = "production"
DEBUG = False
ALLOWED_HOSTS = [
    host.strip() for host in require_settings(["ALLOWED_HOSTS"])["ALLOWED_HOSTS"].split(",")
]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
