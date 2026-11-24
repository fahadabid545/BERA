from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from signin.authentication import AdminAuthentication

from . import service
from .serializers import DataRequestChangeInput, DataRequestListQuery, NewDataRequestInput


class DataRequestView(APIView):
    """Both admin roles handle data requests; every route checks the role itself."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def values(self, serializer_class, data):
        serializer = serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class DataRequestList(DataRequestView):
    def get(self, request):
        require_action(request.user, "data_request.handle")
        query = self.values(DataRequestListQuery, request.query_params)
        return Response(service.list_requests(query.get("status")))

    def post(self, request):
        require_action(request.user, "data_request.handle")
        service.create_request(self.admin(), self.values(NewDataRequestInput, request.data))
        return Response(service.list_requests(), status=201)


class DataRequestDetail(DataRequestView):
    def patch(self, request, id):
        require_action(request.user, "data_request.handle")
        service.update_request(self.admin(), id, self.values(DataRequestChangeInput, request.data))
        return Response(service.list_requests())
