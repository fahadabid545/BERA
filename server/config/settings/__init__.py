"""Picks development, staging or production settings from APP_ENV."""

import os

from config.database import database_role, require_encrypted_connection
from config.environment import app_environment, load_local_env_file
from config.secrets import check_required_settings

load_local_env_file()

_environment = app_environment()
_role = database_role()
check_required_settings(os.environ, _environment, _role)
require_encrypted_connection(os.environ, _environment, _role)

if _environment == "development":
    from .development import *  # noqa: F403
elif _environment == "staging":
    from .staging import *  # noqa: F403
else:
    from .production import *  # noqa: F403
