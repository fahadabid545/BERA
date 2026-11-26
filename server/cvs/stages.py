"""Moving candidates through hiring: New, Shortlisted, Interviewed, On hold, Selected, Rejected.

One change or many at once, all or nothing. Every change that really moves a candidate is stored
with who and when (`StageChange`) and shown as the candidate's history; a candidate already at
the stage is left alone and has no new entry. Rejected candidates are hidden from the default
list (see `ranking.py`) and found again through the stage filter.
"""

from uuid import UUID

from django.db import transaction
from django.http import Http404

from core.errors import form_error
from platform_settings.service import get_setting

from .models import Candidate, StageChange


def _checked_ids(raw):
    if not isinstance(raw, list) or not raw:
        raise form_error({"candidate_ids": "Choose at least one candidate."})
    if len(raw) > get_setting("candidates.bulk_max"):
        raise form_error({"candidate_ids": "Too many candidates at once. Choose fewer."})
    try:
        return list(dict.fromkeys(UUID(str(item)) for item in raw))
    except ValueError:
        raise Http404 from None


def change_stage(project, user_id, raw_ids, stage):
    """Moves the project's candidates to `stage`. A candidate that is not in this project (or
    company) makes the whole request "not found" and changes nothing. Returns how many moved."""
    if stage not in Candidate.Stage.values:
        raise form_error({"stage": "Choose one of the stages."})
    ids = _checked_ids(raw_ids)
    with transaction.atomic():
        found = list(
            Candidate.objects.select_for_update().filter(
                company_id=project.company_id, project=project, pk__in=ids
            )
        )
        if len(found) != len(ids):
            raise Http404
        moving = [candidate for candidate in found if candidate.stage != stage]
        StageChange.objects.bulk_create(
            StageChange(
                company_id=project.company_id,
                candidate=candidate,
                from_stage=candidate.stage,
                to_stage=stage,
                changed_by_id=user_id,
            )
            for candidate in moving
        )
        Candidate.objects.filter(pk__in=[candidate.pk for candidate in moving]).update(stage=stage)
    return {"changed": len(moving), "unchanged": len(found) - len(moving)}


def history(candidate):
    """The candidate's stage changes, newest first, with the person's name."""
    changes = StageChange.objects.filter(candidate=candidate).select_related("changed_by")
    return [
        {
            "from_stage": change.from_stage,
            "to_stage": change.to_stage,
            "by": change.changed_by.name,
            "at": change.created_at.isoformat(),
        }
        for change in changes.order_by("-created_at", "-pk")
    ]
