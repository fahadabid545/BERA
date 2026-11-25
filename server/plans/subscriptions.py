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
from notifications.payment_notice import payment_failed
from platform_settings.service import get_setting

from . import stripe_client
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

TRIAL_NOT_AVAILABLE = "A free trial is not available for your company."
TRIAL_ENDED_TEXT = (
    "Your free trial has ended. You can still view and download your data, but you cannot "
    "upload, start projects or score until you choose a plan. Nothing was deleted."
)

# What a plan change in flight leaves behind once it is over (applied, or the subscription ended).
NO_PENDING_CHANGE = {"pending_plan": None, "pending_change": "", "pending_since": None}
# A change waiting for the next renewal survives a late payment, but not the end of access.
KEEPS_PENDING_CHANGE = frozenset({State.ACTIVE, State.PAST_DUE})

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


def _notice_title(subscription, was_trial):
    if subscription.state == State.GRANTED_FREE and subscription.on_trial:
        return "Your free trial has started"
    if subscription.state == State.EXPIRED and was_trial:
        return "Your free trial has ended"
    return NOTICE_TITLES[subscription.state]


def _notice_text(subscription, was_trial=False):
    plan = subscription.plan.name if subscription.plan else ""
    end = subscription.period_end.strftime("%d %B %Y") if subscription.period_end else ""
    return {
        State.ACTIVE: f"Your {plan} plan is active until {end}.",
        State.PAST_DUE: "We could not take your payment. You keep full access until "
        f"{grace_ends_at(subscription).strftime('%d %B %Y') if subscription.past_due_since else ''}"
        ". Please update your payment method.",
        State.CANCELLED: f"Your subscription is cancelled. You keep full access until {end}.",
        State.EXPIRED: TRIAL_ENDED_TEXT
        if was_trial
        else "Your subscription has ended. You can still view and download your "
        "data, but you cannot upload, start projects or score until you renew.",
        State.GRANTED_FREE: (
            f"Your free trial of the {plan} plan started. It runs until {end}, or until you "
            f"have used its limit of {subscription.trial_cv_limit} CVs."
            if subscription.on_trial
            else f"A free {plan} plan was granted to your company until {end}."
        ),
    }[subscription.state]


def owner_of(company_id):
    return CompanyUser.objects.filter(
        company_id=company_id, role=CompanyUser.Role.OWNER, status=CompanyUser.Status.ACTIVE
    ).first()


def _email_the_owner(subscription, was_trial=False):
    owner = owner_of(subscription.company_id)
    if owner is None:
        return
    if subscription.state == State.PAST_DUE:
        payment_failed(subscription, owner, _notice_text(subscription))  # once, never optional
        return
    send_email(
        "usage_notice",
        owner.email,
        name=owner.name,
        title=_notice_title(subscription, was_trial),
        message=_notice_text(subscription, was_trial),
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
    was_trial = subscription.on_trial
    subscription.state = new_state
    fields = {"on_trial": False, **fields}  # a trial ends with any change, unless one starts
    if new_state not in KEEPS_PENDING_CHANGE:
        fields = {**NO_PENDING_CHANGE, **fields}
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
    _email_the_owner(subscription, was_trial=was_trial)
    return subscription


def activate(company_id, plan, *, period_start, period_end, renewal=True, **provider_ids):
    """A payment succeeded (first payment, renewal or plan change). Moves a waiting price or
    limit change of the plan into effect at the same time. `provider_ids` are the payment
    provider's customer and subscription ids, kept on the record."""
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
        **NO_PENDING_CHANGE,
        **provider_ids,
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


def cancel(company_id, *, source=PAYMENT, by=None):
    """Renewal is switched off; access continues until the paid period ends."""
    return _change(company_id, State.CANCELLED, {State.ACTIVE}, source=source, by=by, renewal=False)


def resume(company_id, *, by=None):
    """A cancelled subscription whose period has not ended renews again; nothing is charged now."""
    return _change(company_id, State.ACTIVE, {State.CANCELLED}, source=PAYMENT, by=by, renewal=True)


def expire(company_id, *, source=SYSTEM, by=None, reason="", kind=None):
    """Access ends. A subscription still running at the payment provider is ended there too, so
    nothing more is charged for access the company no longer has."""
    if kind is None and get_subscription(company_id).on_trial:
        kind = "trial.ended"
    subscription = _change(
        company_id,
        State.EXPIRED,
        CAN_BE_EXPIRED,
        source=source,
        by=by,
        reason=reason,
        kind=kind,
        renewal=False,
    )
    if subscription.stripe_subscription_id:
        stripe_client.end_subscription(subscription.stripe_subscription_id)
    return subscription


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


def start_trial(
    company_id, plan, *, period_end, cv_limit, source, by=None, reason="", kind="trial.started"
):
    """Starts the company's one free trial: a free grant that also stops after `cv_limit` CVs
    (see `trials.py`). Refused when the company has had a trial before or still has access."""
    now = timezone.now()
    with transaction.atomic():
        if _lock(company_id).trial_started_at is not None:
            raise AppError("trial_used", TRIAL_NOT_AVAILABLE, status_code=409)
        return _change(
            company_id,
            State.GRANTED_FREE,
            CAN_BE_GRANTED_FREE,
            source=source,
            by=by,
            reason=reason,
            kind=kind,
            plan=plan,
            period_start=now,
            period_end=period_end,
            renewal=False,
            past_due_since=None,
            on_trial=True,
            trial_started_at=now,
            trial_cv_limit=cv_limit,
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


def terminate(company_id, *, by, reason):
    """An admin ends the subscription now. Only access ends: the company's data stays until the
    retention period runs out (nothing here deletes anything)."""
    return expire(
        company_id, source=ADMIN, by=by, reason=reason, kind="admin.subscription_terminated"
    )
