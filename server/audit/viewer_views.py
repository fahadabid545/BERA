from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from core.throttles import DownloadThrottle, limited
from signin.authentication import AdminAuthentication

from . import log_viewer
from .viewer_serializers import AuditFilters, AuditPageQuery


class AuditView(APIView):
    """Super admins only; the route checks its own action."""

    authentication_classes = [AdminAuthentication]

    def checked(self, serializer_class):
        require_action(self.request.user, "audit_log.view")
        serializer = serializer_class(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        return dict(serializer.validated_data)


class AuditLog(AuditView):
    def get(self, request):
        filters = self.checked(AuditPageQuery)
        cursor = filters.pop("cursor", None)
        return Response(log_viewer.page(filters, cursor))


class AuditLogExport(AuditView):
    def get_throttles(self):
        return [throttle() for throttle in limited(DownloadThrottle)]

    def get(self, request):
        filters = self.checked(AuditFilters)
        admin = AdminUser.objects.get(pk=request.user.user_id)
        rows = log_viewer.export(admin, filters)
        response = StreamingHttpResponse(rows, content_type="text/csv; charset=utf-8")
        day = timezone.now().strftime("%Y-%m-%d")
        response["Content-Disposition"] = f'attachment; filename="audit-log-{day}.csv"'
        return response
