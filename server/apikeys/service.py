"""Making, listing and revoking keys. Only the owner does any of it (see the views)."""

from django.db import transaction
from django.utils import timezone

from audit.service import record
from companies.models import Company
from core.errors import AppError, not_found
from platform_settings.service import get_setting

from . import access, keys
from .models import ApiKey

TOO_MANY_CODE = "too_many_api_keys"


def describe(key):
    return {
        "id": str(key.pk),
        "name": key.name,
        "last_four": key.last_four,
        "scopes": key.scopes,
        "created_at": key.created_at.isoformat(),
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "request_count": key.request_count,
    }


def list_keys(company_id):
    return [describe(key) for key in ApiKey.objects.filter(company_id=company_id)]


def create_key(owner, name, scopes, expires_at):
    """Returns (the stored key, the key text). The text is not kept anywhere: this is the only
    time it exists."""
    if not access.is_open(owner.company_id, owner.pk):
        raise access.closed_error()
    token = keys.new_token()
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=owner.company_id)  # one at a time per company
        live = ApiKey.objects.filter(company_id=owner.company_id, revoked_at__isnull=True)
        limit = get_setting("api.max_active_keys_per_company")
        if live.count() >= limit:
            raise AppError(
                TOO_MANY_CODE,
                f"A company may have at most {limit} active API keys. Revoke one first.",
                status_code=409,
            )
        key = ApiKey.objects.create(
            company_id=owner.company_id,
            created_by=owner,
            name=name,
            key_hash=keys.hash_of(token),
            last_four=token[-4:],
            scopes=sorted(scopes),
            expires_at=expires_at,
        )
        record(
            "api_key.created",
            actor=owner,
            details={"credential": str(key.pk), "scopes": ",".join(key.scopes)},
        )
    return key, token


def revoke_key(owner, key_id):
    """Takes effect at once, because every request looks the key up again. Revoking a key that
    is already revoked changes nothing."""
    with transaction.atomic():
        key = (
            ApiKey.objects.select_for_update()
            .filter(company_id=owner.company_id, pk=key_id)
            .first()
        )
        if key is None:
            raise not_found()
        if key.revoked_at is None:
            key.revoked_at = timezone.now()
            key.save(update_fields=["revoked_at"])
            record("api_key.revoked", actor=owner, details={"credential": str(key.pk)})
    return key
