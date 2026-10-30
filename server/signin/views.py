from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import NotAuthenticated
from rest_framework.response import Response

from core import request_context
from core.permissions import PublicAccess
from core.throttles import LoginThrottle, RefreshThrottle, limited

from . import service
from .cookies import refresh_cookie_name, set_session_cookies
from .csrf import enforce_csrf
from .kinds import ADMIN, COMPANY
from .login import check_login
from .serializers import LoginSerializer


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


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the password is the credential
@throttle_classes(limited(LoginThrottle))
def login_company(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    person = check_login(**serializer.validated_data)
    request_context.bind_actor(person.pk, person.company_id)
    # Every sign-in is its own session, so a second device never signs out the first.
    issued = service.start_session(
        user_id=person.pk, role=person.role, company_id=person.company_id, kind=COMPANY
    )
    response = Response({"status": "ok"})  # the tokens travel only in cookies
    set_session_cookies(response, COMPANY, issued)
    return response
