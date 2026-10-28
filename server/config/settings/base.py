from pathlib import Path

import dj_database_url

from config.environment import require_settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent

_required = require_settings(["DJANGO_SECRET_KEY", "DATABASE_URL"])
SECRET_KEY = _required["DJANGO_SECRET_KEY"]
DATABASES = {"default": dj_database_url.parse(_required["DATABASE_URL"], conn_max_age=60)}

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "django_q",
    "core",
    "companies",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "core.exception_handler.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# Background jobs run in a separate worker process, queued in PostgreSQL.
Q_CLUSTER = {
    "name": "bera",
    "orm": "default",
    "workers": 2,
    "timeout": 60,
    "retry": 120,
    "queue_limit": 50,
}
