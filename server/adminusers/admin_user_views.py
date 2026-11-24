"""Managing the admin team: super admins only, every route checks its own action. The team list
needs `admin_user.view`; every change needs `admin_user.manage`, a written reason where the audit
log asks for one, and is audited."""

from django.http import Http404
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import PublicAccess
from core.throttles import LoginThrottle, limited
from signin.authentication import AdminAuthentication

from . import admin_accounts, admin_invites
from .admin_user_serializers import (
    AcceptAdminInviteSerializer,
    ChangeRoleSerializer,
    ChangeStatusSerializer,
    InviteAdminSerializer,
)
from .models import AdminUser
from .role_matrix import require_action


def _team():
    return {
        "admins": admin_invites.describe_admins(),
        "invitations": admin_invites.describe_invitations(),
    }


class AdminTeamView(APIView):
    authentication_classes = [AdminAuthentication]

    def me(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def values(self, serializer_class):
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class TeamList(AdminTeamView):
    def get(self, request):
        require_action(request.user, "admin_user.view")
        return Response(_team())


class InviteAdmin(AdminTeamView):
    def post(self, request):
        require_action(request.user, "admin_user.manage")
        values = self.values(InviteAdminSerializer)
        admin_invites.invite_admin(self.me(), **values)
        return Response(_team(), status=201)


class ResendInvite(AdminTeamView):
    def post(self, request, id):
        require_action(request.user, "admin_user.manage")
        if admin_invites.resend_invite(self.me(), id) is None:
            raise Http404
        return Response(_team())


class RevokeInvite(AdminTeamView):
    def post(self, request, id):
        require_action(request.user, "admin_user.manage")
        if admin_invites.revoke_invite(self.me(), id) is None:
            raise Http404
        return Response(_team())


class ChangeRole(AdminTeamView):
    def post(self, request, id):
        require_action(request.user, "admin_user.manage")
        values = self.values(ChangeRoleSerializer)
        target = self._found(id)
        admin_accounts.change_role(target.pk, values["role"], by=self.me(), reason=values["reason"])
        return Response(_team())

    @staticmethod
    def _found(id):
        try:
            return AdminUser.objects.exclude(status=AdminUser.Status.REMOVED).get(pk=id)
        except AdminUser.DoesNotExist:
            raise Http404 from None


class ChangeStatus(ChangeRole):
    def post(self, request, id):
        require_action(request.user, "admin_user.manage")
        values = self.values(ChangeStatusSerializer)
        target = self._found(id)
        admin_accounts.set_status(
            target.pk, values["status"], by=self.me(), reason=values["reason"]
        )
        return Response(_team())


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the single-use secret in the link is the credential
@throttle_classes(limited(LoginThrottle))
def accept_admin_invite(request):
    serializer = AcceptAdminInviteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    admin_invites.accept_invite(values["token"], values["password"])
    return Response({"status": "ok"})
