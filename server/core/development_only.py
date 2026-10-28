from django.conf import settings

from .errors import AppError


def require_development():
    """Guard for commands that create fake data or wipe the database."""
    if settings.APP_ENV != "development":
        raise AppError(
            "development_only",
            "This command only runs when APP_ENV=development.",
            status_code=403,
        )
