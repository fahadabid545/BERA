"""AI spend alerts: an email to the super admins when AI spending passes a limit.

A super admin sets a daily and a monthly limit in US dollars (`ai.daily_spend_alert_usd`,
`ai.monthly_spend_alert_usd`; empty means no alert). Spending is the sum of the AI call records'
estimated costs, which were priced when each call was made. The day and the month are UTC.

`check` runs in the once-a-minute sweep. Spending only grows inside a period, so a limit is
crossed at most once per day or month: the alert is stored with its period and limit, and a second
check in the same period finds it and sends nothing. A new period, or a limit changed during the
period, is a new crossing. Nothing here reads or stores CV text.
"""

import logging
from datetime import UTC
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from adminusers.models import AdminUser
from audit.service import record
from emailing.links import build_link
from emailing.service import send_email
from platform_settings.models import PlatformSetting
from platform_settings.service import get_setting

from .models import AiCall, AiSpendAlert

logger = logging.getLogger(__name__)

SETTING_NAMES = {
    AiSpendAlert.Kind.DAILY: "ai.daily_spend_alert_usd",
    AiSpendAlert.Kind.MONTHLY: "ai.monthly_spend_alert_usd",
}
PERIOD_NAMES = {AiSpendAlert.Kind.DAILY: "today", AiSpendAlert.Kind.MONTHLY: "this month"}
CONTROLS_PATH = "/admin/advanced/ai-controls"
MONEY_PLACES = Decimal("0.01")


def period_of(kind, now):
    """(label stored with the alert, start of the period) for the UTC day or month of `now`."""
    moment = now.astimezone(UTC)
    if kind == AiSpendAlert.Kind.DAILY:
        return moment.strftime("%Y-%m-%d"), moment.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return moment.strftime("%Y-%m"), start


def spent_since(start, *, purpose=None):
    """What AI calls cost since `start`: all of them, or only those of one purpose."""
    calls = AiCall.objects.filter(created_at__gte=start)
    if purpose:
        calls = calls.filter(purpose=purpose)
    total = calls.aggregate(
        total=Coalesce(Sum("estimated_cost"), Decimal(0), output_field=DecimalField())
    )["total"]
    return total


def _money(value):
    return str(Decimal(value).quantize(MONEY_PLACES))


def _notify(kind, spent, limit):
    link = build_link(CONTROLS_PATH)
    for admin in AdminUser.objects.filter(
        role=AdminUser.Role.SUPER, status=AdminUser.Status.ACTIVE
    ):
        send_email(
            "ai_spend_alert",
            admin.email,
            name=admin.name,
            period=kind,
            period_name=PERIOD_NAMES[kind],
            spent=_money(spent),
            limit=_money(limit),
            link=link,
        )


def check(now=None):
    """Sends the alert for each limit that is passed and has not been alerted yet. Returns the
    kinds that were alerted."""
    now = now or timezone.now()
    alerted = []
    for kind, setting_name in SETTING_NAMES.items():
        limit = get_setting(setting_name)
        if limit is None:
            continue
        label, start = period_of(kind, now)
        spent = spent_since(start)
        if spent < Decimal(str(limit)):
            continue
        with transaction.atomic():
            _, created = AiSpendAlert.objects.get_or_create(
                kind=kind,
                period=label,
                limit_usd=Decimal(str(limit)),
                defaults={"spent_usd": spent},
            )
            if created:
                _notify(kind, spent, limit)
        if created:
            alerted.append(kind)
            logger.warning("AI spending passed the %s limit.", kind)
    return alerted


def describe(now=None):
    now = now or timezone.now()
    return {
        "daily_limit": _setting_text(SETTING_NAMES[AiSpendAlert.Kind.DAILY]),
        "monthly_limit": _setting_text(SETTING_NAMES[AiSpendAlert.Kind.MONTHLY]),
        "spent_today": _money(spent_since(period_of(AiSpendAlert.Kind.DAILY, now)[1])),
        "spent_this_month": _money(spent_since(period_of(AiSpendAlert.Kind.MONTHLY, now)[1])),
    }


def _setting_text(name):
    value = get_setting(name)
    return None if value is None else str(value)


def set_limits(daily, monthly, *, by, reason):
    """Sets both limits (None clears one) and records who changed them and why."""
    wanted = {
        SETTING_NAMES[AiSpendAlert.Kind.DAILY]: daily,
        SETTING_NAMES[AiSpendAlert.Kind.MONTHLY]: monthly,
    }
    with transaction.atomic():
        changes = {}
        for name, value in wanted.items():
            old = get_setting(name)
            if value is None:
                PlatformSetting.objects.filter(key=name).delete()
            else:
                PlatformSetting.objects.update_or_create(key=name, defaults={"value": float(value)})
            detail = (
                "daily_limit" if name == SETTING_NAMES[AiSpendAlert.Kind.DAILY] else "monthly_limit"
            )
            changes[detail] = {
                "old": None if old is None else str(old),
                "new": None if value is None else str(value),
            }
        record("admin.ai_spend_alerts_changed", actor=by, reason=reason, changes=changes)
    return describe()
