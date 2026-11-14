"""The filters of the ranked candidate list (see `ranking.py`).

Every filter is a query value, so a link shows the same result; filters combine (a candidate must
pass all of them), and a list value takes several choices separated by commas (any one of them).
No value means no filter. The ranking is then made among the candidates that pass.

- score_min, score_max: the AI score; ats_min, ats_max: the ATS score; years_min, years_max:
  the years of experience in the profile. A CV without that value (still on its way, or no jobs
  with dates) never passes a filter on it.
- grade, label, stage: several choices each.
- missing: requirement ids; a must-have the candidate is judged as missing (each one listed).
- has: requirement ids; a requirement the candidate is judged as meeting (each one listed).
- added_from, added_to: dates (YYYY-MM-DD), both days included.
- duplicate: "true" for CVs flagged as likely the same person as another.
- q: text found in the file name or the profile's summary, whatever the letter case.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.db.models import Exists, FloatField, OuterRef, Q
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast

from core.errors import form_error
from platform_settings.service import get_setting
from projects.models import Requirement

from .models import Candidate, CvFile, RequirementResult
from .recommendation import LABELS
from .scoring import GRADE_LIMITS, LOWEST_GRADE

NUMBERS = {
    "score": Decimal,
    "ats": int,
    "years": float,
}
LIST_VALUES = {
    "grade": [grade for grade, _ in GRADE_LIMITS] + [LOWEST_GRADE],
    "label": list(LABELS),
    "stage": [stage for stage, _ in Candidate.Stage.choices],
}
FRIENDLY = {
    "score": "the AI score",
    "ats": "the ATS score",
    "years": "the years of experience",
}


def _pieces(value):
    return [piece.strip() for piece in value.split(",") if piece.strip()]


def _number(name, end, raw, problems):
    try:
        number = NUMBERS[name](raw)
        if not Decimal(str(number)).is_finite():
            raise ValueError
    except (ValueError, InvalidOperation):
        problems[f"{name}_{end}"] = f"Enter a number for {FRIENDLY[name]}."
        return None
    if number < 0:
        problems[f"{name}_{end}"] = f"{FRIENDLY[name].capitalize()} cannot be below 0."
        return None
    return number


def _requirement_ids(name, raw, project, problems):
    """Ids of this project's requirements (only must-haves for `missing`)."""
    allowed = Requirement.objects.filter(company_id=project.company_id, project=project)
    if name == "missing":
        allowed = allowed.filter(kind=Requirement.Kind.MUST)
    known = {str(pk) for pk in allowed.values_list("pk", flat=True)}
    ids = []
    for piece in _pieces(raw):
        try:
            piece = str(UUID(piece))
        except ValueError:
            piece = ""
        if piece not in known:
            problems[name] = (
                "Choose one of the project's must-haves."
                if name == "missing"
                else "Choose one of the project's requirements."
            )
            return []
        ids.append(piece)
    return ids


def checked_filters(params, project):
    """The filters in the request's query, with each value checked, or a form error that names
    every filter with a wrong value."""
    problems, filters = {}, {}
    for name in NUMBERS:
        for end in ("min", "max"):
            raw = params.get(f"{name}_{end}")
            if raw not in (None, ""):
                number = _number(name, end, raw, problems)
                if number is not None:
                    filters[f"{name}_{end}"] = number
        low, high = filters.get(f"{name}_min"), filters.get(f"{name}_max")
        if low is not None and high is not None and low > high:
            problems[f"{name}_min"] = f"The lowest {name} is above the highest."
    for name, allowed in LIST_VALUES.items():
        chosen = _pieces(params.get(name) or "")
        if any(value not in allowed for value in chosen):
            problems[name] = "Choose from the values on the list."
        elif chosen:
            filters[name] = chosen
    for name in ("missing", "has"):
        ids = _requirement_ids(name, params.get(name) or "", project, problems)
        if ids:
            filters[name] = ids
    for name in ("added_from", "added_to"):
        raw = params.get(name)
        if raw:
            try:
                filters[name] = date.fromisoformat(raw)
            except ValueError:
                problems[name] = "Enter the date as year-month-day."
    if "added_from" in filters and "added_to" in filters:
        if filters["added_from"] > filters["added_to"]:
            problems["added_from"] = "The first date is after the last date."
    if params.get("duplicate") not in (None, "", "true"):
        problems["duplicate"] = "Duplicates is true or left out."
    elif params.get("duplicate") == "true":
        filters["duplicate"] = True
    search = (params.get("q") or "").strip()
    if len(search) > get_setting("candidates.search_max_length"):
        problems["q"] = "The search is too long."
    elif search:
        filters["q"] = search
    if problems:
        raise form_error(problems)
    return filters


def _range(rows, column, filters, name):
    if f"{name}_min" in filters:
        rows = rows.filter(**{f"{column}__gte": filters[f"{name}_min"]})
    if f"{name}_max" in filters:
        rows = rows.filter(**{f"{column}__lte": filters[f"{name}_max"]})
    return rows


def _judged(rows, requirement_id, verdict):
    judged = RequirementResult.objects.filter(
        candidate=OuterRef("candidate"), requirement_id=requirement_id, verdict=verdict
    )
    return rows.filter(Exists(judged))


def apply_filters(rows, filters):
    """`rows` (the list's base query) narrowed to the candidates that pass every filter."""
    rows = rows.annotate(
        years_value=Cast(
            KeyTextTransform("years_of_experience", "candidate__profile__content"), FloatField()
        )
    )
    rows = _range(rows, "score_value", filters, "score")
    rows = _range(rows, "ats_value", filters, "ats")
    rows = _range(rows, "years_value", filters, "years")
    for name, column in (
        ("grade", "grade_value"),
        ("label", "label_value"),
        ("stage", "stage_value"),
    ):
        if name in filters:
            rows = rows.filter(**{f"{column}__in": filters[name]})
    for requirement_id in filters.get("missing", []):
        rows = _judged(rows, requirement_id, RequirementResult.Verdict.MISSING)
    for requirement_id in filters.get("has", []):
        rows = _judged(rows, requirement_id, RequirementResult.Verdict.MET)
    if "added_from" in filters:
        rows = rows.filter(created_at__date__gte=filters["added_from"])
    if "added_to" in filters:
        rows = rows.filter(created_at__date__lte=filters["added_to"])
    if filters.get("duplicate"):
        rows = rows.filter(review=CvFile.Review.FLAGGED)
    if "q" in filters:
        rows = rows.filter(
            Q(original_name__icontains=filters["q"])
            | Q(candidate__profile__content__summary__icontains=filters["q"])
        )
    return rows


def requirement_choices(project):
    """The project's requirements, for the pickers of `missing` and `has`."""
    return [
        {"id": str(item.pk), "text": item.text, "kind": item.kind}
        for item in Requirement.objects.filter(company_id=project.company_id, project=project)
    ]
