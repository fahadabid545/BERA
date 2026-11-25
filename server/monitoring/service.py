"""The health check run every few minutes: measure, count how many times in a row each limit was
exceeded, alert the super admins, and send the heartbeat ping only if everything is fine."""

import logging

from django.conf import settings

from audit.alerts import alert_admins
from audit.service import record
from platform_settings.service import get_setting

from .checks import ACTS_AT_ONCE, take_all
from .errors import forget_old_counts
from .heartbeat import ping
from .models import CheckStreak

logger = logging.getLogger(__name__)


def _streak(name, over):
    row, _ = CheckStreak.objects.get_or_create(name=name)
    row.consecutive = row.consecutive + 1 if over else 0
    row.save()
    return row.consecutive


def _alert(measurement, streak, needed):
    """One audit entry when the limit has been exceeded long enough, and an email now and then
    for as long as it stays exceeded (the alert cooldown spaces them)."""
    if streak == needed:
        record(
            measurement.event,
            details={"value": measurement.value, "limit": measurement.limit},
        )
    alert_admins(measurement.event, f"Now: {measurement.value}{measurement.unit}.")


def run_health_check():
    """Returns (measurements, everything_is_fine). The ping is sent only when nothing is over
    its limit and it went through; a failing check stops the ping, and the outside service
    raises the alarm."""
    forget_old_counts()
    measurements = take_all()
    needed_in_a_row = get_setting("monitor.checks_in_a_row")
    for measurement in measurements:
        streak = _streak(measurement.name, measurement.over)
        needed = 1 if measurement.name in ACTS_AT_ONCE else needed_in_a_row
        if streak >= needed:
            _alert(measurement, streak, needed)
    healthy = not any(measurement.over for measurement in measurements)
    pinged = ping(settings.HEARTBEAT_URL) if healthy else False
    return measurements, healthy and pinged
