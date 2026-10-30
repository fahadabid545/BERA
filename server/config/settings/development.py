from .base import *  # noqa: F403

APP_ENV = "development"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
# The web app on its development port.
ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
