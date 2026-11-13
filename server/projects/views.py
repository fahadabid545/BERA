from rest_framework import status
from rest_framework.response import Response

from companies.models import CompanyUser
from signin.company_views import CompanyObjectView

from .models import Project
from .serializers import CreateProjectSerializer
from .service import create_project


class ProjectList(CompanyObjectView):
    """Projects of the signed-in user's own company; the company is never taken from the
    request."""

    queryset = Project.objects.all()
    required_action = "project.create"

    def post(self, request):
        self.get_queryset()  # checks the company and the role
        serializer = CreateProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        project = create_project(
            CompanyUser.objects.get(pk=request.user.user_id),
            values["title"],
            values["job_description"],
            acknowledge_warnings=values["acknowledge_warnings"],
        )
        return Response({"id": str(project.id)}, status=status.HTTP_201_CREATED)
