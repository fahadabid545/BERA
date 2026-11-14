"""The ranked candidate list of a project, best first.

One row for each CV of the project that has not been cancelled: a scored candidate, or an item
still on its way (waiting, reading, scoring) or failed, which shows its status instead of a score.
Rows are sorted and paged by the database, so the list stays fast with thousands of CVs, and only
the page's rows are read (and their names decrypted).

- The rank is the place in the order AI score high to low, ties by date added then file name; it
  does not change when the list is sorted another way. Only scored candidates have one.
- Whatever the sort, items without a score sit at the bottom.
- Whatever the sort, ties are ordered by date added, then file name, then id, so the order
  never flickers.
- Filters (`filters.py`) narrow the list first; the rank is then among the candidates that pass.
- The CV's name is shown as initials (see `core/personal_data.py`). It is encrypted, so the
  candidate column sorts by the file name.
"""

from django.db.models import Case, F, IntegerField, When, Window
from django.db.models.functions import RowNumber

from core.errors import form_error
from core.personal_data import mask_name
from platform_settings.service import get_setting

from .filters import apply_filters, checked_filters, requirement_choices
from .models import CvFile

SORTS = ("rank", "candidate", "score", "ats", "label", "stage", "added")
DEFAULT_SORT, DEFAULT_DIRECTION = "score", "desc"
ASC, DESC = "asc", "desc"
LABEL_ORDER = Case(
    When(candidate__score__label="strong_match", then=0),
    When(candidate__score__label="possible", then=1),
    When(candidate__score__label="not_recommended", then=2),
    default=3,
    output_field=IntegerField(),
)
# The column a sort key orders by (rank is handled on its own).
COLUMNS = {
    "candidate": "original_name",
    "score": "score_value",
    "ats": "ats_value",
    "label": "label_order",
    "stage": "stage_value",
    "added": "created_at",
}
NEUTRAL = ("created_at", "original_name", "id")  # the tie-breakers, always in this order


def _base(project):
    """The project's CVs with every value the list shows, read through joins, so one query
    serves a page."""
    return (
        CvFile.objects.filter(company_id=project.company_id, project=project)
        .exclude(status=CvFile.Status.CANCELLED)
        .annotate(
            candidate_pk=F("candidate__pk"),
            contact_name=F("contact__name"),
            score_value=F("candidate__score__score"),
            grade_value=F("candidate__score__grade"),
            outdated_value=F("candidate__score__outdated"),
            label_value=F("candidate__score__label"),
            borderline_value=F("candidate__score__borderline"),
            ats_value=F("candidate__ats_score__score"),
            stage_value=F("candidate__stage"),
            label_order=LABEL_ORDER,
            has_score=Case(
                When(candidate__score__isnull=False, then=0), default=1, output_field=IntegerField()
            ),
            ranking=Window(
                RowNumber(),
                order_by=[F("score_value").desc(nulls_last=True), *NEUTRAL],
            ),
        )
    )


def _ordering(sort, direction):
    """Unscored items last, then the chosen column, then the fixed tie-breakers."""
    if sort == "rank":
        chosen = F("ranking").asc() if direction == ASC else F("ranking").desc()
    else:
        column = F(COLUMNS[sort])
        chosen = column.asc(nulls_last=True) if direction == ASC else column.desc(nulls_last=True)
    return ["has_score", chosen, *NEUTRAL]


def checked_query(params):
    """(sort, direction, page) from the request's query, or a form error saying what is wrong."""
    sort = params.get("sort") or DEFAULT_SORT
    default_direction = DESC if sort in ("score", "ats", "added") else ASC
    direction = params.get("direction") or default_direction
    problems = {}
    if sort not in SORTS:
        problems["sort"] = "Choose one of the columns to sort by."
    if direction not in (ASC, DESC):
        problems["direction"] = "The direction is ascending or descending."
    try:
        page = int(params.get("page") or 1)
        if page < 1:
            raise ValueError
    except ValueError:
        problems["page"] = "The page is a number from 1."
        page = 1
    if problems:
        raise form_error(problems)
    return sort, direction, page


def _row(item):
    scored = item.score_value is not None
    return {
        "id": str(item.pk),
        "candidate_id": str(item.candidate_pk) if item.candidate_pk else None,
        "file_name": item.original_name,
        "name": mask_name(item.contact_name) if item.contact_name else "",
        "status": item.status,
        "reason": item.failure_reason,
        "rank": item.ranking if scored else None,
        "score": f"{item.score_value:.1f}" if scored else None,
        "grade": item.grade_value,
        "outdated": bool(item.outdated_value),
        "ats_score": item.ats_value,
        "label": item.label_value,
        "borderline": bool(item.borderline_value),
        "stage": item.stage_value,
        "added_at": item.created_at.isoformat(),
    }


def ranked_list(project, params):
    """One page of the project's ranked candidates, with the totals the page needs."""
    sort, direction, page = checked_query(params)
    size = get_setting("candidates.page_size")
    filters = checked_filters(params, project)
    rows = apply_filters(_base(project), filters)
    total = rows.count()
    pages = max(1, -(-total // size))
    page = min(page, pages)
    window = rows.order_by(*_ordering(sort, direction))[(page - 1) * size : page * size]
    return {
        "sort": sort,
        "direction": direction,
        "page": page,
        "pages": pages,
        "page_size": size,
        "count": total,
        "filtered": bool(filters),
        "requirements": requirement_choices(project),
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "rows": [_row(item) for item in window],
    }
