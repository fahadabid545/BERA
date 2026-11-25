"""The API (`/api/v1/`). Every route names the scope it needs, works only on the company of
the key, and uses the shared error format. Contact details are never returned: they stay in
the panel."""

from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.errors import AppError, form_error
from core.permissions import IsSignedIn
from core.scoping import get_in_company
from core.throttles import UploadThrottle
from cvs.detail import ats_block, requirement_results, score_block
from cvs.models import Candidate, RequirementResult
from cvs.ranking import ranked_list
from projects.listing import list_projects
from projects.models import Project
from projects.serializers import ListProjectsSerializer

from . import scopes, uploads
from .authentication import ApiKeyAuthentication
from .throttles import ApiKeyThrottle

MISSING_SCOPE = "scope_missing"
RANKED_FIELDS = (
    "id",
    "candidate_id",
    "status",
    "rank",
    "score",
    "grade",
    "outdated",
    "ats_score",
    "label",
    "borderline",
    "stage",
    "top",
    "added_at",
)
SCORE_FIELDS = (
    "score",
    "grade",
    "capped",
    "outdated",
    "must_score",
    "nice_score",
    "label",
    "borderline",
)
REQUIREMENT_FIELDS = (
    "requirement_id",
    "text",
    "kind",
    "weight",
    "verdict",
    "confidence",
    "outdated",
)


def require_scope(principal, scope):
    if scope not in principal.scopes:
        raise AppError(
            MISSING_SCOPE,
            f"This key does not have the scope {scope}.",
            details={"scope": scope},
            status_code=403,
        )


class ApiView(APIView):
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsSignedIn]
    throttle_classes = [ApiKeyThrottle]
    scope = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_scope(request.user, self.scope)

    def project(self, id):
        return get_in_company(Project.objects.all(), self.request.user.company_id, pk=id)


class ProjectList(ApiView):
    scope = scopes.PROJECTS_READ

    def get(self, request):
        query = ListProjectsSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(list_projects(request.user.company_id, **query.validated_data))


class ProjectDetail(ApiView):
    scope = scopes.PROJECTS_READ

    def get(self, request, id):
        project = self.project(id)
        return Response(
            {
                "id": str(project.pk),
                "title": project.title,
                "status": project.status,
                "updated_at": project.updated_at.isoformat(),
            }
        )


class CvUpload(ApiView):
    scope = scopes.CVS_UPLOAD
    parser_classes = [MultiPartParser]

    def get_throttles(self):
        return [ApiKeyThrottle(), UploadThrottle()]

    def post(self, request, id):
        project = self.project(id)
        sent = request.FILES.getlist("files")
        if not sent:
            raise form_error({"files": "Choose at least one file."})
        idempotency_key = uploads.checked_idempotency_key(request.headers.get("Idempotency-Key"))
        body, replayed = uploads.upload(
            request.user, project, sent, request.data.get("batch"), idempotency_key
        )
        response = Response(body)
        if replayed:
            response["Idempotent-Replay"] = "true"
        return response


class Candidates(ApiView):
    scope = scopes.CANDIDATES_READ

    def get(self, request, id):
        page = ranked_list(self.project(id), request.query_params)
        return Response(
            {
                **{name: page[name] for name in ("sort", "direction", "page", "pages", "count")},
                "page_size": page["page_size"],
                "rows": [{name: row[name] for name in RANKED_FIELDS} for row in page["rows"]],
            }
        )


class CandidateDetail(ApiView):
    scope = scopes.CANDIDATES_READ

    def get(self, request, id, candidate_id):
        project = self.project(id)
        candidate = get_in_company(
            Candidate.objects.select_related("cv_file"),
            request.user.company_id,
            pk=candidate_id,
            project_id=project.pk,
        )
        score = score_block(candidate)
        ats = ats_block(candidate)
        results = list(RequirementResult.objects.filter(candidate=candidate))
        return Response(
            {
                "id": str(candidate.pk),
                "status": candidate.cv_file.status,
                "stage": candidate.stage,
                "added_at": candidate.created_at.isoformat(),
                "score": score and {name: score[name] for name in SCORE_FIELDS},
                "ats_score": ats and ats["score"],
                "requirements": [
                    {name: entry[name] for name in REQUIREMENT_FIELDS}
                    for entry in requirement_results(candidate, results)
                ],
            }
        )
