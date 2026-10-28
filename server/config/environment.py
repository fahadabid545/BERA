"""Reads settings from the environment. Secrets never come from anywhere else."""

import os
from pathlib import Path

from core.errors import ConfigurationError
from dotenv import load_dotenv

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
