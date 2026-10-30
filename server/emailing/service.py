"""The one way the product sends system email.

    send_email("verify_email", address, name="Jo", link=build_link(...), expires_in_hours=24)

Sending never raises because of the provider: the email is stored, a background job delivers
it, a failure is retried after the waits in the platform setting `email.retry_waits_seconds`
and finally logged. Only mistakes in the calling code (see rendering.py) raise.
"""

import logging
import smtplib
from datetime import timedelta

from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import DatabaseError, transaction
from django.utils import timezone
from django_q.models import Schedule
from django_q.tasks import async_task, schedule

from core.jobs import logged_job
from platform_settings.service import get_setting

from .models import BouncedAddress, OutgoingEmail
from .rendering import render_email

logger = logging.getLogger(__name__)

DELIVER_JOB = "emailing.service.deliver_email"
FROM_NAME = "Bera"


def send_email(template_name, to_address, *, now=False, **values):
    """Queue one email (or, with `now=True`, deliver it before returning).

    Returns the stored email, or None if even storing it failed, which is logged."""
    subject, text_body, html_body = render_email(template_name, values)
    try:
        with transaction.atomic():
            email = OutgoingEmail.objects.create(
                template=template_name,
                to_address=to_address,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )
    except DatabaseError as error:
        logger.error("Could not store a %s email (%s).", template_name, type(error).__name__)
        return None
    if now:
        deliver_email(str(email.id))
        email.refresh_from_db()
    else:
        # After the surrounding action is saved, so a rolled-back action sends nothing.
        transaction.on_commit(lambda: _queue_delivery(email.id))
    return email


def _queue_delivery(email_id):
    try:
        async_task(DELIVER_JOB, str(email_id))
    except Exception as error:  # the queue is down; the user's action must still succeed
        logger.error("Could not queue email %s (%s).", email_id, type(error).__name__)


def is_suppressed(address):
    return BouncedAddress.objects.filter(address_lookup=address).exists()


def record_bounce(address, kind):
    """Called when the provider reports a bounce or complaint. Later sends to it are skipped."""
    BouncedAddress.objects.get_or_create(
        address_lookup=address, defaults={"address": address, "kind": kind}
    )


@logged_job
def deliver_email(email_id):
    with transaction.atomic():
        email = (
            OutgoingEmail.objects.select_for_update()
            .filter(pk=email_id, status=OutgoingEmail.Status.QUEUED)
            .first()
        )
        if email is None:  # already handled (a repeated job)
            return
        if is_suppressed(email.to_address):
            _finish(email, OutgoingEmail.Status.SUPPRESSED)
            return
        try:
            _send_through_provider(email)
        except smtplib.SMTPRecipientsRefused as error:
            # The provider says this address cannot receive mail: a bounce. Retrying is useless.
            record_bounce(email.to_address, BouncedAddress.Kind.HARD_BOUNCE)
            _finish(email, OutgoingEmail.Status.FAILED, error)
        except (smtplib.SMTPException, OSError) as error:
            _retry_or_give_up(email, error)
        else:
            _finish(email, OutgoingEmail.Status.SENT)


def _send_through_provider(email):
    message = EmailMultiAlternatives(
        subject=email.subject,
        body=email.text_body,
        to=[email.to_address],
        headers={"X-Bera-Template": email.template},
        connection=get_connection(),
    )
    message.attach_alternative(email.html_body, "text/html")
    message.send(fail_silently=False)


def _retry_or_give_up(email, error):
    waits = get_setting("email.retry_waits_seconds")
    email.attempts += 1
    email.last_error = type(error).__name__
    if email.attempts > len(waits):
        logger.error(
            "Email %s (%s) was not sent after %s attempts (%s).",
            email.id,
            email.template,
            email.attempts,
            email.last_error,
        )
        _finish(email, OutgoingEmail.Status.FAILED)
        return
    wait = waits[email.attempts - 1]
    logger.warning(
        "Email %s attempt %s failed (%s); trying again in %s seconds.",
        email.id,
        email.attempts,
        email.last_error,
        wait,
    )
    email.save(update_fields=["attempts", "last_error"])
    schedule(
        DELIVER_JOB,
        str(email.id),
        name=f"email-retry-{email.id}-{email.attempts}",
        schedule_type=Schedule.ONCE,
        next_run=timezone.now() + timedelta(seconds=wait),
    )


def _finish(email, status, error=None):
    """Record the outcome and wipe the personal data and one-time links."""
    email.status = status
    email.attempts += 1 if status == OutgoingEmail.Status.SENT else 0
    email.last_error = type(error).__name__ if error else email.last_error
    email.finished_at = timezone.now()
    email.to_address = email.subject = email.text_body = email.html_body = ""
    email.save()
