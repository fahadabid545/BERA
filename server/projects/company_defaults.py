"""The company's scoring defaults: what its new projects start with. The owner sets them; they are
copied into a project when it is created (`service.py`), so changing them never touches a
project that already exists."""

from django.db import transaction

from activity.service import record
from plans.limits import check_top_n

from .factor_settings import default_factors
from .factor_settings import refuse_impossible as refuse_impossible_factors
from .models import CompanyScoringDefaults
from .scoring_settings import FIELDS, held_at_cap, scoring_defaults, top_n_cap
from .scoring_settings import refuse_impossible as refuse_impossible_scoring


def effective_defaults(company_id):
    """The company's saved defaults, or the platform's where it has saved none. A top-N above
    the plan's cap (the plan was lowered) is held at the cap, as it is for a project."""
    saved = CompanyScoringDefaults.objects.filter(company_id=company_id).first()
    if saved is None:
        values = {**scoring_defaults(), "factors": default_factors()}
    else:
        values = {name: getattr(saved, name) for name in FIELDS}
        values["factors"] = {**default_factors(), **saved.factors}
    values["top_n"] = held_at_cap(values["top_n"], top_n_cap(company_id))
    return values


def describe(company_id):
    return {**effective_defaults(company_id), "top_n_cap": top_n_cap(company_id)}


def save_defaults(owner, company_id, values):
    """Checks and saves the owner's defaults; returns what is now in force."""
    refuse_impossible_scoring(values)
    refuse_impossible_factors(
        {
            "required_years": None,
            "required_education": None,
            "seniority": None,
            "factors": values["factors"],
        }
    )
    check_top_n(company_id, values["top_n"]).raise_if_blocked()
    with transaction.atomic():
        CompanyScoringDefaults.objects.update_or_create(company_id=company_id, defaults=values)
        record(
            "setting_changed",
            company_id=company_id,
            actor=owner,
            details={"setting": "scoring_defaults"},
        )
    return describe(company_id)
