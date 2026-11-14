"""Counting what a company uses. Only the server's own work calls these (no route), so a
company can never change its own counters.

Every change locks the company's row first, so parallel uploads are handled one after another
for a company: none is counted twice or missed."""

import calendar
from datetime import UTC
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from companies.models import Company
from plans.subscriptions import get_subscription

from .models import CvUsage, UsageCounter, UsagePeriod

Status = CvUsage.Status


def _month_start(anchor, months):
    """The anchor moved by whole months, keeping its day (shortened in short months)."""
    index = anchor.year * 12 + anchor.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


def _anchor(company_id):
    """Periods start on the day the subscription started (the company's sign-up day if it has
    never had one)."""
    started = get_subscription(company_id).period_start
    return (started or Company.objects.get(pk=company_id).created_at).astimezone(UTC)


def window_for(company_id, moment):
    """(start, end) of the monthly period holding `moment`."""
    anchor = _anchor(company_id)
    months = (moment.year * 12 + moment.month) - (anchor.year * 12 + anchor.month)
    while _month_start(anchor, months) > moment:
        months -= 1
    while _month_start(anchor, months + 1) <= moment:
        months += 1
    return _month_start(anchor, months), _month_start(anchor, months + 1)


def _lock(company_id):
    Company.objects.select_for_update().get(pk=company_id)


def _period_at(company_id, moment):
    """The stored period holding `moment`, created when it is the first thing in it. A period
    never overlaps the one before it (a renewal can move the start day)."""
    existing = UsagePeriod.objects.filter(
        company_id=company_id, start__lte=moment, end__gt=moment
    ).first()
    if existing:
        return existing
    start, end = window_for(company_id, moment)
    earlier = UsagePeriod.objects.filter(company_id=company_id, end__lte=moment).order_by("-end")
    last = earlier.first()
    if last and last.end > start:
        start = last.end
    return UsagePeriod.objects.create(company_id=company_id, start=start, end=end)


def _counter(period, project_id):
    counter, _ = UsageCounter.objects.get_or_create(
        company_id=period.company_id, period=period, project_id=project_id
    )
    return counter


def accept_cv(company_id, cv_id, project_id=None, *, now=None):
    """A file was accepted for scoring. This fixes the period it counts in. Calling it again
    for the same CV changes nothing. It does not count the CV: only `mark_scored` does."""
    now = now or timezone.now()
    with transaction.atomic():
        _lock(company_id)
        existing = CvUsage.objects.filter(company_id=company_id, cv_id=cv_id).first()
        if existing:
            return existing
        return CvUsage.objects.create(
            company_id=company_id,
            cv_id=cv_id,
            project_id=project_id,
            period=_period_at(company_id, now),
            accepted_at=now,
        )


def mark_scored(company_id, cv_id):
    """The CV was scored successfully: counts it once, in the period it was accepted in.
    Returns whether it was counted now (False for re-scoring)."""
    with transaction.atomic():
        _lock(company_id)
        entry = CvUsage.objects.select_related("period").get(company_id=company_id, cv_id=cv_id)
        if entry.status == Status.SCORED:
            return False
        entry.status = Status.SCORED
        entry.save(update_fields=["status"])
        counter = _counter(entry.period, entry.project_id)
        UsageCounter.objects.filter(pk=counter.pk).update(cvs_scored=F("cvs_scored") + 1)
        return True


def mark_failed(company_id, cv_id):
    """Reading or scoring failed for good: the CV is never counted. A CV already counted stays
    counted (a later failed re-scoring does not take it back)."""
    with transaction.atomic():
        _lock(company_id)
        entry = CvUsage.objects.get(company_id=company_id, cv_id=cv_id)
        if entry.status != Status.PENDING:
            return False
        entry.status = Status.FAILED
        entry.save(update_fields=["status"])
        return True


def reopen_cv(company_id, cv_id):
    """A failed CV is tried again: it waits (and counts as waiting) once more. The caller has
    checked that the month has room. Returns whether it was reopened."""
    with transaction.atomic():
        _lock(company_id)
        entry = CvUsage.objects.get(company_id=company_id, cv_id=cv_id)
        if entry.status != Status.FAILED:
            return False
        entry.status = Status.PENDING
        entry.save(update_fields=["status"])
        return True


def add_tokens(
    company_id, tokens_in, tokens_out, estimated_cost, *, cv_id=None, project_id=None, now=None
):
    """Adds the tokens and estimated cost of one AI call (re-scoring included). Work on a CV
    always counts in the period the CV was accepted in, whenever the call ran. Work with no CV
    counts in the period holding `now`."""
    cost = Decimal(estimated_cost)
    if min(tokens_in, tokens_out) < 0 or cost < 0:
        raise ValueError("Usage cannot be negative.")
    with transaction.atomic():
        _lock(company_id)
        if cv_id is not None:
            entry = CvUsage.objects.select_related("period").get(company_id=company_id, cv_id=cv_id)
            period, project_id = entry.period, entry.project_id
        else:
            period = _period_at(company_id, now or timezone.now())
        counter = _counter(period, project_id)
        UsageCounter.objects.filter(pk=counter.pk).update(
            tokens_in=F("tokens_in") + tokens_in,
            tokens_out=F("tokens_out") + tokens_out,
            estimated_cost=F("estimated_cost") + cost,
        )


def waiting_cvs(company_id):
    """CVs accepted and not yet scored or failed (the monthly limit counts them too)."""
    return CvUsage.objects.filter(company_id=company_id, status=Status.PENDING).count()


def _totals(counters):
    totals = {"cvs_scored": 0, "tokens_in": 0, "tokens_out": 0, "estimated_cost": Decimal(0)}
    for counter in counters:
        for name in totals:
            totals[name] += getattr(counter, name)
    return totals


def usage_of_period(company_id, period):
    counters = list(UsageCounter.objects.filter(company_id=company_id, period=period))
    return {
        "period_start": period.start,
        "period_end": period.end,
        **_totals(counters),
        "projects": {str(c.project_id): _totals([c]) for c in counters if c.project_id},
    }


def current_usage(company_id, now=None):
    """What the company used in the period now (zeros when nothing happened yet). Reading
    creates nothing."""
    now = now or timezone.now()
    period = UsagePeriod.objects.filter(company_id=company_id, start__lte=now, end__gt=now).first()
    if period:
        return usage_of_period(company_id, period)
    start, end = window_for(company_id, now)
    return {
        "period_start": start,
        "period_end": end,
        **_totals([]),
        "projects": {},
    }


def usage_history(company_id):
    """Every period that has usage, newest first."""
    periods = UsagePeriod.objects.filter(company_id=company_id).order_by("-start")
    return [usage_of_period(company_id, period) for period in periods]
