"""The Usage tab's history: CVs, tokens and estimated cost for each billing period, for each
project of one period, and when in the week CVs were uploaded in it.

Every figure is read from the same counters the limits and the plan card use (`UsageCounter`,
`CvUsage`), never recomputed from anything else, so the tab always matches them. A period is a
billing period, not a calendar month. Hours and weekdays are in UTC."""

import uuid
from datetime import UTC
from decimal import Decimal

from django.db.models import Count
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay

from core.errors import form_error
from platform_settings.service import get_setting
from projects.models import Project

from .models import CvUsage, UsageCounter, UsagePeriod

WEEKDAYS = 7
HOURS = 24


def _figures(counters):
    cvs = sum(c.cvs_scored for c in counters)
    tokens_in = sum(c.tokens_in for c in counters)
    tokens_out = sum(c.tokens_out for c in counters)
    cost = sum((c.estimated_cost for c in counters), Decimal(0))
    return {
        "cvs": cvs,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens": tokens_in + tokens_out,
        "estimated_cost": f"{cost:.6f}",
    }


def _checked_period(periods, raw):
    """The chosen period (the newest when none is named) or a form error."""
    if raw in (None, ""):
        return periods[0] if periods else None
    try:
        wanted = uuid.UUID(str(raw))
    except ValueError:
        wanted = None
    for period in periods:
        if period.pk == wanted:
            return period
    raise form_error({"period": "Choose one of the periods listed."})


def _projects(company_id, counters):
    titles = dict(
        Project.objects.filter(
            company_id=company_id, pk__in=[c.project_id for c in counters if c.project_id]
        ).values_list("pk", "title")
    )
    rows = [
        {
            "project_id": str(c.project_id) if c.project_id else None,
            # A deleted project keeps its counters, so its row stays with no title.
            "title": titles.get(c.project_id),
            **_figures([c]),
        }
        for c in counters
    ]
    return sorted(rows, key=lambda row: (-Decimal(row["estimated_cost"]), row["title"] or ""))


def _upload_grid(company_id, period):
    """CVs accepted in the period by weekday (Monday first) and hour: seven rows of 24."""
    grid = [[0] * HOURS for _ in range(WEEKDAYS)]
    accepted = (
        CvUsage.objects.filter(company_id=company_id, period=period)
        .annotate(
            weekday=ExtractIsoWeekDay("accepted_at", tzinfo=UTC),
            hour=ExtractHour("accepted_at", tzinfo=UTC),
        )
        .values("weekday", "hour")
        .annotate(total=Count("id"))
    )
    for row in accepted:
        grid[row["weekday"] - 1][row["hour"]] = row["total"]
    return grid


def usage_report(company_id, raw_period=None):
    shown = get_setting("usage.history_periods")
    periods = list(UsagePeriod.objects.filter(company_id=company_id).order_by("-start")[:shown])
    counters = {period.pk: [] for period in periods}
    for counter in UsageCounter.objects.filter(company_id=company_id, period__in=periods):
        counters[counter.period_id].append(counter)
    chosen = _checked_period(periods, raw_period)
    return {
        "periods": [
            {
                "id": str(period.pk),
                "start": period.start.isoformat(),
                "end": period.end.isoformat(),
                **_figures(counters[period.pk]),
            }
            for period in periods
        ],
        "selected": str(chosen.pk) if chosen else None,
        "projects": _projects(company_id, counters[chosen.pk]) if chosen else [],
        "uploads": _upload_grid(company_id, chosen) if chosen else [],
    }
