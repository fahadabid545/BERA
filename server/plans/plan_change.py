"""A company moves to another plan. An upgrade is charged now (the difference for the rest of
the period) and the plan changes only when the provider's paid-invoice notice arrives, so until
then the change is "processing" and a failed card leaves everything as it was. A downgrade
changes the provider's price now with nothing charged or credited, and our plan at the renewal,
because that renewal is the first invoice at the lower price.

Usage counters are never touched: the period stays as it is, so what was used carries over.
Nothing is ever deleted when a plan gets smaller (see `warn_over_limits`)."""

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from audit.service import record
from companies.models import Company
from core.errors import AppError
from emailing.links import build_link
from emailing.service import send_email
from platform_settings.service import get_setting
from projects.service import active_project_count
from usage import service as usage

from . import limits, stripe_client
from .checkout import MINOR_UNITS, _buyable_plan
from .models import LimitOverride, Subscription
from .pricing import charge_price
from .subscriptions import NO_PENDING_CHANGE, State, effective_state, get_subscription, owner_of

Change = Subscription.Change
UPGRADE_PROCESSING, UPGRADE_ACTION, DOWNGRADE_SCHEDULED = (
    "processing",
    "action_required",
    "downgrade_scheduled",
)
DECLINED_MESSAGE = (
    "Your card could not be charged, so your plan has not changed. Check your card and try again."
)


def _refuse(code, message, details=None):
    return AppError(code, message, status_code=409, details=details)


def _lock(company_id):
    Company.objects.select_for_update().get(pk=company_id)  # one billing change at a time


def _limit_under(company_id, plan, name):
    """The limit the company would have on `plan`: its own override still wins."""
    override = LimitOverride.objects.filter(company_id=company_id, name=name).first()
    return override.value if override else getattr(plan, name)


def _in_use(company_id):
    from companies.invites import seats_in_use  # it reads the limits this module also reads

    current = usage.current_usage(company_id)
    return {
        limits.CVS_PER_MONTH: current["cvs_scored"] + usage.waiting_cvs(company_id),
        limits.MAX_PROJECTS: active_project_count(company_id),
        limits.MAX_TEAM_ACCOUNTS: seats_in_use(Company.objects.get(pk=company_id)),
    }


LABELS = {
    limits.CVS_PER_MONTH: "CVs this month",
    limits.MAX_PROJECTS: "Projects",
    limits.MAX_TEAM_ACCOUNTS: "Team accounts and open invitations",
}


def over_limits(company_id, plan):
    """What the company already uses beyond what `plan` allows, with exact numbers."""
    over = []
    for name, used in _in_use(company_id).items():
        limit = _limit_under(company_id, plan, name)
        if used > limit:
            over.append(
                {
                    "name": name,
                    "label": LABELS[name],
                    "used": used,
                    "limit": limit,
                    "over": used - limit,
                }
            )
    return over


def _over_text(over):
    return "; ".join(
        f"{item['label']}: {item['used']} in use, the plan allows {item['limit']} "
        f"({item['over']} over)"
        for item in over
    )


def _is_processing(subscription, now):
    window = timedelta(minutes=get_setting("billing.upgrade_processing_minutes"))
    return (
        subscription.pending_change == Change.UPGRADE
        and subscription.pending_since is not None
        and subscription.pending_since > now - window
    )


def _store_pending(subscription, plan, change, now):
    subscription.pending_plan, subscription.pending_change = plan, change
    subscription.pending_since = now
    subscription.save(
        update_fields=["pending_plan", "pending_change", "pending_since", "updated_at"]
    )


def _forget_pending(subscription):
    for name, value in NO_PENDING_CHANGE.items():
        setattr(subscription, name, value)
    subscription.save(update_fields=[*NO_PENDING_CHANGE, "updated_at"])


def _amount_minor(plan):
    price = charge_price(plan)
    return price.currency, int(price.amount * MINOR_UNITS)


def _change_price(subscription, plan, *, immediate):
    currency, amount_minor = _amount_minor(plan)
    return stripe_client.change_subscription_price(
        subscription_id=subscription.stripe_subscription_id,
        company_id=subscription.company_id,
        plan=plan,
        currency=currency,
        amount_minor=amount_minor,
        immediate=immediate,
        idempotency_key=str(uuid4()),  # the company lock already stops a double click
    )


