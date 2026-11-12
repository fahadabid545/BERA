"""Every change to a company's subscription state. Only payment events and admin actions call
these (their tickets come later); there is no route, so a company can never change its own."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from audit.service import record
from companies.models import Company, CompanyUser
from core.errors import AppError
from core.jobs import logged_job
from emailing.links import build_link
from emailing.service import send_email
from platform_settings.service import get_setting

from .models import Subscription
from .service import apply_pending_change

State = Subscription.State
PAYMENT = "payment"
ADMIN = "admin"
SYSTEM = "system"

# States that give full use of the product. An expired or plan-less company can only view and
# download.
FULL_ACCESS_STATES = frozenset({State.ACTIVE, State.PAST_DUE, State.CANCELLED, State.GRANTED_FREE})
CAN_BE_EXPIRED = frozenset({State.ACTIVE, State.PAST_DUE, State.CANCELLED, State.GRANTED_FREE})
CAN_BE_GRANTED_FREE = frozenset({State.NO_PLAN, State.EXPIRED})

NOTICE_TITLES = {
    State.ACTIVE: "Your plan is active",
    State.PAST_DUE: "Your payment is overdue",
    State.CANCELLED: "Your subscription is cancelled",
    State.EXPIRED: "Your subscription has ended",
    State.GRANTED_FREE: "A free plan was granted to your company",
}


def get_subscription(company_id):
    """The company's subscription; a new company has none yet, which means No plan."""
    subscription, _ = Subscription.objects.get_or_create(company_id=company_id)
    return subscription


def grace_ends_at(subscription):
    days = get_setting("billing.past_due_grace_days")
    return subscription.past_due_since + timedelta(days=days)


def effective_state(subscription, now=None):
    """The state access is decided on, worked out from the dates. A paid, renewing period that
    ran out stays Active: the payment event (renewed or failed) decides what comes next."""
    now = now or timezone.now()
    state = subscription.state
    ended = subscription.period_end is not None and subscription.period_end <= now
    if state == State.PAST_DUE and grace_ends_at(subscription) <= now:
        return State.EXPIRED
    if state in (State.CANCELLED, State.GRANTED_FREE) and ended:
        return State.EXPIRED
    if state == State.ACTIVE and not subscription.renewal and ended:
        return State.EXPIRED
    return state


def status_of(company_id, now=None):
    """What the billing screens and warnings show."""
    subscription = get_subscription(company_id)
    state = effective_state(subscription, now)
    return {
        "state": state,
        "plan": subscription.plan,
        "period_start": subscription.period_start,
        "period_end": subscription.period_end,
        "renewal": subscription.renewal,
        "grace_ends_at": grace_ends_at(subscription) if state == State.PAST_DUE else None,
    }


# The access rules, one place for the projects, upload and scoring tickets to call.
def can_view(company_id):
    """Viewing and downloading are allowed in every state."""
    return True


def can_create_project(company_id):
    return effective_state(get_subscription(company_id)) in FULL_ACCESS_STATES


def can_upload(company_id):
    return effective_state(get_subscription(company_id)) in FULL_ACCESS_STATES


def can_score(company_id):
    return effective_state(get_subscription(company_id)) in FULL_ACCESS_STATES


def _refuse(message):
    return AppError("subscription_change_refused", message, status_code=409)


def _notice_text(subscription):
    plan = subscription.plan.name if subscription.plan else ""
    end = subscription.period_end.strftime("%d %B %Y") if subscription.period_end else ""
    return {
        State.ACTIVE: f"Your {plan} plan is active until {end}.",
        State.PAST_DUE: "We could not take your payment. You keep full access until "
        f"{grace_ends_at(subscription).strftime('%d %B %Y') if subscription.past_due_since else ''}"
        ". Please update your payment method.",
        State.CANCELLED: f"Your subscription is cancelled. You keep full access until {end}.",
        State.EXPIRED: "Your subscription has ended. You can still view and download your "
        "data, but you cannot upload, start projects or score until you renew.",
        State.GRANTED_FREE: f"A free {plan} plan was granted to your company until {end}.",
    }[subscription.state]


def _email_the_owner(subscription):
    owner = CompanyUser.objects.filter(
        company_id=subscription.company_id,
        role=CompanyUser.Role.OWNER,
        status=CompanyUser.Status.ACTIVE,
    ).first()
    if owner is None:
        return
    send_email(
        "usage_notice",
        owner.email,
        name=owner.name,
        title=NOTICE_TITLES[subscription.state],
        message=_notice_text(subscription),
        link=build_link("/company/billing"),
    )


