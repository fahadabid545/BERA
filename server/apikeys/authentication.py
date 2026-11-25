"""Signs a request in with an API key (`Authorization: Bearer bera_live_...`).

Looks the key up again on every request, so a revoked or expired key, a suspended company or an
ended subscription stops it at once. Everything unknown, revoked or expired gets the same "not
signed in" answer; only a valid key of a company that no longer qualifies is told why. A key is
never written to a log or an audit entry. Wrong keys from one address are limited."""

from django.db.models import F
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import NotAuthenticated

from audit.security import record_security_event
from core import rate_limits, request_context
from core.client_address import client_address
from core.errors import AppError
from signin.authentication import BEARER_PREFIX

from . import access, keys
from .models import ApiKey

KIND = "api"
REFUSED_EVENT = "security.api_key_refused"


class ApiPrincipal:
    """Who is calling: a key of one company. It is never a person, so it has no role."""

    kind = KIND
    role = None
    is_authenticated = True

    def __init__(self, key):
        self.key_id = str(key.pk)
        self.company_id = key.company_id
        self.uploader_id = key.created_by_id  # the person whose upload limits the key shares
        self.scopes = frozenset(key.scopes)
        self.user_id = None


def _refuse(request, why, company_id=None):
    """Counts the failure against the address and records it (never the key itself)."""
    wait = rate_limits.hit(rate_limits.API_KEY_FAILURES, f"address:{client_address(request)}")
    if wait:
        raise AppError("rate_limited", rate_limits.try_again_message(wait), status_code=429)
    record_security_event(REFUSED_EVENT, company_id=company_id, details={"why": why})
    raise NotAuthenticated()


class ApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request)
        if not header:
            return None  # IsSignedIn gives the "not signed in" answer
        if not header.lower().startswith(BEARER_PREFIX):
            raise NotAuthenticated()
        token = header[len(BEARER_PREFIX) :].decode("latin-1").strip()
        if not token.startswith(keys.PREFIX):
            _refuse(request, "wrong_kind")
        key = ApiKey.objects.filter(key_hash=keys.hash_of(token)).first()
        if key is None:
            _refuse(request, "unknown")
        now = timezone.now()
        if key.revoked_at is not None:
            _refuse(request, "revoked", key.company_id)
        if key.expires_at is not None and key.expires_at <= now:
            _refuse(request, "expired", key.company_id)
        if not access.is_open(key.company_id, key.created_by_id):
            record_security_event(
                REFUSED_EVENT, company_id=key.company_id, details={"why": "access_closed"}
            )
            raise access.closed_error()
        ApiKey.objects.filter(pk=key.pk).update(
            request_count=F("request_count") + 1, last_used_at=now
        )
        request_context.bind_actor(None, key.company_id)
        return ApiPrincipal(key), None

    def authenticate_header(self, request):
        return "Bearer"
