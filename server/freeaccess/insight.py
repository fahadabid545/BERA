"""What the admin reads about free access: one person's usage, activity and feedback, the daily
chart, an overview of the beta users and the list of paying companies.

Read-only. It holds counts, names and the feedback the people chose to send, never a CV or a
candidate; it changes nothing, so it cannot affect any of the three kinds of access.
"""

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from activity.models import ActivityEntry
from companies.models import CompanyUser
from core.errors import not_found
from feedback.models import Feedback
from plans import limits
from plans.models import Subscription
from plans.subscriptions import State, effective_state
from platform_settings.service import get_setting
from projects.service import active_project_count
from usage import service as usage
from usage.models import CvUsage

from . import entitlement, service
from .models import FreeAccess

PAID_STATES = (State.ACTIVE, State.PAST_DUE, State.CANCELLED)


def daily_cvs(company_ids):
    """CVs accepted per day over the last days (scored or waiting; a failed one gave its place
    back), as one entry for every day so a chart has no gaps."""
    days = get_setting("free_access.chart_days")
    today = timezone.localdate()
    first = today - timedelta(days=days - 1)
    counted = (
        CvUsage.objects.filter(
            company_id__in=company_ids,
            accepted_at__date__gte=first,
            status__in=[CvUsage.Status.PENDING, CvUsage.Status.SCORED],
        )
        .annotate(day=TruncDate("accepted_at"))
        .values("day")
        .annotate(cvs=Count("pk"))
    )
    per_day = {row["day"]: row["cvs"] for row in counted}
    return [
        {
            "day": (first + timedelta(days=offset)).isoformat(),
            "cvs": per_day.get(first + timedelta(days=offset), 0),
        }
        for offset in range(days)
    ]


def _usage_of(company_id, grant):
    current = usage.current_usage(company_id)
    figures = {
        "cvs_today": usage.cvs_since(company_id, entitlement.start_of_today()),
        "cvs_this_period": current["cvs_scored"] + usage.waiting_cvs(company_id),
        "tokens_in": current["tokens_in"],
        "tokens_out": current["tokens_out"],
        "estimated_cost": f"{current['estimated_cost']:.6f}",
        "projects": active_project_count(company_id),
    }
    if grant.kind == FreeAccess.Kind.BETA:
        figures["cvs_per_day_limit"] = get_setting("beta.cvs_per_day")
    figures["cvs_per_month_limit"] = limits.limit_for(company_id, limits.CVS_PER_MONTH)
    return figures


def _activity_of(company_id):
    entries = ActivityEntry.objects.filter(company_id=company_id).order_by("-created_at", "-id")
    return [
        {
            "id": entry.pk,
            "kind": entry.kind,
            "actor_name": entry.actor_name,
            "created_at": entry.created_at.isoformat(),
        }
        for entry in entries[: get_setting("free_access.detail_items")]
    ]


def _feedback_of(company_id):
    sent = Feedback.objects.filter(company_id=company_id).select_related("user")
    return [
        {
            "id": str(item.pk),
            "kind": item.kind,
            "status": item.status,
            "message": item.message,
            "user": item.user.name,
            "created_at": item.created_at.isoformat(),
        }
        for item in sent.order_by("-created_at", "-pk")[: get_setting("free_access.detail_items")]
    ]


def grant_detail(grant_id):
    """One access with the company's usage, daily CVs, latest activity and feedback."""
    grant = FreeAccess.objects.select_related("invite", "plan").filter(pk=grant_id).first()
    if grant is None:
        raise not_found()
    company_id = grant.company_id
    return {
        **service.describe_grant(grant),
        "usage": _usage_of(company_id, grant),
        "daily_cvs": daily_cvs([company_id]),
        "activity": _activity_of(company_id),
        "feedback": _feedback_of(company_id),
    }


def beta_overview():
    """How many beta accesses are in each state, the CVs they scored each day, and how much
    feedback they sent."""
    now = timezone.now()
    beta = FreeAccess.objects.filter(kind=FreeAccess.Kind.BETA)
    company_ids = list(beta.values_list("company_id", flat=True).distinct())
    return {
        "active": beta.filter(revoked_at__isnull=True, ends_at__gt=now).count(),
        "ended": beta.filter(revoked_at__isnull=True, ends_at__lte=now).count(),
        "revoked": beta.filter(revoked_at__isnull=False).count(),
        "feedback": Feedback.objects.filter(company_id__in=company_ids).count(),
        "daily_cvs": daily_cvs(company_ids),
    }


def checked_page(raw):
    return int(raw) if str(raw).isdigit() and int(raw) > 0 else 1


def _paid_row(subscription):
    company = subscription.company
    figures = usage.current_usage(company.pk)
    grants = {
        grant.kind
        for grant in entitlement.active_grants(company.pk)  # the other ways it has access
    }
    return {
        "id": str(company.pk),
        "name": company.name,
        "plan_name": subscription.plan.name if subscription.plan else None,
        "state": effective_state(subscription),
        "period_end": subscription.period_end.isoformat() if subscription.period_end else None,
        "cvs_used": figures["cvs_scored"] + usage.waiting_cvs(company.pk),
        "cvs_limit": limits.limit_for(company.pk, limits.CVS_PER_MONTH),
        "users": CompanyUser.objects.filter(company=company)
        .exclude(status=CompanyUser.Status.REMOVED)
        .count(),
        "also_free_access": sorted(grants),
    }


def list_paid(*, search="", page=1):
    """Companies that pay by card, a page at a time. A free trial or a free grant is not paying."""
    paid = (
        Subscription.objects.exclude(stripe_subscription_id="")
        .filter(state__in=PAID_STATES, plan__isnull=False)
        .select_related("company", "plan")
    )
    if search.strip():
        paid = paid.filter(company__name__icontains=search.strip())
    paid = paid.order_by("company__name", "pk")
    size = get_setting("free_access.page_size")
    return {
        "total": paid.count(),
        "page": page,
        "page_size": size,
        "items": [_paid_row(each) for each in paid[(page - 1) * size : page * size]],
    }
