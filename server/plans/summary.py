"""The plan and usage figures a company sees. Every number comes from the same functions the
limit checks use, so what is shown always matches what is enforced."""

from freeaccess import entitlement
from platform_settings.service import get_setting
from projects.service import active_project_count
from usage import service as usage

from . import limits, trials
from .plan_change import pending_of
from .subscriptions import State, access_of, get_subscription, grace_ends_at


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
    access = access_of(company_id)
    state = access.state
    current = usage.current_usage(company_id)
    cv_limit = limits.limit_for(company_id, limits.CVS_PER_MONTH)
    cvs_used = current["cvs_scored"] + usage.waiting_cvs(company_id)
    if trials.on_trial(subscription):  # the stricter of the monthly and the whole-trial limit
        trial_used = trials.cvs_used(subscription)
        if subscription.trial_cv_limit - trial_used < cv_limit - cvs_used:
            cv_limit, cvs_used = subscription.trial_cv_limit, trial_used
    project_limit = limits.limit_for(company_id, limits.MAX_PROJECTS)
    return {
        "plan_name": access.plan.name if access.plan else None,
        "free_access": entitlement.describe(access.grant),
        "plan_id": subscription.plan_id,
        "can_manage_billing": bool(subscription.stripe_customer_id),
        "pending_change": pending_of(subscription),
        "state": state,
        "trial": trials.describe_trial(subscription),
        "renewal": subscription.renewal,
        "grace_ends_at": grace_ends_at(subscription) if state == State.PAST_DUE else None,
        "period_start": current["period_start"],
        "period_end": current["period_end"],
        # Scored plus waiting, exactly what the monthly limit check counts.
        "cvs": _measure(cvs_used, cv_limit),
        "estimated_cost": f"{current['estimated_cost']:.6f}",
        "projects": {"used": projects_in_use(company_id), "limit": project_limit},
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
    }
