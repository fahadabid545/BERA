"""Writing, reading and clearing a company's activity log."""

from datetime import UTC, datetime, time, timedelta

from django.utils import timezone

from companies.models import Company
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


def retention_days(company_id):
    """How long the company's entries are kept: its own choice while that is still one of the
    platform's choices, otherwise the platform default."""
    chosen = Company.objects.filter(pk=company_id).values_list("retention_days", flat=True).first()
    if chosen in get_setting("retention.choices_days"):
        return chosen
    return get_setting("retention.default_days")


def retention_cutoff(company_id):
    """Entries older than this are no longer listed or kept."""
    return timezone.now() - timedelta(days=retention_days(company_id))


def list_entries(company_id, before=None, *, actor_id=None, since=None, until=None):
    """The company's newest entries within the retention period, optionally of one person and
    between two days (UTC, both inclusive): a page, and where the next page starts (the time of
    the last entry shown) or None."""
    entries = ActivityEntry.objects.filter(
        company_id=company_id, created_at__gte=retention_cutoff(company_id)
    )
    if actor_id is not None:
        entries = entries.filter(actor_id=actor_id)
    if since is not None:
        entries = entries.filter(created_at__gte=_day_start(since))
    if until is not None:
        entries = entries.filter(created_at__lt=_day_start(until + timedelta(days=1)))
    if before is not None:
        entries = entries.filter(created_at__lt=before)
    size = get_setting("activity.page_size")
    page = list(entries.order_by("-created_at", "-id")[: size + 1])
    next_before = page[size - 1].created_at if len(page) > size else None
    return page[:size], next_before


def _day_start(day):
    return datetime.combine(day, time.min, tzinfo=UTC)


def people_in_log(company_id):
    """Who has entries within the retention period, for the person filter: the name each had
    most recently, sorted by name."""
    latest = (
        ActivityEntry.objects.filter(
            company_id=company_id,
            created_at__gte=retention_cutoff(company_id),
            actor_id__isnull=False,
        )
        .order_by("actor_id", "-created_at")
        .distinct("actor_id")
        .values("actor_id", "actor_name")
    )
    return sorted(
        ({"id": row["actor_id"], "name": row["actor_name"]} for row in latest),
        key=lambda person: person["name"].lower(),
    )


@logged_job
def purge_expired_entries():
    """Deletes each company's entries past its own retention period; for a periodic job."""
    deleted = 0
    for company_id in ActivityEntry.objects.values_list("company_id", flat=True).distinct():
        removed, _ = ActivityEntry.objects.filter(
            company_id=company_id, created_at__lt=retention_cutoff(company_id)
        ).delete()
        deleted += removed
    return deleted
