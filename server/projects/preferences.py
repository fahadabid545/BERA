"""How a project's candidates are handled: small per-project choices the owner makes in the
project settings. Each is a plain column on the project; this module is the one place that reads
them for the screen and saves them, with the same log entry for every change."""

from django.db import transaction

from activity import service as activity

from .models import Project
from .service import require_editable

FIELDS = ("hide_contact_by_default", "auto_shortlist", "auto_reject_below", "labels")


def preferences_of(project):
    return {name: getattr(project, name) for name in FIELDS}


def save_preferences(actor, project, values):
    """Saves the fields in `values` (any of FIELDS) and logs each one that really changed."""
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project.pk)
        require_editable(project)
        changed = [name for name, value in values.items() if getattr(project, name) != value]
        for name in changed:
            setattr(project, name, values[name])
        if changed:
            project.save(update_fields=[*changed, "updated_at"])
            for name in changed:
                activity.record(
                    "setting_changed",
                    company_id=project.company_id,
                    actor=actor,
                    target_kind="project",
                    target_id=project.pk,
                    details={"setting": name},
                )
    return project
