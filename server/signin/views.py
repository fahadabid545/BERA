from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import NotAuthenticated
from rest_framework.response import Response

from core.permissions import PublicAccess
from core.throttles import RefreshThrottle, limited

from . import service
from .cookies import refresh_cookie_name, set_session_cookies
from .csrf import enforce_csrf
from .kinds import ADMIN, COMPANY


def make_refresh_view(kind):
    @api_view(["POST"])
    @authentication_classes([])
    @permission_classes([PublicAccess])  # the refresh token is the credential
    @throttle_classes(limited(RefreshThrottle))
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
