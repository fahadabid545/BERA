"""The measurements the health check takes. Each is a number against a limit from the platform
settings (`monitor.*`); nothing here reads or returns data about people, CVs or companies."""

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from ai import control
from cvs import processing
from cvs.models import CvFile
from emailing.models import OutgoingEmail
from platform_settings.service import get_setting

from . import readings
from .errors import errors_in_the_last

SECONDS_PER_MINUTE = 60


@dataclass(frozen=True)
class Measurement:
    name: str
    event: str  # the audit log kind, listed in audit/events.py and described in audit/alerts.py
    value: int
    limit: int
    unit: str
    over: bool


def _measure(name, event, value, limit, unit):
    return Measurement(name, event, round(value), limit, unit, value > limit)


def disk():
    used = readings.disk_used_percent()
    limit = get_setting("monitor.disk_used_percent_limit")
    return None if used is None else _measure("disk", "monitor.disk_full", used, limit, "% used")


def memory():
    used = readings.memory_used_percent()
    limit = get_setting("monitor.memory_used_percent_limit")
    return (
        None if used is None else _measure("memory", "monitor.memory_low", used, limit, "% in use")
    )


def _due_waiting_jobs(now):
    return CvFile.objects.filter(status=CvFile.Status.WAITING, next_attempt_at__lte=now)


def waiting_jobs(now):
    """Jobs that are due now and still waiting. Work held back because AI is paused on purpose
    is not a problem, so nothing is measured then."""
    if control.is_paused(now):
        return None
    return _measure(
        "jobs_waiting",
        "monitor.jobs_waiting",
        _due_waiting_jobs(now).count(),
        get_setting("monitor.waiting_jobs_limit"),
        " jobs waiting",
    )


def longest_wait(now):
    if control.is_paused(now):
        return None
    oldest = (
        _due_waiting_jobs(now)
        .order_by("next_attempt_at")
        .values_list("next_attempt_at", flat=True)
        .first()
    )
    minutes = (now - oldest).total_seconds() / SECONDS_PER_MINUTE if oldest else 0
    return _measure(
        "job_wait",
        "monitor.job_waiting_too_long",
        minutes,
        get_setting("monitor.job_waiting_minutes_limit"),
        " minutes the longest job has waited",
    )


def stuck_jobs(now):
    stuck = CvFile.objects.filter(
        status__in=(CvFile.Status.READING, CvFile.Status.SCORING),
        started_at__lt=processing.stuck_cutoff(now),
    )
    return _measure(
        "jobs_stuck",
        "monitor.jobs_stuck",
        stuck.count(),
        get_setting("monitor.stuck_jobs_limit"),
        " jobs stuck",
    )


def email_backlog(now):
    cutoff = now - timedelta(minutes=get_setting("monitor.email_queue_minutes"))
    stuck = OutgoingEmail.objects.filter(status=OutgoingEmail.Status.QUEUED, created_at__lt=cutoff)
    return _measure(
        "email_backlog",
        "monitor.emails_backed_up",
        stuck.count(),
        get_setting("monitor.email_backlog_limit"),
        " emails waiting to be sent",
    )


def error_rate(now):
    window = get_setting("monitor.error_window_minutes")
    return _measure(
        "error_rate",
        "monitor.error_rate",
        errors_in_the_last(window),
        get_setting("monitor.error_limit"),
        f" server errors in {window} minutes",
    )


# The error rate is already counted over a time window, so one run over its limit is enough.
ACTS_AT_ONCE = {"error_rate"}


def take_all(now=None):
    now = now or timezone.now()
    taken = [disk(), memory(), waiting_jobs(now), longest_wait(now)]
    taken += [stuck_jobs(now), email_backlog(now), error_rate(now)]
    return [measurement for measurement in taken if measurement is not None]
