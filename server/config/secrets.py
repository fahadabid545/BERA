"""The one list of settings the app cannot run without, and the start-up check for it.

In staging and production every entry must be present, and every secret must be a real
value, not a placeholder such as the fake ones in `.env.example`. Development only needs
the entries to exist. The check names what is wrong, never the values.

A ticket that adds a feature with its own key (AI, payments, email, storage...) adds the
key to REQUIRED_SETTINGS in that ticket, with a line in `.env.example` and in the README.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from core.errors import ConfigurationError

from .environment import MIN_SIGNING_SECRET_LENGTH

REAL_ENVIRONMENTS = ("staging", "production")


@dataclass(frozen=True)
class RequiredSetting:
    name: str
    # A secret must not be a placeholder; other settings (like a count) are only required.
    secret: bool = True
    # Which processes hold it. The app never holds the migrator's password, nor the reverse.
    roles: tuple = ("app", "migrations")


REQUIRED_SETTINGS = [
    RequiredSetting("DJANGO_SECRET_KEY"),
    RequiredSetting("DATABASE_URL", roles=("app",)),
    RequiredSetting("MIGRATION_DATABASE_URL", roles=("migrations",)),
    RequiredSetting("FIELD_ENCRYPTION_KEY"),
    RequiredSetting("FIELD_HASH_KEY"),
    RequiredSetting("JWT_COMPANY_SECRET"),
    RequiredSetting("JWT_ADMIN_SECRET"),
    RequiredSetting("TRUSTED_PROXY_COUNT", secret=False),
]
# Needed to run at all, even on a developer's computer. Everything else on the list
# above is only enforced where real people's data lives.
REQUIRED_IN_DEVELOPMENT = {
    "DJANGO_SECRET_KEY",
    "DATABASE_URL",
    "MIGRATION_DATABASE_URL",
    "JWT_COMPANY_SECRET",
    "JWT_ADMIN_SECRET",
    "FIELD_ENCRYPTION_KEY",
    "FIELD_HASH_KEY",
}

PLACEHOLDER_WORDS = (
    "fake",
    "changeme",
    "change-me",
    "change_me",
    "placeholder",
    "example",
    "replace",
    "your-",
    "your_",
    "xxxx",
    "todo",
    "dummy",
    "sample",
    "insert",
    "secret-key-here",
    "password",
)


def looks_like_placeholder(value):
    lowered = value.strip().lower()
    return (
        len(lowered) < MIN_SIGNING_SECRET_LENGTH // 2
        or len(set(lowered)) <= 3
        or any(word in lowered for word in PLACEHOLDER_WORDS)
    )


def _secret_part(name, value):
    """The part of a setting that is secret: the password inside a database address."""
    if not name.endswith("DATABASE_URL"):
        return value
    try:
        return urlsplit(value).password or ""
    except ValueError:
        return ""


def check_required_settings(environ, app_env, role="app"):
    """Raises ConfigurationError naming every missing or placeholder setting for this role."""
    real = app_env in REAL_ENVIRONMENTS
    missing, placeholders = [], []
    for setting in REQUIRED_SETTINGS:
        if role not in setting.roles:
            continue
        if not real and setting.name not in REQUIRED_IN_DEVELOPMENT:
            continue
        value = environ.get(setting.name, "").strip()
        if not value:
            missing.append(setting.name)
        elif real and setting.secret and looks_like_placeholder(_secret_part(setting.name, value)):
            placeholders.append(setting.name)
    if missing or placeholders:
        parts = []
        if missing:
            parts.append(f"Missing required settings: {', '.join(missing)}.")
        if placeholders:
            parts.append(f"Still placeholders, set real values: {', '.join(placeholders)}.")
        raise ConfigurationError(
            " ".join(parts), {"missing": missing, "placeholders": placeholders}
        )
