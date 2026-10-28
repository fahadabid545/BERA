"""Picks development, staging or production settings from APP_ENV."""

from config.environment import app_environment, load_local_env_file

load_local_env_file()

_environment = app_environment()

if _environment == "development":
    from .development import *  # noqa: F403
elif _environment == "staging":
    from .staging import *  # noqa: F403
else:
    from .production import *  # noqa: F403
