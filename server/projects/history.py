"""Who changed what on one project and when, read from the company's activity log so there is a
single record. Only the project's own kinds are listed, newest first, within the log's
retention period."""

from activity import service as activity
from activity.models import ActivityEntry
from platform_settings.service import get_setting

KINDS = ("project_changed", "setting_changed", "project_owner_changed")
CHANGES = frozenset({"title", "job_description", "requirements", "scoring", "factors", "stages"})


def record_change(actor, project, change):
    """Logs one change to the project; `change` is one of CHANGES."""
    if change not in CHANGES:
        raise KeyError(change)  # a mistake in the code, so it fails loudly
    activity.record(
        "project_changed",
        company_id=project.company_id,
        actor=actor,
        target_kind="project",
        target_id=project.pk,
        details={"change": change},
    )


def history_of(project):
    entries = ActivityEntry.objects.filter(
        company_id=project.company_id,
        target_kind="project",
        target_id=str(project.pk),
        kind__in=KINDS,
        created_at__gte=activity.retention_cutoff(project.company_id),
    ).order_by("-created_at", "-id")[: get_setting("activity.page_size")]
    return [
        {
            "id": str(entry.id),
            "kind": entry.kind,
            "actor_name": entry.actor_name,
            "target_kind": entry.target_kind,
            "target_id": entry.target_id,
            "details": entry.details,
            "created_at": entry.created_at,
        }
        for entry in entries
    ]
