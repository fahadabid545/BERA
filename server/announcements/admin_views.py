from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from signin.authentication import AdminAuthentication

from . import service
from .serializers import AnnouncementInput, NewAnnouncementInput


class AnnouncementView(APIView):
    """Both roles may read; only a super admin may write. Every method checks its own action,
    so a hidden button is never what keeps support out."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def values(self, serializer_class):
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class AnnouncementList(AnnouncementView):
    def get(self, request):
        require_action(request.user, "announcement.read")
        return Response(service.list_for_admin())

    def post(self, request):
        require_action(request.user, "announcement.create")
        service.create_announcement(self.admin(), self.values(NewAnnouncementInput))
        return Response(service.list_for_admin(), status=201)


class AnnouncementDetail(AnnouncementView):
    def put(self, request, id):
        require_action(request.user, "announcement.edit")
        service.update_announcement(self.admin(), id, self.values(AnnouncementInput))
        return Response(service.list_for_admin())

    def delete(self, request, id):
        require_action(request.user, "announcement.delete")
        service.delete_announcement(self.admin(), id)
        return Response(service.list_for_admin())