def _record(subscription, kind, by, old, new):
    record(
        "plan.changed",
        actor=by,
        target=Company.objects.get(pk=subscription.company_id),
        details={"kind": kind},
        changes={"plan": {"old": old, "new": new}},
    )


def _changeable_subscription(company_id, now):
    subscription = get_subscription(company_id)
    if (
        subscription.state != State.ACTIVE
        or effective_state(subscription, now) != State.ACTIVE
        or subscription.plan is None
        or not subscription.stripe_subscription_id
    ):
        raise _refuse(
            "plan_change_unavailable",
            "Your plan can be changed only while it is active and paid by card.",
        )
    return subscription


def request_change(company_id, plan_id, *, by=None):
    """Asks for another plan. Returns (result, url): `processing` or `action_required` for an
    upgrade, `downgrade_scheduled` for a downgrade."""
    target = _buyable_plan(plan_id)
    now = timezone.now()
    with transaction.atomic():
        _lock(company_id)
        subscription = _changeable_subscription(company_id, now)
        current = subscription.plan
        if target.pk == current.pk:
            raise _refuse("same_plan", "Your company is already on this plan.")
        if _is_processing(subscription, now):
            raise _refuse(
                "plan_change_processing", "Your upgrade is still being processed. Please wait."
            )
        if charge_price(target).amount > charge_price(current).amount:
            return _upgrade(subscription, target, by, now)
        return _downgrade(subscription, target, by, now)


def _upgrade(subscription, target, by, now):
    outcome = _change_price(subscription, target, immediate=True)
    if outcome.status == stripe_client.DECLINED:
        raise AppError("payment_declined", DECLINED_MESSAGE, status_code=402)
    _store_pending(subscription, target, Change.UPGRADE, now)
    _record(subscription, Change.UPGRADE, by, subscription.plan_id, target.pk)
    if outcome.status == stripe_client.NEEDS_ACTION:
        return UPGRADE_ACTION, outcome.url
    return UPGRADE_PROCESSING, ""


def _downgrade(subscription, target, by, now):
    over = over_limits(subscription.company_id, target)
    if over:
        raise _refuse(
            "downgrade_blocked",
            f"You cannot move to {target.name} yet. {_over_text(over)}. "
            "Reduce your use, then try again.",
            details={"over": over},
        )
    _change_price(subscription, target, immediate=False)
    _store_pending(subscription, target, Change.DOWNGRADE, now)
    _record(subscription, Change.DOWNGRADE, by, subscription.plan_id, target.pk)
    return DOWNGRADE_SCHEDULED, ""


def cancel_downgrade(company_id, *, by=None):
    """Takes a waiting downgrade back: the provider's price returns to the current plan's price
    (nothing charged or credited) and the waiting plan is forgotten."""
    now = timezone.now()
    with transaction.atomic():
        _lock(company_id)
        subscription = _changeable_subscription(company_id, now)
        if subscription.pending_change != Change.DOWNGRADE:
            raise _refuse("no_downgrade_waiting", "There is no plan change waiting.")
        waiting = subscription.pending_plan_id
        _change_price(subscription, subscription.plan, immediate=False)
        _forget_pending(subscription)
        _record(subscription, "downgrade_cancelled", by, waiting, subscription.plan_id)


def pending_of(subscription, now=None):
    """What the billing screen shows about a change in flight, or None."""
    if not subscription.pending_change or subscription.pending_plan is None:
        return None
    now = now or timezone.now()
    return {
        "kind": subscription.pending_change,
        "plan_id": subscription.pending_plan_id,
        "plan_name": subscription.pending_plan.name,
        "takes_effect": subscription.period_end
        if subscription.pending_change == Change.DOWNGRADE
        else None,
        "processing": subscription.pending_change == Change.UPGRADE
        and _is_processing(subscription, now),
    }


def warn_over_limits(company_id):
    """After a plan got smaller: tells the owner exactly what is over and by how much. Nothing
    is deleted; the limit checks already refuse new work until the company is under the limit."""
    owner = owner_of(company_id)
    plan = get_subscription(company_id).plan
    over = over_limits(company_id, plan) if plan else []
    if owner is None or not over:
        return
    send_email(
        "usage_notice",
        owner.email,
        name=owner.name,
        title="Your company is over its plan limits",
        message=f"You are now on the {plan.name} plan. {_over_text(over)}. Nothing was deleted. "
        "You cannot add more of these until you are under the limit.",
        link=build_link("/company/billing"),
    )
