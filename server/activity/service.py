"""Writing, reading and clearing a company's activity log."""

from datetime import timedelta

from django.utils import timezone

from core.jobs import logged_job
from platform_settings.service import get_setting

from .events import KINDS
from .models import ActivityEntry

MAX_DETAIL_LENGTH = 200
FORBIDDEN_NAME_PARTS = ("password", "token", "secret", "code", "cv", "text", "hash", "key")


def _checked_details(details):
    for name, value in details.items():
        if any(part in name.lower() for part in FORBIDDEN_NAME_PARTS):
            raise ValueError(f"The activity log must not hold a detail called {name!r}.")
        if (
            not isinstance(value, (str, int, bool, type(None)))
            or len(str(value)) > MAX_DETAIL_LENGTH
        ):
            raise ValueError(f"The activity detail {name!r} must be a short value.")
    return details


def record(kind, *, company_id, actor, target_kind="", target_id="", details=None):
    """Adds an entry for the company. `actor` is the company user who did it."""
    if kind not in KINDS:
        raise KeyError(kind)  # a mistake in the code, so it fails loudly
    return ActivityEntry.objects.create(
        company_id=company_id,
        kind=kind,
        actor_id=actor.pk,
        actor_name=actor.name,
        target_kind=target_kind,
        target_id=str(target_id),
        details=_checked_details(details or {}),
    )


def retention_cutoff():
    """Entries older than this are no longer listed or kept. Every company follows the
    platform default until companies can choose their own."""
    return timezone.now() - timedelta(days=get_setting("retention.default_days"))


def list_entries(company_id, before=None):
    """The company's newest entries within the retention period: a page, and where the next
    page starts (the time of the last entry shown) or None."""
    entries = ActivityEntry.objects.filter(
        company_id=company_id, created_at__gte=retention_cutoff()
    )
    if before is not None:
        entries = entries.filter(created_at__lt=before)
    size = get_setting("activity.page_size")
    page = list(entries.order_by("-created_at", "-id")[: size + 1])
    next_before = page[size - 1].created_at if len(page) > size else None
    return page[:size], next_before


@logged_job
def purge_expired_entries():
    """Deletes entries past the retention period; for a periodic job."""
    deleted, _ = ActivityEntry.objects.filter(created_at__lt=retention_cutoff()).delete()
    return deleted
