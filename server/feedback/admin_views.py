from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from signin.authentication import AdminAuthentication

from . import service
from .serializers import FeedbackChangeInput, FeedbackListQuery


class FeedbackView(APIView):
    """Both admin roles read feedback and change its status; every route checks the role."""

    authentication_classes = [AdminAuthentication]

    def values(self, serializer_class, data):
        serializer = serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class FeedbackList(FeedbackView):
    def get(self, request):
        require_action(request.user, "feedback.handle")
        return Response(service.list_feedback(self.values(FeedbackListQuery, request.query_params)))


class FeedbackDetail(FeedbackView):
    def patch(self, request, id):
        require_action(request.user, "feedback.handle")
        admin = AdminUser.objects.get(pk=request.user.user_id)
        feedback = service.update_feedback(
            admin, id, self.values(FeedbackChangeInput, request.data)
        )
        return Response(service.item_of(feedback))
