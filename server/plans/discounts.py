"""Discount codes, made and kept at the payment provider.

A super admin creates a coupon (a percentage or a fixed US-dollar amount, for the first payment,
some months or forever) and a promotion code for it (expiry, use limit, first-time customers only)
through the provider's API. The provider applies the discount to the subscription and its
invoices, so renewals and "first N months" are right; this server never works the discount out for
the charge. It only keeps the ids, the plan a code is limited to (the one rule the provider cannot
enforce for inline prices), and shows the company the price, the discount and the new price before
it pays (for display; the provider's invoice is the truth).

Test mode only for now, like checkout. A code that cannot be used, for whatever reason, always
gets the same answer, so nobody can learn which codes exist.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from audit.service import record
from core.errors import AppError
from platform_settings.service import get_setting

from . import stripe_client
from .models import DiscountCode, PaymentEvent, Plan, Subscription
from .pricing import USD, charge_price

NOT_USABLE_CODE = "codenot_usable"
NOT_USABLE = "This code cannot be used."
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,39}$")
MINOR_UNITS = Decimal(100)
PERCENT = Decimal(100)
CENT = Decimal("0.01")
ONCE, MONTHS, FOREVER = "once", "months", "forever"
STRIPE_DURATION = {ONCE: "once", MONTHS: "repeating", FOREVER: "forever"}


def normalised(code):
    return re.sub(r"\s+", "", str(code)).upper()


def not_usable():
    return AppError(NOT_USABLE_CODE, NOT_USABLE, status_code=400)


def problem(field, message):
    return AppError("invalid_discount", message, status_code=400, fields={field: message})


def _checked_new(values):
    """The rules between a new code's fields, read from the platform settings."""
    if not CODE_PATTERN.match(values["code"]):
        raise problem("code", "Use 3 to 40 letters, numbers, dashes or underscores.")
    if values["kind"] == "percent":
        if values["value"] != int(values["value"]) or not 1 <= values["value"] <= 100:
            raise problem("value", "A percentage is a whole number from 1 to 100.")
    else:
        largest = get_setting("discounts.max_amount_off_usd")
        if not 0 < values["value"] <= largest:
            raise problem("value", f"A fixed amount is above 0 and at most {largest} US dollars.")
    if values["duration"] == MONTHS:
        longest = get_setting("discounts.max_months")
        if not values.get("months") or not 1 <= values["months"] <= longest:
            raise problem("months", f"Use 1 to {longest} months.")
    if values.get("expires_at") and values["expires_at"] <= timezone.now():
        raise problem("expires_at", "The code must expire in the future.")
    if values.get("plan") is not None and values["plan"].status != Plan.Status.ACTIVE:
        raise problem("plan_id", "Choose an active plan.")


def create(admin, values):
    """Makes the coupon and the promotion code at the provider, then the local record. `values`:
    code, kind (percent or amount), value, duration (once, months, forever), months, expires_at,
    max_redemptions, first_time_only, plan (a Plan or None)."""
    values = {**values, "code": normalised(values["code"])}
    _checked_new(values)
    if DiscountCode.objects.filter(code=values["code"]).exists():
        raise problem("code", "This code already exists.")
    key = uuid.uuid4().hex  # the provider makes nothing twice for a repeated call of this one
    percent = values["kind"] == "percent"
    coupon = stripe_client.create_coupon(
        idempotency_key=f"coupon-{key}",
        percent_off=int(values["value"]) if percent else None,
        amount_off_minor=None if percent else int(Decimal(values["value"]) * MINOR_UNITS),
        duration=STRIPE_DURATION[values["duration"]],
        months=values.get("months"),
    )
    promotion = stripe_client.create_promotion_code(
        idempotency_key=f"promotion-{key}",
        coupon_id=coupon.id,
        code=values["code"],
        expires_at=values.get("expires_at"),
        max_redemptions=values.get("max_redemptions"),
        first_time_only=bool(values.get("first_time_only")),
    )
    with transaction.atomic():
        row = DiscountCode.objects.create(
            code=values["code"],
            stripe_coupon_id=coupon.id,
            stripe_promotion_code_id=promotion.id,
            plan=values.get("plan"),
        )
        record(
            "admin.discount_created",
            actor=admin,
            details={
                "credential": row.pk,
                "kind": values["kind"],
                "duration": values["duration"],
                "plan": values["plan"].pk if values.get("plan") else None,
            },
        )
    return row


def _row(discount_id):
    row = DiscountCode.objects.select_for_update().filter(pk=discount_id).first()
    if row is None:
        raise AppError("discount_not_found", "There is no such code.", status_code=404)
    return row


def switch(admin, discount_id, *, enabled):
    """Switches the promotion code on or off at the provider and here."""
    with transaction.atomic():
        row = _row(discount_id)
        if row.enabled == enabled:
            raise AppError("nothing_changed", "Nothing was changed.", status_code=400)
        stripe_client.set_promotion_code_active(row.stripe_promotion_code_id, enabled)
        row.enabled = enabled
        row.save(update_fields=["enabled"])
        record(
            "admin.discount_changed",
            actor=admin,
            details={"credential": row.pk},
            changes={"enabled": {"old": not enabled, "new": enabled}},
        )
    return row


