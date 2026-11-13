"""A project's scoring settings: the platform defaults until the project saves its own."""

from django.db import transaction

from core.errors import form_error
from plans.limits import MAX_TOP_N, check_top_n, limit_for
from platform_settings.service import get_setting

from .deletion import register_project_data
from .models import Project, ProjectScoringSettings
from .recalculation import recalculate_scores
from .service import require_editable

FIELDS = ("must_weight_percent", "nice_weight_percent", "recommendation_threshold", "top_n")


def scoring_defaults():
    """The values a project starts with. The company's own scoring defaults plug in here."""
    return {
        "must_weight_percent": get_setting("scoring.must_have_weight_percent"),
        "nice_weight_percent": get_setting("scoring.nice_to_have_weight_percent"),
        "recommendation_threshold": get_setting("scoring.strong_match_min"),
        "top_n": get_setting("scoring.top_n"),
    }


def top_n_cap(company_id):
    return limit_for(company_id, MAX_TOP_N)


def effective_settings(project):
    """What scoring uses now. A top-N above the plan's cap (the plan was lowered) is held at
    the cap, never above it."""
    saved = ProjectScoringSettings.objects.filter(project=project).first()
    values = {name: getattr(saved, name) for name in FIELDS} if saved else scoring_defaults()
    values["top_n"] = min(values["top_n"], top_n_cap(project.company_id))
    return values


def describe(project):
    return {**effective_settings(project), "top_n_cap": top_n_cap(project.company_id)}


def _refuse_impossible(values):
    problems = {}
    for name in ("must_weight_percent", "nice_weight_percent"):
        if not 0 <= values[name] <= 100:
            problems[name] = "A weight is a percent from 0 to 100."
    if not problems and values["must_weight_percent"] + values["nice_weight_percent"] != 100:
        problems["nice_weight_percent"] = "The two weights must add up to 100."
    if not 0 <= values["recommendation_threshold"] <= 100:
        problems["recommendation_threshold"] = "The threshold is a percent from 0 to 100."
    if values["top_n"] < 1:
        problems["top_n"] = "The top list must have at least 1 candidate."
    if problems:
        raise form_error(problems)


def save_scoring_settings(project_id, company_id, values):
    """Saves the settings and recalculates scores without the AI. Returns what is now in
    force and how many scores changed."""
    _refuse_impossible(values)
    check_top_n(company_id, values["top_n"]).raise_if_blocked()
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id, company_id=company_id)
        require_editable(project)
        before = effective_settings(project)
        ProjectScoringSettings.objects.update_or_create(
            project=project, defaults={"company_id": company_id, **values}
        )
        changed = before != effective_settings(project)
        recalculated = recalculate_scores(project) if changed else 0
    return {**describe(project), "recalculated": recalculated}


def _remove_for_project(company_id, project_id):
    ProjectScoringSettings.objects.filter(company_id=company_id, project_id=project_id).delete()


register_project_data("ProjectScoringSettings", _remove_for_project)
