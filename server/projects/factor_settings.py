"""A project's extra scoring factors: which are switched on, how much each counts (0 to 100%),
and what the job expects of experience, education and seniority. With no saved row every factor
is off. The factors themselves are worked out in `cvs/extra_factors.py`."""

from django.db import transaction

from core.errors import form_error
from platform_settings.service import get_setting

from .deletion import register_project_data
from .models import Project, ProjectFactorSettings
from .recalculation import recalculate_scores
from .service import require_editable

FACTORS = (
    "experience_years",
    "education",
    "seniority",
    "recency",
    "gaps_and_changes",
    "readability",
    "confidence",
)
EDUCATION_LEVELS = ("bachelor", "master", "doctorate")
SENIORITY_LEVELS = ("junior", "mid", "senior", "lead")
JOB_FIELDS = ("required_years", "required_education", "seniority")


def _default_factors():
    return {
        name: {"enabled": False, "weight": get_setting("factors.default_weight")}
        for name in FACTORS
    }


def effective_factors(project):
    """The settings in force: the project's own, or everything off."""
    saved = ProjectFactorSettings.objects.filter(project=project).first()
    if saved is None:
        return {
            "required_years": None,
            "required_education": None,
            "seniority": None,
            "factors": _default_factors(),
        }
    return {
        "required_years": saved.required_years,
        "required_education": saved.required_education,
        "seniority": saved.seniority,
        "factors": {**_default_factors(), **saved.factors},
    }


def describe(project):
    return {
        **effective_factors(project),
        "max_required_years": get_setting("factors.max_required_years"),
    }


def _refuse_impossible(values):
    problems = {}
    years = values["required_years"]
    if years is not None and not 0 <= years <= get_setting("factors.max_required_years"):
        problems["required_years"] = (
            f"Years of experience must be from 0 to {get_setting('factors.max_required_years')}."
        )
    if values["required_education"] not in (None, *EDUCATION_LEVELS):
        problems["required_education"] = "Choose one of the listed education levels."
    if values["seniority"] not in (None, *SENIORITY_LEVELS):
        problems["seniority"] = "Choose one of the listed seniority levels."
    if set(values["factors"]) != set(FACTORS):
        problems["factors"] = "Every factor must be given once."
    else:
        for name, setting in values["factors"].items():
            if not 0 <= setting["weight"] <= 100:
                problems[f"factors.{name}"] = "A weight is a percent from 0 to 100."
    if problems:
        raise form_error(problems)


def save_factor_settings(project_id, company_id, values):
    """Saves the settings, brings the stored factor values in line with the job's expectations and
    recombines scores without the AI. Returns what is in force and how many scores changed."""
    from cvs.extra_factors import refresh_project_factors  # cvs builds on projects

    _refuse_impossible(values)
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id, company_id=company_id)
        require_editable(project)
        before = effective_factors(project)
        ProjectFactorSettings.objects.update_or_create(
            project=project, defaults={"company_id": company_id, **values}
        )
        after = effective_factors(project)
        if any(before[name] != after[name] for name in JOB_FIELDS):
            refresh_project_factors(project)
        recalculated = recalculate_scores(project) if before != after else 0
    return {**describe(project), "recalculated": recalculated}


def _remove_for_project(company_id, project_id):
    ProjectFactorSettings.objects.filter(company_id=company_id, project_id=project_id).delete()


register_project_data("ProjectFactorSettings", _remove_for_project)