def set_plan(admin, discount_id, *, plan):
    """Limits the code to one plan, or to every plan (None)."""
    with transaction.atomic():
        row = _row(discount_id)
        if row.plan_id == (plan.pk if plan else None):
            raise AppError("nothing_changed", "Nothing was changed.", status_code=400)
        if plan is not None and plan.status != Plan.Status.ACTIVE:
            raise problem("plan_id", "Choose an active plan.")
        before = row.plan_id
        row.plan = plan
        row.save(update_fields=["plan"])
        record(
            "admin.discount_changed",
            actor=admin,
            details={"credential": row.pk},
            changes={"plan": {"old": before, "new": plan.pk if plan else None}},
        )
    return row


def _timestamp(seconds):
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat() if seconds else None


def _coupon_of(promotion):
    return promotion.promotion.coupon


def _described(row, promotion):
    base = {
        "id": row.pk,
        "code": row.code,
        "plan_id": row.plan_id,
        "enabled": row.enabled,
        "created_at": row.created_at.isoformat(),
    }
    if promotion is None:  # the provider could not be reached or no longer has it
        return {**base, "known": False}
    coupon = _coupon_of(promotion)
    restrictions = getattr(promotion, "restrictions", None)
    return {
        **base,
        "known": True,
        "percent_off": coupon.percent_off,
        "amount_off": (
            f"{Decimal(coupon.amount_off) / MINOR_UNITS:.2f}" if coupon.amount_off else None
        ),
        "duration": {"once": ONCE, "repeating": MONTHS, "forever": FOREVER}[coupon.duration],
        "months": coupon.duration_in_months,
        "expires_at": _timestamp(promotion.expires_at),
        "max_redemptions": promotion.max_redemptions,
        "times_redeemed": promotion.times_redeemed,
        "first_time_only": bool(restrictions and restrictions.first_time_transaction),
        "active": bool(promotion.active),
    }


def list_codes():
    """Every code with the provider's own figures (use counts included)."""
    try:
        at_provider = stripe_client.list_promotion_codes()
    except AppError:
        at_provider = {}
    return [
        _described(row, at_provider.get(row.stripe_promotion_code_id))
        for row in DiscountCode.objects.select_related("plan")
    ]


# --- the company side ------------------------------------------------------------------------


@dataclass(frozen=True)
class Resolved:
    promotion_code_id: str
    percent_off: float | None
    amount_off_minor: int | None
    duration: str
    months: int | None


def _has_paid_before(company_id):
    if PaymentEvent.objects.filter(company_id=company_id, kind=PaymentEvent.Kind.PAYMENT).exists():
        return True
    return (
        Subscription.objects.filter(company_id=company_id)
        .exclude(stripe_subscription_id="")
        .exists()
    )


def resolve(company_id, code, plan):
    """The code for this company and plan, or the one refusal. Our own rules first (on, the plan
    it is limited to, first-time customers only), then the provider's (on, not expired, not used
    up). The provider applies it to the checkout; this only decides whether to offer it. With no
    plan, only the rules that do not depend on a plan are checked."""
    row = DiscountCode.objects.filter(code=normalised(code), enabled=True).first()
    if row is None or (plan is not None and row.plan_id not in (None, plan.pk)):
        raise not_usable()
    promotion = stripe_client.retrieve_promotion_code(row.stripe_promotion_code_id)
    coupon = _coupon_of(promotion)
    expired = promotion.expires_at and promotion.expires_at <= timezone.now().timestamp()
    used_up = promotion.max_redemptions and promotion.times_redeemed >= promotion.max_redemptions
    first_time_only = bool(
        getattr(promotion, "restrictions", None) and promotion.restrictions.first_time_transaction
    )
    if (
        not promotion.active
        or not coupon.valid
        or expired
        or used_up
        or (first_time_only and _has_paid_before(company_id))
        or (
            plan is not None
            and coupon.amount_off
            and str(coupon.currency).upper() != charge_price(plan).currency
        )
    ):
        raise not_usable()
    return Resolved(
        promotion_code_id=row.stripe_promotion_code_id,
        percent_off=float(coupon.percent_off) if coupon.percent_off else None,
        amount_off_minor=coupon.amount_off or None,
        duration={"once": ONCE, "repeating": MONTHS, "forever": FOREVER}[coupon.duration],
        months=coupon.duration_in_months,
    )


def preview(resolved, plan):
    """Price, discount and new price for the company to see before paying. Display only."""
    price = charge_price(plan)
    if resolved.percent_off is not None:
        discount = (price.amount * Decimal(str(resolved.percent_off)) / PERCENT).quantize(
            CENT, ROUND_HALF_UP
        )
    else:
        discount = min(price.amount, Decimal(resolved.amount_off_minor) / MINOR_UNITS)
    return {
        "currency": USD,
        "price": f"{price.amount:.2f}",
        "discount": f"{discount:.2f}",
        "new_price": f"{price.amount - discount:.2f}",
        "duration": resolved.duration,
        "months": resolved.months,
    }
