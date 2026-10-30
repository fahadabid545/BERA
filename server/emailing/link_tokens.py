import secrets
from datetime import timedelta

from django.utils import timezone

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
