"""The admin sign-in. Both the password and an authenticator code are always needed: the
password step only hands out a signed challenge, and the session starts after the code (or,
for an admin who has not set an authenticator up yet, after setting it up)."""

from rest_framework.decorators import api_view, authentication_classes, throttle_classes
from rest_framework.decorators import permission_classes as permission_classes_of
from rest_framework.response import Response

from core import request_context
from core.permissions import PublicAccess
from core.throttles import LoginThrottle, limited
from signin.kinds import ADMIN
from signin.login_session import finish_admin_login
from signin.serializers import LoginSerializer
from twostep import service
from twostep.challenge import SETUP, VERIFY, make_challenge
from twostep.serializers import ChallengeCodeSerializer, ChallengeSerializer
from twostep.views import person_of_login_step

from .login import check_admin_login


@api_view(["POST"])
@authentication_classes([])
@permission_classes_of([PublicAccess])  # the password is the credential
@throttle_classes(limited(LoginThrottle))
def login_admin(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    admin = check_admin_login(**serializer.validated_data)
    request_context.bind_actor(admin.pk, None)
    if admin.two_step_enabled:
        return Response(
            {"status": "two_step_required", "challenge": make_challenge(admin, VERIFY, ADMIN)}
        )
    return Response(
        {"status": "two_step_setup_required", "challenge": make_challenge(admin, SETUP, ADMIN)}
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes_of([PublicAccess])  # the challenge from the password step is the credential
@throttle_classes(limited(LoginThrottle))
def verify_admin_code(request):
    admin, values = person_of_login_step(request, ChallengeCodeSerializer, VERIFY, ADMIN)
    service.check_code(admin, values["code"])
    return finish_admin_login(admin)


@api_view(["POST"])
@authentication_classes([])
@permission_classes_of([PublicAccess])  # the challenge from the password step is the credential
@throttle_classes(limited(LoginThrottle))
def start_admin_setup(request):
    admin, _ = person_of_login_step(request, ChallengeSerializer, SETUP, ADMIN)
    return Response(service.begin_setup(admin))


@api_view(["POST"])
@authentication_classes([])
@permission_classes_of([PublicAccess])  # the challenge from the password step is the credential
@throttle_classes(limited(LoginThrottle))
def confirm_admin_setup(request):
    admin, values = person_of_login_step(request, ChallengeCodeSerializer, SETUP, ADMIN)
    recovery_codes = service.confirm_setup(admin, values["code"])  # always empty for admins
    response = finish_admin_login(admin)
    response.data["recovery_codes"] = recovery_codes
    return response
