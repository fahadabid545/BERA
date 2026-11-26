"""What free access allows, and which of a company's accesses applies.

Three things can give a company access, and they are kept apart: a paid subscription (or a free
trial, which is the same record), a permitted email's free plan and beta access. A paid plan wins
while it is running; otherwise permitted access, then beta. Taking one away never changes another,
because each is its own record.

Beta access has limits of its own, all platform settings (`beta.*`) so an admin can change them:
how many CVs a day, how many people in the company (1: nobody can be invited), and room for many
projects. Its top-list size and monthly AI allowance come from the smallest paid plan, so no new
number is invented for them.
"""

from django.db.models import Q
from django.utils import timezone

from plans.models import Plan
from platform_settings.service import get_setting
from usage import service as usage

from .models import FreeAccess

# limit name (see plans/limits.py) -> the platform setting that gives it to beta access
BETA_SETTINGS = {
    "cvs_per_month": "beta.cvs_per_month",
    "cvs_per_project": "beta.cvs_per_project",
    "max_projects": "beta.max_projects",
    "max_team_accounts": "beta.max_team_accounts",
}
FROM_SMALLEST_PLAN = ("max_top_n", "monthly_ai_token_cap")


def active_grants(company_id, now=None):
    now = now or timezone.now()
    return FreeAccess.objects.filter(company_id=company_id, revoked_at__isnull=True).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)
    )


def active_grant(company_id, now=None):
    """The access that applies when no paid plan does: permitted first, then beta."""
    grants = list(active_grants(company_id, now).select_related("plan"))
    for kind in (FreeAccess.Kind.PERMITTED, FreeAccess.Kind.BETA):
        for grant in grants:
            if grant.kind == kind:
                return grant
    return None


def smallest_paid_plan():
    return (
        Plan.objects.filter(status=Plan.Status.ACTIVE, price_usd__gt=0)
        .order_by("price_usd", "id")
        .first()
    )


def beta_limit(name):
    if name in BETA_SETTINGS:
        return get_setting(BETA_SETTINGS[name])
    plan = smallest_paid_plan()
    return getattr(plan, name) if plan is not None else 0


def start_of_today():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


def describe(grant):
    """What the company's own screens show about its free access, or None for a paid company."""
    if grant is None:
        return None
    shown = {
        "kind": grant.kind,
        "ends_at": grant.ends_at.isoformat() if grant.ends_at else None,
    }
    if grant.kind == "beta":
        shown["cvs_today"] = {
            "used": usage.cvs_since(grant.company_id, start_of_today()),
            "limit": get_setting("beta.cvs_per_day"),
        }
    return shown
