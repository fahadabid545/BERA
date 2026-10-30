import secrets
from datetime import timedelta

from django.utils import timezone

from core.errors import AppError
from signin.tokens import hash_token

from .models import LinkToken

TOKEN_BYTES = 32


def issue_link_token(purpose, subject_id, lifetime_hours):
    """A new link secret. The returned text goes into the email and nowhere else; only its
    hash is stored."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    LinkToken.objects.create(
        purpose=purpose,
        subject_id=subject_id,
        token_hash=hash_token(token),
        expires_at=timezone.now() + timedelta(hours=lifetime_hours),
    )
    return token


def link_refusal(code, message):
    return AppError(code, message, status_code=400)


def consume_link_token(token, purpose):
    """Uses a link secret once and returns who it was for.

    Every cause of refusal is a clear message: a made-up secret, one meant for something else
    (a reset link cannot verify an email), one used already, one past its time. The "mark as
    used" step is a single conditional update, so two people clicking at once cannot both win.
    """
    stored = LinkToken.objects.filter(token_hash=hash_token(token), purpose=purpose).first()
    if stored is None:
        raise link_refusal("link_invalid", "This link is not valid.")
    if stored.used_at is not None:
        raise link_refusal("link_used", "This link has already been used.")
    now = timezone.now()
    if stored.expires_at <= now:
        raise link_refusal("link_expired", "This link has expired.")
    won = LinkToken.objects.filter(pk=stored.pk, used_at__isnull=True).update(used_at=now)
    if not won:
        raise link_refusal("link_used", "This link has already been used.")
    return stored.subject_id


def retire_link_tokens(purpose, subject_id):
    """A newer link replaces the older ones: they stop working."""
    LinkToken.objects.filter(purpose=purpose, subject_id=subject_id, used_at__isnull=True).update(
        used_at=timezone.now()
    )
