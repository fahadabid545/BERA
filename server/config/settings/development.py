import os

from config.environment import parse_pretend_country

from .base import *  # noqa: F403

APP_ENV = "development"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
# The web app on its development port.
ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
# There is no Cloudflare locally, so the sign-up form's detected country can be faked, for
# example DEVELOPMENT_PRETEND_COUNTRY=PK. Staging and production never read this.
DEVELOPMENT_PRETEND_COUNTRY = parse_pretend_country(  # noqa: F405
    os.environ.get("DEVELOPMENT_PRETEND_COUNTRY", "")
)
