from rest_framework import status
from rest_framework.response import Response

from companies.models import CompanyUser
from companies.role_matrix import roles_allowed
from core.errors import form_error
from signin.company_views import CompanyObjectView

from .deletion import delete_project
from .extraction import suggest_requirements
from .listing import list_projects
from .models import Project
from .serializers import (
    CreateProjectSerializer,
    DeleteProjectSerializer,
    EditProjectSerializer,
    ListProjectsSerializer,
)
from .service import archive_project, create_project, restore_project, update_project


class ProjectList(CompanyObjectView):
    """Projects of the signed-in user's own company; the company is never taken from the
    request."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("project.view" if self.request.method == "GET" else "project.create")

    def get(self, request):
        self.get_queryset()  # checks the company and the role
        serializer = ListProjectsSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(list_projects(request.user.company_id, **serializer.validated_data))

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


ACTION_FOR_METHOD = {
    "GET": "project.view",
    "PATCH": "project.edit",
    "DELETE": "project.delete",
    "POST": "project.archive",
}


def describe(project, user):
    return {
        "id": str(project.id),
        "title": project.title,
        "job_description": project.job_description,
        "status": project.status,
        "updated_at": project.updated_at.isoformat(),
        # Only so the screen can hide Delete; the server refuses everyone but the owner.
        "may_delete": user.role in roles_allowed("project.delete"),
    }


class ProjectView(CompanyObjectView):
    """One project of the user's own company. Another company's project is "not found"."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed(ACTION_FOR_METHOD[self.request.method])


class ProjectDetail(ProjectView):
    def get(self, request, id):
        return Response(describe(self.get_object(), request.user))

    def patch(self, request, id):
        project = self.get_object()
        serializer = EditProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise form_error({"title": "Change the title or the job description."})
        updated = update_project(project.pk, project.company_id, **serializer.validated_data)
        return Response(describe(updated, request.user))

    def delete(self, request, id):
        project = self.get_object()
        serializer = DeleteProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["confirm_title"] != project.title:
            raise form_error({"confirm_title": "Type the project title exactly to confirm."})
        delete_project(CompanyUser.objects.get(pk=request.user.user_id), project)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectArchive(ProjectView):
    def post(self, request, id):
        project = self.get_object()
        return Response(describe(archive_project(project.pk, project.company_id), request.user))


class ProjectRestore(ProjectView):
    def post(self, request, id):
        project = self.get_object()
        return Response(describe(restore_project(project.pk, project.company_id), request.user))


class ProjectRequirementSuggestions(ProjectView):
    """Asks the AI to propose requirements. Nothing is saved: the person edits and confirms."""

    def permitted_roles(self):
        return roles_allowed("project.edit")

    def post(self, request, id):
        return Response(suggest_requirements(self.get_object()))
