"""Free trials: a free grant (state "granted free") on a chosen plan that stops at a date or after
a number of CVs, whichever comes first. No card, no payment provider.

A trial starts only by a super admin's hand (for a company, with a written reason) or by the owner
redeeming a trial code a super admin made. Nothing starts one by itself. A company has one trial,
ever: `Subscription.trial_started_at` is kept after it ends. When the trial ends the company can
only view and download, like any ended subscription; nothing is deleted. Buying a plan during the
trial starts the paid period at once and drops what was left (see `subscriptions.activate`).
"""

import hashlib
import re
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from audit.service import record
from companies.models import Company
from core.errors import AppError
from platform_settings.service import get_setting
from usage import service as usage

from . import subscriptions
from .models import Plan, Subscription, TrialCode

State = Subscription.State
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0, O, 1, I: a code is read aloud and typed
CODE_LENGTH = 12
GROUP = 4
PREFIX = "TRIAL"
NOT_USABLE_CODE = "code_not_usable"
# One message for a code that does not exist, ran out, is switched off or was used, so the
# message never tells anyone which codes exist.
NOT_USABLE = "This code cannot be used."
TRIAL_CV_LIMIT_CODE = "trial_cv_limit_reached"
TRIAL_CV_LIMIT_MESSAGE = "Your free trial's limit of {limit} CVs has been reached."


def _normalised(code):
    return re.sub(r"[^A-Z0-9]", "", str(code).upper())


def hash_of(code):
    return hashlib.sha256(_normalised(code).encode()).hexdigest()


def new_code():
    body = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    groups = [body[i : i + GROUP] for i in range(0, CODE_LENGTH, GROUP)]
    return "-".join([PREFIX, *groups])


def on_trial(subscription):
    """True while a trial is running (not ended by its date)."""
    return subscription.on_trial and (
        subscriptions.effective_state(subscription) == State.GRANTED_FREE
    )


def _check_numbers(days, cv_limit):
    problems = {}
    if not 1 <= days <= get_setting("trials.max_days"):
        problems["days"] = f"Use 1 to {get_setting('trials.max_days')} days."
    if not 1 <= cv_limit <= get_setting("trials.max_cv_limit"):
        problems["cv_limit"] = f"Use 1 to {get_setting('trials.max_cv_limit')} CVs."
    if problems:
        raise AppError(
            "invalid_trial", "Check the trial's days and CVs.", status_code=400, fields=problems
        )


def _start(company_id, plan, *, days, cv_limit, source, by, reason, kind):
    _check_numbers(days, cv_limit)
    return subscriptions.start_trial(
        company_id,
        plan,
        period_end=timezone.now() + timedelta(days=days),
        cv_limit=cv_limit,
        source=source,
        by=by,
        reason=reason,
        kind=kind,
    )


def start_for_company(company_id, plan, *, days, cv_limit, by, reason):
    """A super admin starts a trial for a company, with a written reason."""
    return _start(
        company_id,
        plan,
        days=days,
        cv_limit=cv_limit,
        source=subscriptions.ADMIN,
        by=by,
        reason=reason,
        kind="admin.trial_started",
    )


# --- trial codes (super admin) ---------------------------------------------------------------


def create_code(admin, *, name, plan, days, cv_limit, expires_at):
    """Makes a code and returns (row, the code). The code is shown once; only its hash is kept."""
    _check_numbers(days, cv_limit)
    if expires_at <= timezone.now():
        raise AppError(
            "invalid_trial",
            "The code must expire in the future.",
            status_code=400,
            fields={"expires_at": "The code must expire in the future."},
        )
    code = new_code()
    with transaction.atomic():
        row = TrialCode.objects.create(
            name=name,
            code_hash=hash_of(code),
            plan=plan,
            days=days,
            cv_limit=cv_limit,
            expires_at=expires_at,
        )
        record(
            "admin.trial_code_created",
            actor=admin,
            details={"credential": row.pk, "days": days, "cap": cv_limit, "plan": plan.pk},
        )
    return row, code


def switch_code(admin, code_id, *, enabled):
    with transaction.atomic():
        row = TrialCode.objects.select_for_update().filter(pk=code_id).first()
        if row is None:
            raise AppError("trial_code_not_found", "There is no such code.", status_code=404)
        if row.enabled == enabled:
            raise AppError("nothing_changed", "Nothing was changed.", status_code=400)
        row.enabled = enabled
        row.save(update_fields=["enabled"])
        record(
            "admin.trial_code_switched",
            actor=admin,
            details={"credential": row.pk, "enabled": enabled},
        )
    return row


def code_status(row, now=None):
    now = now or timezone.now()
    if row.redeemed_company_id is not None:
        return "redeemed"
    if not row.enabled:
        return "off"
    return "expired" if row.expires_at <= now else "unused"


def describe_code(row):
    company = (
        Company.objects.filter(pk=row.redeemed_company_id).values("id", "name").first()
        if row.redeemed_company_id
        else None
    )
    return {
        "id": row.pk,
        "name": row.name,
        "plan": {"id": row.plan_id, "name": row.plan.name},
        "days": row.days,
        "cv_limit": row.cv_limit,
        "expires_at": row.expires_at.isoformat(),
        "enabled": row.enabled,
        "status": code_status(row),
        "redeemed_at": row.redeemed_at.isoformat() if row.redeemed_at else None,
        "redeemed_company": {"id": company["id"], "name": company["name"]} if company else None,
        "created_at": row.created_at.isoformat(),
    }


def list_codes():
    return [describe_code(row) for row in TrialCode.objects.select_related("plan")]


# --- the company side ------------------------------------------------------------------------


def usable_code(code):
    """The trial code row if the text is a trial code that can still be redeemed, else None (used
    to tell a trial code from a discount code; it never says why a code is not usable)."""
    row = TrialCode.objects.select_related("plan").filter(code_hash=hash_of(code)).first()
    return row if row is not None and code_status(row) == "unused" else None


def redeem(company_id, owner, code):
    """The owner starts the company's trial with a code. A code that cannot be used (unknown,
    expired, switched off, used) always gets the same refusal."""
    with transaction.atomic():
        row = TrialCode.objects.select_for_update().filter(code_hash=hash_of(code)).first()
        if row is None or code_status(row) != "unused":
            raise AppError(NOT_USABLE_CODE, NOT_USABLE, status_code=400)
        _start(
            company_id,
            row.plan,
            days=row.days,
            cv_limit=row.cv_limit,
            source="code",
            by=owner,
            reason="",
            kind="trial.code_redeemed",
        )
        row.redeemed_company_id = company_id
        row.redeemed_at = timezone.now()
        row.save(update_fields=["redeemed_company_id", "redeemed_at"])
    return subscriptions.get_subscription(company_id)


# --- the CV limit ----------------------------------------------------------------------------


def cvs_used(subscription):
    """CVs counted against the trial: scored or waiting since it started."""
    return usage.cvs_since(subscription.company_id, subscription.trial_started_at)


def describe_trial(subscription):
    """What the billing screens show about a trial (None when none is running)."""
    if not on_trial(subscription):
        return None
    return {
        "ends_at": subscription.period_end.isoformat(),
        "cv_limit": subscription.trial_cv_limit,
        "cvs_used": cvs_used(subscription),
    }


def plan_for(plan_id):
    plan = Plan.objects.filter(pk=plan_id).first()
    if plan is None:
        raise AppError("plan_not_found", "There is no such plan.", status_code=404)
    return plan
