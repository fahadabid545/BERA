from rest_framework.response import Response

from companies.role_matrix import roles_allowed
from core.throttles import AskThrottle, limited
from projects.models import Project
from signin.company_views import CandidateDataView

from . import service
from .serializers import QuestionInput


class AskAboutProject(CandidateDataView):
    """A question about one project of the user's own company (another company's is "not
    found"). Whoever may see the candidates may ask."""

    queryset = Project.objects.all()

    def get_throttles(self):
        return [throttle() for throttle in limited(AskThrottle)]

    def permitted_roles(self):
        return roles_allowed("candidate.view")

    def post(self, request, id):
        serializer = QuestionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(service.ask(self.get_object(), serializer.validated_data["question"]))
