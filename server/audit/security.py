"""Security events: written to the audit log and announced to the super admins."""

from core import rate_limits
from platform_settings.service import get_setting

from .alerts import alert_admins
from .service import record

SECONDS_PER_MINUTE = 60


def record_security_event(kind, **details_of_the_entry):
    """Same as `audit.service.record`, then emails the super admins (at most once per kind per
    hour). Use it for every kind that starts with "security."."""
    entry = record(kind, **details_of_the_entry)
    alert_admins(kind)
    return entry


def watch_cv_downloads(person, count=1):
    """Called for the CVs a user downloads (`count` of them at once). The first download beyond
    the limit in the hour is an event of its own; the user is not stopped here (the download
    limits do that)."""
    window = get_setting("security.download_alert_window_minutes") * SECONDS_PER_MINUTE
    limit = get_setting("security.download_alert_threshold")
    total = rate_limits.count_in_window(
        "cv-downloads", f"{person.__class__.__name__}:{person.pk}", window, cost=count
    )
    if total - count <= limit < total:  # once per window, not for every download after it
        record_security_event(
            "security.download_volume",
            actor=person,
            details={"downloads": total, "limit": limit},
        )
