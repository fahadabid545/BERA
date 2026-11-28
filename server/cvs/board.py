"""The candidates board of a project: one column for each stage, best score first.

A card is a candidate with its key (the project's candidate number behind a prefix), masked name,
latest role and score. Each column loads at most `candidates.board_column_size` cards and says
how many candidates it holds in all. The list's filters apply; unlike the list, rejected
candidates have their own column instead of being hidden. CVs that are not yet candidates (still
being read, or failed) are not cards.
"""

from django.db.models import Count, F

from core.personal_data import mask_name
from platform_settings.service import get_setting

from .filters import apply_filters, checked_filters, requirement_choices
from .models import Candidate, CvFile
from .profile_checks import PRESENT, month_number
from .ranking import annotated, ordering

STAGES = [stage for stage, _ in Candidate.Stage.choices]


def latest_role(profile_content):
    """The title of the job the CV shows as current or, failing that, the one that ended last;
    empty when the CV lists no job."""
    jobs = (profile_content or {}).get("jobs") or []
    if not jobs:
        return ""

    def ended(job):
        if job.get("end") == PRESENT:
            return float("inf")
        known = job.get("end") or job.get("start")
        return month_number(known, end=True) if known else float("-inf")

    return max(jobs, key=ended)["title"]


def _card(item):
    return {
        "id": str(item.candidate_pk),
        "key": f"{get_setting('candidates.key_prefix')}-{item.number_value}",
        "file_name": item.original_name,
        "name": mask_name(item.contact_name) if item.contact_name else "",
        "role": latest_role(item.profile_content),
        "score": f"{item.score_value:.1f}" if item.score_value is not None else None,
        "grade": item.grade_value,
    }


def board(project, params):
    filters = checked_filters(params, project)
    rows = apply_filters(
        annotated(CvFile.objects.filter(company_id=project.company_id, project=project)).annotate(
            number_value=F("candidate__number"), profile_content=F("profile__content")
        ),
        filters,
    ).filter(candidate__isnull=False)
    counts = dict(rows.order_by().values_list("stage_value").annotate(total=Count("pk")).order_by())
    size = get_setting("candidates.board_column_size")
    order = ordering("score", "desc")
    return {
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "filtered": bool(filters),
        "requirements": requirement_choices(project),
        "columns": [
            {
                "stage": stage,
                "count": counts.get(stage, 0),
                "cards": [
                    _card(item) for item in rows.filter(stage_value=stage).order_by(*order)[:size]
                ],
            }
            for stage in STAGES
        ],
    }
