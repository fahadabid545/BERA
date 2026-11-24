from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from core.permissions import PublicAccess
from signin.authentication import AdminAuthentication

from . import admin_settings, branding, maintenance
from .serializers import MaintenanceInput, SaveSettings, SettingsQuery


class SettingsView(APIView):
    """Super admins only: every route checks its own action, so a hidden page is never what keeps
    anyone out."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def values(self, serializer_class, data):
        serializer = serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class SettingsList(SettingsView):
    def get(self, request):
        require_action(request.user, "settings.view")
        query = self.values(SettingsQuery, request.query_params)
        return Response(admin_settings.list_settings(query.get("page")))

    def put(self, request):
        require_action(request.user, "settings.change")
        values = self.values(SaveSettings, request.data)["values"]
        admin_settings.update_settings(self.admin(), values)
        return Response(admin_settings.list_settings())


class SettingReset(SettingsView):
    def post(self, request, key):
        require_action(request.user, "settings.change")
        admin_settings.reset_setting(self.admin(), key)
        return Response(admin_settings.list_settings())


class Maintenance(SettingsView):
    def get(self, request):
        require_action(request.user, "settings.view")
        return Response(admin_settings.maintenance_state())

    def post(self, request):
        require_action(request.user, "settings.change")
        values = self.values(MaintenanceInput, request.data)
        state = admin_settings.set_maintenance(
            self.admin(),
            enabled=values["enabled"],
            message=values.get("message", ""),
            reason=values["reason"],
        )
        return Response(state)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([PublicAccess])
def platform_info(request):
    """What every screen may know, signed in or not: the platform's name, where to get help, and
    whether maintenance mode is on with its message."""
    return Response(
        {
            "app_name": branding.app_name(),
            "support_email": branding.support_email(),
            "maintenance": {"enabled": maintenance.is_on(), "message": maintenance.message()},
        }
    )