def _lock(company_id):
    Company.objects.select_for_update().get(pk=company_id)  # serialises changes per company
    return get_subscription(company_id)


def _change(
    company_id, new_state, allowed_from, *, source, by=None, reason="", kind=None, **fields
):
    """Applies one transition, logs it in the audit log and emails the owner. A transition from
    a state not in `allowed_from` is refused and changes nothing."""
    with transaction.atomic():
        subscription = _lock(company_id)
        lapsed = effective_state(subscription)
        if allowed_from is not None and new_state != State.EXPIRED and lapsed == State.EXPIRED:
            if subscription.state != State.EXPIRED:
                _apply(subscription, State.EXPIRED, source=SYSTEM)  # catch up first
        if allowed_from is not None and subscription.state not in allowed_from:
            raise _refuse("This change is not possible for the company's subscription now.")
        return _apply(
            subscription, new_state, source=source, by=by, reason=reason, kind=kind, **fields
        )


def _apply(subscription, new_state, *, source, by=None, reason="", kind=None, **fields):
    before = {"state": subscription.state, "plan": subscription.plan_id}
    subscription.state = new_state
    for name, value in fields.items():
        setattr(subscription, name, value)
    subscription.save()
    record(
        kind or "subscription.state_changed",
        actor=by,
        target=Company.objects.get(pk=subscription.company_id),
        reason=reason,
        details={"source": source},
        changes={
            "state": {"old": before["state"], "new": new_state},
            "plan": {"old": before["plan"], "new": subscription.plan_id},
        },
    )
    _email_the_owner(subscription)
    return subscription


def activate(company_id, plan, *, period_start, period_end, renewal=True):
    """A payment succeeded (first payment, renewal or plan change). Moves a waiting price or
    limit change of the plan into effect at the same time."""
    apply_pending_change(plan)
    return _change(
        company_id,
        State.ACTIVE,
        None,
        source=PAYMENT,
        plan=plan,
        period_start=period_start,
        period_end=period_end,
        renewal=renewal,
        past_due_since=None,
    )


def mark_past_due(company_id):
    """A renewal payment failed. Full access continues for the grace period."""
    return _change(
        company_id,
        State.PAST_DUE,
        {State.ACTIVE},
        source=PAYMENT,
        past_due_since=timezone.now(),
    )


def cancel(company_id):
    """Renewal is switched off; access continues until the paid period ends."""
    return _change(company_id, State.CANCELLED, {State.ACTIVE}, source=PAYMENT, renewal=False)


def expire(company_id, *, source=SYSTEM, by=None, reason=""):
    return _change(
        company_id,
        State.EXPIRED,
        CAN_BE_EXPIRED,
        source=source,
        by=by,
        reason=reason,
        renewal=False,
    )


def grant_free(company_id, plan, *, period_end, by, reason):
    """An admin gives a free subscription for a chosen period. Refused while a subscription
    still gives access, so a company never holds two."""
    now = timezone.now()
    if period_end <= now:
        raise AppError("invalid_period", "The free period must end in the future.", status_code=400)
    return _change(
        company_id,
        State.GRANTED_FREE,
        CAN_BE_GRANTED_FREE,
        source=ADMIN,
        by=by,
        reason=reason,
        kind="admin.free_subscription_granted",
        plan=plan,
        period_start=now,
        period_end=period_end,
        renewal=False,
        past_due_since=None,
    )


def end_free(company_id, *, by, reason):
    """Ends a free grant before its date."""
    return _change(
        company_id,
        State.EXPIRED,
        {State.GRANTED_FREE},
        source=ADMIN,
        by=by,
        reason=reason,
        kind="admin.free_subscription_ended",
        period_end=timezone.now(),
    )


@logged_job
def expire_lapsed_subscriptions():
    """Saves the changes the dates already imply (grace over, period over), logs them and
    emails the owners. Reads are right without it; it is scheduled once periodic jobs exist."""
    candidates = Subscription.objects.filter(state__in=CAN_BE_EXPIRED)
    lapsed = [s.company_id for s in candidates if effective_state(s) == State.EXPIRED]
    for company_id in lapsed:
        expire(company_id)
    return len(lapsed)
