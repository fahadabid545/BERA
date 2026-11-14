import uuid

from django.http import Http404
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from companies.models import CompanyUser
from companies.role_matrix import roles_allowed
from core.errors import form_error
from core.throttles import UploadThrottle, limited
from platform_settings.service import get_setting
from projects.models import Project
from signin.company_views import CandidateDataView, CompanyObjectView

from .estimate import confirm, estimate
from .file_checks import check_cv_file, check_name_and_size
from .models import Candidate, CandidateScore, CvFile
from .processing import cancel_unstarted, project_processing, retry_failed
from .service import upload_cvs, upload_rules
from .text_reading import CvTextUnreadable, read_text


def _batch_id(value):
    """The id the upload area gives to everything dropped together; none, or anything that is
    not an id, means this request is a batch of its own."""
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


class ProjectCvUpload(CandidateDataView):
    """Uploads CVs to a project of the user's own company (another company's is "not found").
    The files arrive as one multipart request; every file gets its own result."""

    queryset = Project.objects.all()
    parser_classes = [MultiPartParser]

    def permitted_roles(self):
        return roles_allowed("cv.upload")

    def get_throttles(self):
        # Sending counts every file toward the company's upload allowance; reading does not.
        classes = limited(UploadThrottle) if self.request.method == "POST" else limited()
        return [throttle() for throttle in classes]

    def get(self, request, id):
        self.get_object()
        return Response(upload_rules())

    def post(self, request, id):
        project = self.get_object()
        sent = request.FILES.getlist("files")
        if not sent:
            raise form_error({"files": "Choose at least one file."})
        uploader = CompanyUser.objects.get(pk=request.user.user_id)
        files = [(file.name, file.size, file.read) for file in sent]
        batch_id = _batch_id(request.data.get("batch"))
        return Response({"results": upload_cvs(uploader, project, files, batch_id)})


class ReadDescriptionFile(CompanyObjectView):
    """Reads the text out of a job description file (PDF or Word) for the Create project form.
    The file goes through File checks and the shared text reading, then is thrown away: it is
    never stored and nothing is counted. The form puts the text in the description box."""

    queryset = Project.objects.all()
    parser_classes = [MultiPartParser]

    def permitted_roles(self):
        return roles_allowed("project.create")

    def get_throttles(self):
        return [throttle() for throttle in limited(UploadThrottle)]

    def post(self, request):
        self.get_queryset()  # checks the company and the role
        chosen = request.FILES.getlist("files")
        if len(chosen) != 1:
            raise form_error({"file": "Choose one file."})
        sent = chosen[0]
        if problem := check_name_and_size(sent.name, sent.size):
            raise form_error({"file": problem.message})
        data = sent.read()
        checked = check_cv_file(sent.name, data)
        if checked.problem:
            raise form_error({"file": checked.problem.message})
        try:
            read = read_text(
                checked.file_type,
                data,
                max_characters=get_setting("projects.description_max_length"),
            )
        except CvTextUnreadable as error:
            raise form_error({"file": error.message}) from error
        return Response({"text": read.text, "trimmed": read.trimmed, "notice": checked.notice})


class ProjectProcessing(CandidateDataView):
    """What the project page shows about its CVs: counts per status and each CV's status."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request, id):
        return Response(project_processing(self.get_object()))


class CostEstimate(CandidateDataView):
    """The estimate for the project's CVs held for confirmation, and the confirmation itself.
    `batch` limits both to one upload."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("cv.upload")

    def get(self, request, id):
        return Response(estimate(self.get_object(), _batch_id(request.query_params.get("batch"))))

    def post(self, request, id):
        released = confirm(self.get_object(), _batch_id(request.data.get("batch")))
        return Response({"confirmed": released})


class CancelUnstarted(CandidateDataView):
    """Skips the CVs that have not started, for the whole project or one upload (`batch`)."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("cv.upload")

    def post(self, request, id):
        project = self.get_object()
        skipped = cancel_unstarted(project, _batch_id(request.data.get("batch")))
        return Response({"skipped": skipped})


class RetryFailedCv(CandidateDataView):
    """Puts one failed CV back in line. The CV must belong to this project and company."""

    queryset = CvFile.objects.all()
    lookup_url_kwarg = "cv_id"

    def permitted_roles(self):
        return roles_allowed("cv.upload")

    def post(self, request, id, cv_id):
        cv_file = self.get_object()
        if str(cv_file.project_id) != str(id):
            raise Http404
        retry_failed(cv_file)
        return Response({"status": CvFile.Status.WAITING})


class CandidateRecommendation(CandidateDataView):
    """The score, grade, label and insights of one candidate. The candidate must belong to this
    project and company, and must have been scored."""

    queryset = Candidate.objects.all()
    lookup_url_kwarg = "candidate_id"

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request, id, candidate_id):
        candidate = self.get_object()
        if str(candidate.project_id) != str(id):
            raise Http404
        score = CandidateScore.objects.filter(candidate=candidate).first()
        if score is None:
            raise Http404
        return Response(
            {
                "score": f"{score.score:.1f}",
                "grade": score.grade,
                "capped": score.capped,
                "label": score.label,
                "borderline": score.borderline,
                "strengths": score.strengths,
                "risks": score.risks,
                "interview_questions": score.interview_questions,
                "guide_note": score.guide_note,
            }
        )
