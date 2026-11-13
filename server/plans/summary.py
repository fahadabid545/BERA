"""The plan and usage figures a company sees. Every number comes from the same functions the
limit checks use, so what is shown always matches what is enforced."""

from platform_settings.service import get_setting
from projects.service import active_project_count
from usage import service as usage

from . import limits
from .subscriptions import State, effective_state, get_subscription, grace_ends_at


def projects_in_use(company_id):
    """How many projects count toward the limit: archived ones do not."""
    return active_project_count(company_id)


def warning_level(used, limit):
    """The highest warning percent reached (80 or 100 by default), or None. A company with no
    allowance has nothing to measure against."""
    if not limit:
        return None
    reached = [p for p in get_setting("usage.warning_percents") if used * 100 >= p * limit]
    return max(reached) if reached else None


def _measure(used, limit):
    return {
        "used": used,
        "limit": limit,
        "left": max(limit - used, 0),
        "warning": warning_level(used, limit),
    }


def plan_and_usage(company_id):
    subscription = get_subscription(company_id)
    state = effective_state(subscription)
    current = usage.current_usage(company_id)
    cv_limit = limits.limit_for(company_id, limits.CVS_PER_MONTH)
    token_limit = limits.limit_for(company_id, limits.MONTHLY_AI_TOKEN_CAP)
    project_limit = limits.limit_for(company_id, limits.MAX_PROJECTS)
    return {
        "plan_name": subscription.plan.name if subscription.plan else None,
        "state": state,
        "renewal": subscription.renewal,
        "grace_ends_at": grace_ends_at(subscription) if state == State.PAST_DUE else None,
        "period_start": current["period_start"],
        "period_end": current["period_end"],
        # Scored plus waiting, exactly what the monthly limit check counts.
        "cvs": _measure(current["cvs_scored"] + usage.waiting_cvs(company_id), cv_limit),
        "tokens": _measure(current["tokens_in"] + current["tokens_out"], token_limit),
        "estimated_cost": f"{current['estimated_cost']:.6f}",
        "projects": {"used": projects_in_use(company_id), "limit": project_limit},
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
    }
