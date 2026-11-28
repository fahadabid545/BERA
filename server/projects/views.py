from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, throttle_classes
from rest_framework.response import Response

from companies.models import CompanyUser
from companies.role_matrix import require_action, roles_allowed
from core.errors import form_error
from core.throttles import limited
from platform_settings.service import get_setting
from signin.authentication import CompanyAuthentication
from signin.company_views import CompanyObjectView

from .company_defaults import describe as describe_defaults
from .company_defaults import save_defaults
from .deletion import delete_project
from .duplication import duplicate_project
from .extraction import suggest_requirements
from .factor_settings import describe as describe_factors
from .factor_settings import save_factor_settings
from .listing import list_projects
from .models import Project
from .ownership import change_project_owner
from .preferences import preferences_of, save_preferences
from .requirements import (
    confirm_requirements,
    list_requirements,
    near_duplicates,
    save_requirements,
    start_rereading,
)
from .rescoring import rescore_everything
from .scoring_settings import describe as describe_scoring
from .scoring_settings import save_scoring_settings
from .serializers import (
    ChangeProjectOwnerSerializer,
    CreateProjectSerializer,
    DeleteProjectSerializer,
    EditProjectSerializer,
    FactorSettingsSerializer,
    ListProjectsSerializer,
    PauseUploadsSerializer,
    PreferencesSerializer,
    RescoreSerializer,
    SaveRequirementsSerializer,
    ScoringDefaultsSerializer,
    ScoringSettingsSerializer,
)
from .service import (
    archive_project,
    create_project,
    restore_project,
    set_uploads_paused,
    update_project,
)


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
        "requirements_status": project.requirements_status,
        "updated_at": project.updated_at.isoformat(),
        # Only so the screen can hide Delete; the server refuses everyone but the owner.
        "may_delete": user.role in roles_allowed("project.delete"),
        "may_change_owner": user.role in roles_allowed("project.change_owner"),
        "owner_id": project.created_by_id,
        "uploads_paused": project.uploads_paused,
        "preferences": preferences_of(project),
    }


def _requirements_body(project, items, warnings):
    """The list with where it stands: `drafting` (the AI is reading), `draft` (to be checked,
    with a notice when the AI could not help) or `confirmed`."""
    return {
        "requirements": items,
        "warnings": warnings,
        "status": project.requirements_status,
        "notice": project.requirements_notice,
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
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


class ProjectDuplicate(ProjectView):
    """A copy of the project with its requirements and settings, and no CVs."""

    def permitted_roles(self):
        return roles_allowed("project.create")

    def post(self, request, id):
        copy = duplicate_project(
            CompanyUser.objects.get(pk=request.user.user_id), self.get_object()
        )
        return Response({"id": str(copy.id)}, status=status.HTTP_201_CREATED)


class ProjectPreferences(ProjectView):
    """How the project's candidates are handled; only what is sent changes."""

    def permitted_roles(self):
        return roles_allowed("project.edit")

    def get(self, request, id):
        return Response(preferences_of(self.get_object()))

    def put(self, request, id):
        serializer = PreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = save_preferences(
            CompanyUser.objects.get(pk=request.user.user_id),
            self.get_object(),
            serializer.validated_data,
        )
        return Response(preferences_of(project))


class ProjectUploads(ProjectView):
    """Pauses or resumes new CV uploads for the project."""

    def permitted_roles(self):
        return roles_allowed("project.edit")

    def put(self, request, id):
        serializer = PauseUploadsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = set_uploads_paused(
            CompanyUser.objects.get(pk=request.user.user_id),
            self.get_object(),
            serializer.validated_data["paused"],
        )
        return Response(describe(changed, request.user))


class ProjectRescore(ProjectView):
    """Scores every CV of the project against every requirement again, after the person has seen
    how many CVs will run and the approximate cost."""

    def permitted_roles(self):
        return roles_allowed("project.edit")

    def post(self, request, id):
        project = self.get_object()
        serializer = RescoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        queued = rescore_everything(
            project.pk, project.company_id, serializer.validated_data["acknowledge_rescoring"]
        )
        return Response({"queued": queued}, status=status.HTTP_202_ACCEPTED)


class ProjectOwner(ProjectView):
    """Hands the project to another active team member (the company's owner decides)."""

    def permitted_roles(self):
        return roles_allowed("project.change_owner")

    def put(self, request, id):
        project = self.get_object()
        serializer = ChangeProjectOwnerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = change_project_owner(
            CompanyUser.objects.get(pk=request.user.user_id),
            project,
            serializer.validated_data["owner_id"],
        )
        return Response(describe(changed, request.user))


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


class ProjectRequirements(ProjectView):
    """The project's requirements, read and saved as one list."""

    def permitted_roles(self):
        return roles_allowed("project.view" if self.request.method == "GET" else "project.edit")

    def get(self, request, id):
        project = self.get_object()
        items = list_requirements(project)
        return Response(_requirements_body(project, items, near_duplicates(items)))

    def put(self, request, id):
        project = self.get_object()
        serializer = SaveRequirementsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        items, warnings = save_requirements(
            project.pk,
            project.company_id,
            values["requirements"],
            acknowledge_rescoring=values["acknowledge_rescoring"],
        )
        project.refresh_from_db()
        return Response(_requirements_body(project, items, warnings))


class ProjectRequirementsConfirm(ProjectView):
    """The person accepts the drafted list as it is, so CVs can be processed."""

    def permitted_roles(self):
        return roles_allowed("project.edit")

    def post(self, request, id):
        project = self.get_object()
        items = confirm_requirements(project.pk, project.company_id)
        project.refresh_from_db()
        return Response(_requirements_body(project, items, near_duplicates(items)))


class ProjectRequirementsReread(ProjectView):
    """Asks the AI to draft the list again while it is still a draft."""

    def permitted_roles(self):
        return roles_allowed("project.edit")

    def post(self, request, id):
        project = self.get_object()
        start_rereading(project.pk, project.company_id)
        project.refresh_from_db()
        return Response(_requirements_body(project, [], []), status=status.HTTP_202_ACCEPTED)


class ProjectScoringSettingsView(ProjectView):
    """The project's scoring settings, read and saved as a whole."""

    def permitted_roles(self):
        return roles_allowed("project.view" if self.request.method == "GET" else "project.edit")

    def get(self, request, id):
        return Response(describe_scoring(self.get_object()))

    def put(self, request, id):
        project = self.get_object()
        serializer = ScoringSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            save_scoring_settings(project.pk, project.company_id, serializer.validated_data)
        )


class ProjectFactorSettingsView(ProjectView):
    """The project's extra scoring factors, read and saved as a whole."""

    def permitted_roles(self):
        return roles_allowed("project.view" if self.request.method == "GET" else "project.edit")

    def get(self, request, id):
        return Response(describe_factors(self.get_object()))

    def put(self, request, id):
        project = self.get_object()
        serializer = FactorSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            save_factor_settings(project.pk, project.company_id, serializer.validated_data)
        )


@api_view(["GET", "PUT"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def company_scoring_defaults(request):
    """What the company's new projects start with. Owner only; it never touches a project that
    already exists."""
    require_action(request.user, "settings.change")
    if request.method == "GET":
        return Response(describe_defaults(request.user.company_id))
    serializer = ScoringDefaultsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return Response(
        save_defaults(
            CompanyUser.objects.get(pk=request.user.user_id),
            request.user.company_id,
            serializer.validated_data,
        )
    )
