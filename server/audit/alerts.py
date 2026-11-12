"""Emailing the active super admins about a security event, at most once per kind per cooldown."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from adminusers.models import AdminUser
from emailing.links import build_link
from emailing.rendering import format_moment
from emailing.service import send_email
from platform_settings.service import get_setting

from .models import AlertState

SECONDS_PER_MINUTE = 60
AUDIT_LOG_PAGE = "/admin/settings/audit-log"
TEST_ALERT = "A test alert, to check that security alerts reach you."

# Plain words for the email; never the details of the event (no names, addresses or tokens).
DESCRIPTIONS = {
    "security.token_reuse": "A sign-in token that had already been used was presented again, "
    "so that session was ended.",
    "security.permission_refused": "Someone who is signed in asked for something their role "
    "may not do.",
    "security.abuse_blocked": "A source was blocked for too many requests or wrong attempts.",
    "security.download_volume": "One user downloaded an unusually large number of CVs in an hour.",
}


def _recipients():
    return list(AdminUser.objects.filter(role=AdminUser.Role.SUPER, status=AdminUser.Status.ACTIVE))


def _claim(kind):
    """True for the one caller that may send now. Safe when requests overlap: only one can
    move `last_sent_at`, or create the row."""
    now = timezone.now()
    cutoff = now - timedelta(minutes=get_setting("security.alert_cooldown_minutes"))
    if AlertState.objects.filter(kind=kind, last_sent_at__lt=cutoff).update(last_sent_at=now):
        return True
    try:
        with transaction.atomic():  # a savepoint, so the caller's own transaction survives
            AlertState.objects.create(kind=kind, last_sent_at=now)
    except IntegrityError:
        return False  # one was sent within the cooldown
    return True


def _send(admins, what):
    when = format_moment(timezone.now())
    for admin in admins:
        send_email(
            "security_alert",
            admin.email,
            name=admin.name,
            what=what,
            when=when,
            link=build_link(AUDIT_LOG_PAGE),
        )


def alert_admins(kind):
    """Emails every active super admin about `kind`, unless that kind was announced within the
    cooldown. With nobody to tell, nothing is sent and the cooldown is not used up."""
    admins = _recipients()
    if admins and _claim(kind):
        _send(admins, DESCRIPTIONS[kind])
        return True
    return False


def send_test_alert():
    """For checking that alerts arrive: goes to every active super admin, whatever the cooldown."""
    admins = _recipients()
    _send(admins, TEST_ALERT)
    return len(admins)
