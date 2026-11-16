from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response

from core.permissions import PublicAccess
from core.throttles import limited
from signin.authentication import CompanyAuthentication

from .account import (
    EMAIL_SENT_MESSAGE,
    company_settings,
    confirm_email_change,
    profile,
    rename,
    request_email_change,
    update_company,
)
from .account_serializers import (
    CompanySettingsSerializer,
    ConfirmEmailChangeSerializer,
    EmailChangeSerializer,
    ProfileSerializer,
)
from .models import CompanyUser
from .role_matrix import require_action


def _person(request):
    return CompanyUser.objects.select_related("company").get(pk=request.user.user_id)


@api_view(["GET", "PATCH"])
@authentication_classes([CompanyAuthentication])  # signed-in company users only (IsSignedIn)
@throttle_classes(limited())
def own_profile(request):
    """The signed-in person's own profile; no id is ever taken from the request."""
    person = _person(request)
    if request.method == "GET":
        return Response(profile(person))
    serializer = ProfileSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return Response(rename(person, serializer.validated_data["name"]))


@api_view(["POST"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def own_email_change(request):
    serializer = EmailChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    request_email_change(_person(request), values["current_password"], values["email"])
    return Response({"status": "ok", "message": EMAIL_SENT_MESSAGE})


@api_view(["POST"])
@authentication_classes([])  # the link decides whose email changes, not who is signed in
@permission_classes([PublicAccess])  # the secret in the link is the credential
def confirm_company_email_change(request):
    serializer = ConfirmEmailChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    confirm_email_change(serializer.validated_data["token"])
    return Response({"status": "changed"})


@api_view(["GET", "PATCH"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def company_settings_view(request):
    """The company's name, billing country and how long its activity log is kept. Owner only."""
    require_action(request.user, "settings.change")
    person = _person(request)
    if request.method == "GET":
        return Response(company_settings(person.company))
    serializer = CompanySettingsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return Response(update_company(person, person.company, serializer.validated_data))
