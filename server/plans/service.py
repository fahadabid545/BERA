"""Creating, changing and listing plans. Every change goes through here, so the rules and the
audit entry cannot be skipped."""

from decimal import Decimal

from django.db import transaction

from audit.service import record
from core.errors import AppError

from .models import PendingPlanChange, Plan
from .subscribers import subscriber_count

# What a plan needs before it can be active (the PKR price and the description are optional).
NUMBERS_NEEDED_TO_BE_ACTIVE = (
    "price_usd",
    "cvs_per_month",
    "cvs_per_project",
    "max_projects",
    "max_team_accounts",
    "max_top_n",
    "monthly_ai_token_cap",
)
# What subscribers pay or may use. Changing these never touches subscribers until renewal
# unless the admin chooses "now". Name, description, order and status do not change what a
# subscriber bought, so they apply at once.
ENTITLEMENT_FIELDS = (
    "price_usd",
    "price_pkr",
    "cvs_per_month",
    "cvs_per_project",
    "max_projects",
    "max_team_accounts",
    "max_top_n",
    "monthly_ai_token_cap",
)
IMMEDIATE_FIELDS = ("name", "description", "status", "display_order")
EDITABLE_FIELDS = IMMEDIATE_FIELDS + ENTITLEMENT_FIELDS
NOW = "now"
RENEWAL = "renewal"

HAS_SUBSCRIBERS = "This plan has subscribers, so it cannot be deleted. Archive it instead."
CHANGE_NOTHING = "Nothing was changed."


def _plain(value):
    """A value as it is written in the audit log."""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return value


def missing_for_active(values):
    """The numbers still empty, given a plan's values (a dict or a plan)."""
    get = values.get if isinstance(values, dict) else lambda name: getattr(values, name)
    return [name for name in NUMBERS_NEEDED_TO_BE_ACTIVE if get(name) is None]


def _refuse_if_incomplete_and_active(values):
    if values.get("status") != Plan.Status.ACTIVE:
        return
    missing = missing_for_active(values)
    if missing:
        raise AppError(
            "plan_incomplete",
            "A plan needs all its numbers before it can be active.",
            status_code=400,
            fields={name: "Fill this in before the plan can be active." for name in missing},
        )


def _values_of(plan):
    return {name: getattr(plan, name) for name in EDITABLE_FIELDS}


def active_plans():
    """The plans visitors may buy: never hidden or archived ones."""
    return Plan.objects.filter(status=Plan.Status.ACTIVE)


def create_plan(admin, values):
    values = {"status": Plan.Status.HIDDEN, **values}
    _refuse_if_incomplete_and_active({**{n: None for n in EDITABLE_FIELDS}, **values})
    with transaction.atomic():
        plan = Plan.objects.create(**values)
        record(
            "admin.plan_created",
            actor=admin,
            details={"plan_id": plan.pk, "plan_name": plan.name},
            changes={name: {"old": None, "new": _plain(value)} for name, value in values.items()},
        )
    return plan


def update_plan(admin, plan_id, values, *, reason, apply=None):
    """Changes a plan. For a plan with subscribers the price and limits wait for the next
    renewal unless `apply` is "now"; everything else applies at once. Returns the plan and
    whether some changes are waiting."""
    with transaction.atomic():
        plan = Plan.objects.select_for_update().get(pk=plan_id)
        before = _values_of(plan)
        changed = {name: value for name, value in values.items() if before[name] != value}
        if not changed:
            raise AppError("nothing_changed", CHANGE_NOTHING, status_code=400)
        _refuse_if_incomplete_and_active({**before, **changed})

        waits = (
            subscriber_count(plan) > 0
            and apply != NOW
            and any(name in ENTITLEMENT_FIELDS for name in changed)
        )
        later = {
            name: value for name, value in changed.items() if waits and name in ENTITLEMENT_FIELDS
        }
        now = {name: value for name, value in changed.items() if name not in later}
        for name, value in now.items():
            setattr(plan, name, value)
        if now:
            plan.save(update_fields=list(now))
        if later:
            _store_pending(plan, later)
        record(
            "admin.plan_changed",
            actor=admin,
            reason=reason,
            details={"plan_id": plan.pk, "applies": RENEWAL if later else NOW},
            changes={
                name: {"old": _plain(before[name]), "new": _plain(value)}
                for name, value in changed.items()
            },
        )
    return plan, bool(later)


def _store_pending(plan, later):
    """Joins an edit already waiting for renewal, so the newest value of a field wins."""
    pending, _ = PendingPlanChange.objects.get_or_create(plan=plan)
    pending.values = {**pending.values, **{name: _plain(value) for name, value in later.items()}}
    pending.save(update_fields=["values", "updated_at"])


def apply_pending_change(plan):
    """For the renewal: moves the waiting changes into the plan. Returns the plan."""
    with transaction.atomic():
        pending = PendingPlanChange.objects.select_for_update().filter(plan=plan).first()
        if pending is None:
            return plan
        for name, value in pending.values.items():
            setattr(
                plan,
                name,
                Decimal(value) if name.startswith("price_") and value is not None else value,
            )
        plan.save(update_fields=list(pending.values))
        pending.delete()
    return plan


def delete_plan(admin, plan_id, *, reason):
    """Only a plan nobody is subscribed to can be deleted; otherwise archive it."""
    with transaction.atomic():
        plan = Plan.objects.select_for_update().get(pk=plan_id)
        if subscriber_count(plan) > 0:
            raise AppError("plan_has_subscribers", HAS_SUBSCRIBERS, status_code=409)
        record(
            "admin.plan_deleted",
            actor=admin,
            reason=reason,
            details={"plan_id": plan.pk, "plan_name": plan.name},
            changes={
                name: {"old": _plain(value), "new": None}
                for name, value in _values_of(plan).items()
            },
        )
        plan.delete()
