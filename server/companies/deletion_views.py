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

from .deletion import overview, request_deletion, undo_deletion
from .deletion_serializers import DeleteCompanySerializer, UndoDeletionSerializer
from .models import CompanyUser
from .role_matrix import require_action


@api_view(["GET", "POST"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def delete_company(request):
    """Whether the company has an active subscription (GET), and asking to delete it (POST).
    Owner only; the company is the signed-in person's own, never taken from the request."""
    require_action(request.user, "company.delete")
    if request.method == "GET":
        return Response(overview(request.user.company_id))
    serializer = DeleteCompanySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    owner = CompanyUser.objects.select_related("company").get(pk=request.user.user_id)
    values = serializer.validated_data
    return Response(
        request_deletion(
            owner, owner.company, values["confirm_name"], values["acknowledge_subscription"]
        ),
        status=202,
    )


@api_view(["POST"])
@authentication_classes([])  # the link decides, not who is signed in (nobody can be)
@permission_classes([PublicAccess])  # the secret in the link is the credential
@throttle_classes(limited())
def undo_company_deletion(request):
    serializer = UndoDeletionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    undo_deletion(serializer.validated_data["token"])
    return Response({"status": "restored"})
