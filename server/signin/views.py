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
from .authentication import AdminAuthentication, CompanyAuthentication
from .cookies import clear_session_cookies, refresh_cookie_name, set_session_cookies
from .csrf import enforce_csrf
from .kinds import ADMIN, COMPANY
from .login import check_login
from .serializers import LoginSerializer
from .service import RevokeReason


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


def make_logout_view(kind):
    @api_view(["POST"])
    @authentication_classes([])
    @permission_classes([PublicAccess])  # the refresh cookie is the credential, so it works even
    @throttle_classes(limited())  # when the short-lived access token has already ended
    def logout(request):
        token = request.COOKIES.get(refresh_cookie_name(kind))
        if token:
            enforce_csrf(request)
            service.end_session_of_refresh_token(token, kind)
        # Always clears the cookies, so signing out twice (or with nothing) is harmless.
        response = Response({"status": "ok"})
        clear_session_cookies(response, kind)
        return response

    logout.__name__ = f"logout_{kind}"
    return logout


def make_logout_all_view(kind, authentication):
    @api_view(["POST"])
    @authentication_classes([authentication])  # signed-in people only; protected by IsSignedIn
    @throttle_classes(limited())
    def logout_all(request):
        service.revoke_user_sessions(request.user.user_id, RevokeReason.LOGOUT_ALL, kind=kind)
        response = Response({"status": "ok"})
        clear_session_cookies(response, kind)
        return response

    logout_all.__name__ = f"logout_all_{kind}"
    return logout_all


logout_company = make_logout_view(COMPANY)
logout_admin = make_logout_view(ADMIN)
logout_all_company = make_logout_all_view(COMPANY, CompanyAuthentication)
logout_all_admin = make_logout_all_view(ADMIN, AdminAuthentication)


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
