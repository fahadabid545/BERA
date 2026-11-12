from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response

from core.permissions import PublicAccess
from core.throttles import InviteThrottle, LoginThrottle, OtherRequestsThrottle, limited
from signin.company_views import CompanyObjectView

from .invites import (
    accept_invitation,
    describe_invitations,
    invite_member,
    resend_invitation,
    revoke_invitation,
)
from .models import CompanyUser, Invitation
from .team_serializers import AcceptInviteSerializer, InviteSerializer


class InvitationView(CompanyObjectView):
    """Invitations of the owner's own company. Only the owner may use any of these routes."""

    queryset = Invitation.objects.all()
    required_action = "team.invite"

    def inviter(self):
        return CompanyUser.objects.get(pk=self.request.user.user_id)


class InviteList(InvitationView):
    def get_throttles(self):
        # Sending counts toward the company's hourly invitation limit; reading does not.
        classes = limited(InviteThrottle) if self.request.method == "POST" else limited()
        return [throttle() for throttle in classes]

    def get(self, request):
        self.get_queryset()  # checks the company and the owner's role
        return Response(describe_invitations(request.user.company_id))

    def post(self, request):
        self.get_queryset()
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = invite_member(self.inviter(), serializer.validated_data["email"])
        return Response({"id": str(invitation.id)}, status=status.HTTP_201_CREATED)


class InviteResend(InvitationView):
    throttle_classes = [InviteThrottle, OtherRequestsThrottle]

    def post(self, request, id):
        resend_invitation(self.get_object(), self.inviter())
        return Response({"status": "ok"})


class InviteRevoke(InvitationView):
    def delete(self, request, id):
        revoke_invitation(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the single-use secret in the link is the credential
@throttle_classes(limited(LoginThrottle))
def accept_company_invite(request):
    serializer = AcceptInviteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    accept_invitation(values["token"], values["name"], values["password"])
    return Response({"status": "ok"})
