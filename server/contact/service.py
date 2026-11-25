"""Receiving a contact message: spam is dropped quietly, everything else is stored and emailed
to the support address."""

import logging

from django.db import DatabaseError, transaction

from audit.security import record_security_event
from core.errors import AppError
from emailing.links import build_link
from emailing.service import send_email
from platform_settings.branding import support_email
from platform_settings.service import get_setting

from . import form_token
from .models import ContactMessage

logger = logging.getLogger(__name__)

HONEYPOT = "honeypot"
NOT_SENT = "We could not send your message. Please try again in a few minutes."


def privacy_note():
    return get_setting("contact.privacy_note").format(days=get_setting("contact.retention_days"))


def spam_reason(fields):
    """Why this message looks like spam, or None. Only the reason is ever recorded."""
    if fields.get("website"):
        return HONEYPOT
    return form_token.problem_with(fields.get("form_token", ""))


def receive(fields):
    """Stores the message and queues the email, or drops it. The sender cannot tell the
    difference: both look like a sent message."""
    reason = spam_reason(fields)
    if reason:
        # A number and a reason only, never anything the sender wrote.
        record_security_event("security.contact_spam_dropped", details={"reason": reason})
        return
    try:
        with transaction.atomic():
            ContactMessage.objects.create(
                name=fields["name"], email=fields["email"], message=fields["message"]
            )
            queued = send_email(
                "contact_message",
                support_email(),
                sender_name=fields["name"],
                sender_email=fields["email"],
                message=fields["message"],
                link=build_link("/admin"),
            )
            if queued is None:
                # Nothing reached the support address, so nothing is kept either: the sender
                # is told and tries again, instead of believing it arrived.
                raise AppError("contact_not_sent", NOT_SENT, status_code=503)
    except DatabaseError as error:
        logger.error("A contact message could not be stored (%s).", type(error).__name__)
        raise AppError("contact_not_sent", NOT_SENT, status_code=503) from error
