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


def parse_pretend_country(text):
    """A country code for the sign-up form to pretend, or "" for none (development only)."""
    from companies.countries import COUNTRY_CODES

    code = text.strip().upper()
    if code and code not in COUNTRY_CODES:
        raise ConfigurationError("DEVELOPMENT_PRETEND_COUNTRY must be a two-letter country code.")
    return code


SMTP_SETTING_NAMES = ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD")
LIVE_STRIPE_PREFIXES = ("sk_live_", "rk_live_")
TEST_STRIPE_PREFIXES = ("sk_test_", "rk_test_")


def staging_email_folder(environ=os.environ):
    """Staging saves its emails in a folder and sends none. It refuses to start with any real
    email account set, so a copied production file can never make it email real people."""
    present = [name for name in SMTP_SETTING_NAMES if environ.get(name, "").strip()]
    if present:
        raise ConfigurationError(
            f"Staging must not have a real email account: remove {', '.join(present)}.",
            {"present": present},
        )
    return require_settings(["STAGING_EMAIL_FOLDER"], environ)["STAGING_EMAIL_FOLDER"]


def refuse_staging_email_folder(environ=os.environ):
    """Production must really send email: the folder is for staging only."""
    if environ.get("STAGING_EMAIL_FOLDER", "").strip():
        raise ConfigurationError("Production must not use the staging email folder.")


def stripe_live_allowed(app_env, environ=os.environ):
    """Real card payments stay off until the owner says so with STRIPE_ALLOW_LIVE_KEYS=true in
    production. Staging never takes real payments, whatever its settings say. A live key without
    the flag (or any live key in staging) stops the start."""
    flag = environ.get("STRIPE_ALLOW_LIVE_KEYS", "").strip().lower()
    if flag not in ("", "true", "false"):
        raise ConfigurationError("STRIPE_ALLOW_LIVE_KEYS must be true or false.")
    allowed = flag == "true"
    key = environ.get("STRIPE_SECRET_KEY", "").strip()
    if app_env == "staging" and (allowed or key.startswith(LIVE_STRIPE_PREFIXES)):
        raise ConfigurationError("Staging must use payment test keys only.")
    if key.startswith(LIVE_STRIPE_PREFIXES) and not allowed:
        raise ConfigurationError(
            "A live payment key needs STRIPE_ALLOW_LIVE_KEYS=true, which the owner sets only "
            "after the tax decision (BERA-170)."
        )
    if key and not key.startswith(TEST_STRIPE_PREFIXES + LIVE_STRIPE_PREFIXES):
        raise ConfigurationError("STRIPE_SECRET_KEY is not a payment provider key.")
    return allowed
