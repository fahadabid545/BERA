from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from signin.authentication import AdminAuthentication

from . import tickets
from .serializers import AdminTicketInput, AdminTicketQuery


class SupportAdminView(APIView):
    """Both admin roles work through tickets; every route checks the role."""

    authentication_classes = [AdminAuthentication]

    def values(self, serializer_class, data):
        serializer = serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class TicketList(SupportAdminView):
    def get(self, request):
        require_action(request.user, "support.handle")
        return Response(tickets.list_for_admin(self.values(AdminTicketQuery, request.query_params)))


class TicketDetail(SupportAdminView):
    def get(self, request, id):
        require_action(request.user, "support.handle")
        return Response(tickets.detail_of(tickets.get_for_admin(id), for_admin=True))

    def patch(self, request, id):
        require_action(request.user, "support.handle")
        admin = AdminUser.objects.get(pk=request.user.user_id)
        ticket = tickets.admin_updates(admin, id, self.values(AdminTicketInput, request.data))
        return Response(tickets.detail_of(ticket, for_admin=True))
