from rest_framework.decorators import api_view, authentication_classes, throttle_classes
from rest_framework.decorators import permission_classes as permission_classes_of
from rest_framework.response import Response

from companies.models import Company, CompanyUser
from core import request_context
from core.permissions import PublicAccess
from core.scoping import require_role
from core.throttles import LoginThrottle, limited
from signin.authentication import CompanyAuthentication
from signin.login_session import finish_company_login

from . import service
from .challenge import SETUP, VERIFY, person_of_challenge
from .serializers import (
    ChallengeCodeSerializer,
    ChallengeSerializer,
    CodeSerializer,
    RequirementSerializer,
    TurnOffSerializer,
)

# Routes during login: the signed challenge from the password step is the credential.


def _person_of_login_step(request, serializer_class, purpose):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    person = person_of_challenge(values["challenge"], purpose)
    request_context.bind_actor(person.pk, person.company_id)
    return person, values


@api_view(["POST"])
@authentication_classes([])
@permission_classes_of([PublicAccess])  # the challenge from the password step is the credential
@throttle_classes(limited(LoginThrottle))
def verify_login_code(request):
    person, values = _person_of_login_step(request, ChallengeCodeSerializer, VERIFY)
    service.check_code(person, values["code"])
    return finish_company_login(request, person)


@api_view(["POST"])
@authentication_classes([])
@permission_classes_of([PublicAccess])  # the challenge from the password step is the credential
@throttle_classes(limited(LoginThrottle))
def start_login_setup(request):
    person, _ = _person_of_login_step(request, ChallengeSerializer, SETUP)
    return Response(service.begin_setup(person))


@api_view(["POST"])
@authentication_classes([])
@permission_classes_of([PublicAccess])  # the challenge from the password step is the credential
@throttle_classes(limited(LoginThrottle))
def confirm_login_setup(request):
    person, values = _person_of_login_step(request, ChallengeCodeSerializer, SETUP)
    codes = service.confirm_setup(person, values["code"])
    return finish_company_login(request, person, {"recovery_codes": codes})


# Routes for a signed-in person, on the Security page.


def _signed_in_person(request):
    return CompanyUser.objects.select_related("company").get(pk=request.user.user_id)


@api_view(["GET"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def two_step_status(request):
    return Response(service.status_of(_signed_in_person(request)))


@api_view(["POST"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def start_setup(request):
    return Response(service.begin_setup(_signed_in_person(request)))


@api_view(["POST"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def confirm_setup(request):
    serializer = CodeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    codes = service.confirm_setup(_signed_in_person(request), serializer.validated_data["code"])
    return Response({"recovery_codes": codes})


@api_view(["POST"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def turn_off(request):
    serializer = TurnOffSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    service.turn_off(_signed_in_person(request), values["password"], values["code"])
    return Response({"status": "ok"})


@api_view(["PUT"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def set_company_requirement(request):
    require_role(request.user, {CompanyUser.Role.OWNER})
    serializer = RequirementSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    required = serializer.validated_data["required"]
    Company.objects.filter(pk=request.user.company_id).update(require_two_step=required)
    return Response({"required": required})
