from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import NotAuthenticated
from rest_framework.response import Response

from companies.models import CompanyUser
from core import request_context
from core.passwords import password_rule_results
from core.permissions import PublicAccess
from core.throttles import LoginThrottle, RefreshThrottle, limited
from twostep.challenge import SETUP, VERIFY, make_challenge

from . import service
from .authentication import AdminAuthentication, CompanyAuthentication
from .cookies import clear_session_cookies, refresh_cookie_name, set_session_cookies
from .csrf import enforce_csrf
from .kinds import ADMIN, COMPANY
from .login import check_login
from .login_session import finish_company_login
from .password_change import change_password
from .serializers import ChangePasswordSerializer, LoginSerializer, PasswordCheckSerializer
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
    # A right password is not enough where two-step is on, or the company requires it: the
    # session only starts after the code (or after setting two-step up).
    if person.two_step_enabled:
        return Response(
            {"status": "two_step_required", "challenge": make_challenge(person, VERIFY)}
        )
    if person.company.require_two_step and person.role == CompanyUser.Role.MEMBER:
        return Response(
            {"status": "two_step_setup_required", "challenge": make_challenge(person, SETUP)}
        )
    return finish_company_login(request, person)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the hints are needed before an account exists
@throttle_classes(limited())
def check_password_rules(request):
    serializer = PasswordCheckSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    rules = password_rule_results(serializer.validated_data["password"])
    return Response({"rules": rules, "ok": all(rule["met"] for rule in rules)})


@api_view(["POST"])
@authentication_classes([CompanyAuthentication])  # signed-in company users only (IsSignedIn)
@throttle_classes(limited())
def change_company_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    person = CompanyUser.objects.get(pk=request.user.user_id)
    values = serializer.validated_data
    change_password(
        person, values["current_password"], values["password"], values["confirm_password"]
    )
    # Every old session ended with the change; this device gets a new one and stays signed in.
    issued = service.start_session(
        user_id=person.pk, role=person.role, company_id=person.company_id, kind=COMPANY
    )
    response = Response({"status": "ok"})
    set_session_cookies(response, COMPANY, issued)
    return response


@api_view(["GET"])
@authentication_classes([CompanyAuthentication])  # signed-in company users only (IsSignedIn)
@throttle_classes(limited())
def company_me(request):
    """Who is signed in, for the panel to show the right name, company and menu."""
    person = CompanyUser.objects.select_related("company").get(pk=request.user.user_id)
    return Response(
        {"name": person.name, "company_name": person.company.name, "role": request.user.role}
    )
