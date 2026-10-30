from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import NotAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from core.permissions import PublicAccess
from platform_settings.service import get_setting

from . import service
from .cookies import refresh_cookie_name, set_session_cookies
from .csrf import enforce_csrf
from .kinds import ADMIN, COMPANY


class RefreshRateThrottle(SimpleRateThrottle):
    """Limits renewals per address. Its counts live in each server process's own cache until the
    shared rate limiter exists."""

    scope = "refresh"

    def get_rate(self):
        return f"{get_setting('tokens.refresh_attempts_per_minute')}/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.META.get("REMOTE_ADDR", ""),
        }


def make_refresh_view(kind):
    @api_view(["POST"])
    @authentication_classes([])
    @permission_classes([PublicAccess])  # the refresh token is the credential
    @throttle_classes([RefreshRateThrottle])
    def refresh(request):
        token = request.COOKIES.get(refresh_cookie_name(kind))
        if not token:
            raise NotAuthenticated()
        enforce_csrf(request)
        issued = service.refresh_session(token, kind)
        response = Response({"status": "ok"})  # the tokens travel only in cookies
        set_session_cookies(response, kind, issued)
        return response

    refresh.__name__ = f"refresh_{kind}"
    return refresh


refresh_company = make_refresh_view(COMPANY)
refresh_admin = make_refresh_view(ADMIN)
