"""Reads settings from the environment. Secrets never come from anywhere else."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from dotenv import load_dotenv

from core.errors import ConfigurationError

ENVIRONMENTS = ("development", "staging", "production")
LOCAL_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def load_local_env_file():
    """Real environment variables always win over the local .env file."""
    load_dotenv(LOCAL_ENV_FILE)


def app_environment(environ=os.environ):
    name = environ.get("APP_ENV", "").strip()
    if name not in ENVIRONMENTS:
        raise ConfigurationError(
            f"APP_ENV must be one of {', '.join(ENVIRONMENTS)}.",
            {"allowed": list(ENVIRONMENTS)},
        )
    return name


def require_settings(names, environ=os.environ):
    """Return the named settings, or refuse to continue listing every missing name."""
    values = {name: environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigurationError(
            f"Missing required settings: {', '.join(missing)}. "
            "Copy .env.example to .env (development) or set them in the environment.",
            {"missing": missing},
        )
    return values


MIN_SIGNING_SECRET_LENGTH = 32


def require_distinct_long_secrets(names, environ=os.environ):
    """Secrets that must each be long enough and different from each other, so that one
    leaking or being guessed never unlocks the other."""
    values = require_settings(names, environ)
    too_short = [name for name, value in values.items() if len(value) < MIN_SIGNING_SECRET_LENGTH]
    if too_short:
        raise ConfigurationError(
            f"{', '.join(too_short)} must be at least {MIN_SIGNING_SECRET_LENGTH} characters.",
            {"too_short": too_short},
        )
    if len(set(values.values())) < len(values):
        raise ConfigurationError(
            f"{' and '.join(names)} must be different.", {"must_differ": list(names)}
        )
    return values


def require_signing_secrets(environ=os.environ):
    """The two token-signing secrets: a company token can never pass as an admin one."""
    values = require_distinct_long_secrets(["JWT_COMPANY_SECRET", "JWT_ADMIN_SECRET"], environ)
    return {"company": values["JWT_COMPANY_SECRET"], "admin": values["JWT_ADMIN_SECRET"]}


def require_field_keys(environ=os.environ):
    """The two keys protecting personal data in the database (see core/field_protection.py)."""
    values = require_distinct_long_secrets(["FIELD_ENCRYPTION_KEY", "FIELD_HASH_KEY"], environ)
    return {"encryption": values["FIELD_ENCRYPTION_KEY"], "hash": values["FIELD_HASH_KEY"]}


def parse_origins(text):
    """A comma separated list of https web addresses, such as https://app.example.com."""
    origins = [origin.strip().rstrip("/") for origin in text.split(",") if origin.strip()]
    insecure = [origin for origin in origins if not origin.startswith("https://")]
    if not origins or insecure:
        raise ConfigurationError(
            "ALLOWED_ORIGINS must list https web addresses.", {"not_https": insecure}
        )
    return origins


MAX_TRUSTED_PROXIES = 5


def parse_proxy_count(text):
    """How many of our own proxies sit in front of the server; wrong guesses weaken limits."""
    if not text.isdigit() or int(text) > MAX_TRUSTED_PROXIES:
        raise ConfigurationError(
            f"TRUSTED_PROXY_COUNT must be a whole number from 0 to {MAX_TRUSTED_PROXIES}.",
        )
    return int(text)


def parse_web_base_url(text):
    """The website's own address, used for every link in an email (https, no path)."""
    address = text.strip().rstrip("/")
    parts = urlsplit(address)
    if parts.scheme != "https" or not parts.netloc or parts.path or parts.query or parts.fragment:
        raise ConfigurationError(
            "WEB_BASE_URL must be the https address of the website, such as https://app.example.com."
        )
    return address


def parse_sender_address(text):
    address = text.strip()
    try:
        validate_email(address)
    except ValidationError:
        raise ConfigurationError("EMAIL_FROM_ADDRESS must be a valid email address.") from None
    return address
