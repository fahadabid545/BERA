import uuid

from django.http import Http404
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from companies.models import CompanyUser
from companies.role_matrix import roles_allowed
from core.errors import form_error
from core.throttles import DownloadThrottle, UploadThrottle, limited
from platform_settings.service import get_setting
from projects.models import Project
from signin.company_views import CandidateDataView, CompanyObjectView

from .comparison import matrix, side_by_side
from .detail import candidate_detail
from .downloads import cv_file_response
from .estimate import confirm, estimate
from .file_checks import check_cv_file, check_name_and_size
from .models import Candidate, CandidateScore, CvFile
from .notes import add_note, change_note, remove_note
from .processing import cancel_unstarted, project_processing, retry_failed
from .ranking import ranked_list
from .service import upload_cvs, upload_rules
from .stages import change_stage
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


class CandidateDetail(CandidateDataView):
    """Everything about one candidate, including the contact details. The candidate must belong
    to this project and company; a deleted one is "not found"."""

    queryset = Candidate.objects.select_related("cv_file", "profile", "contact", "project")
    lookup_url_kwarg = "candidate_id"

    def permitted_roles(self):
        return roles_allowed("candidate.view")

    def get(self, request, id, candidate_id):
        candidate = self.get_object()
        if str(candidate.project_id) != str(id):
            raise Http404
        return Response(candidate_detail(candidate, request.user.user_id))


class CandidateCvFile(CandidateDataView):
    """The candidate's original CV: shown in the page (PDF only) or, with `?download=1`, saved."""

    queryset = Candidate.objects.select_related("cv_file")
    lookup_url_kwarg = "candidate_id"

    def permitted_roles(self):
        return roles_allowed("cv.download")

    def get_throttles(self):
        return [throttle() for throttle in limited(DownloadThrottle)]

    def get(self, request, id, candidate_id):
        candidate = self.get_object()
        if str(candidate.project_id) != str(id):
            raise Http404
        return cv_file_response(
            candidate.cv_file, download=request.query_params.get("download") == "1"
        )


class CandidateStages(CandidateDataView):
    """Moves one candidate or many (`candidate_ids`) of the project to a stage, all or nothing."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("candidate.change_stage")

    def post(self, request, id):
        project = self.get_object()
        return Response(
            change_stage(
                project,
                request.user.user_id,
                request.data.get("candidate_ids"),
                request.data.get("stage"),
            )
        )


class CandidateNotes(CandidateDataView):
    """Adds a note to a candidate of this project."""

    queryset = Candidate.objects.all()
    lookup_url_kwarg = "candidate_id"

    def permitted_roles(self):
        return roles_allowed("candidate.write_note")

    def post(self, request, id, candidate_id):
        candidate = self.get_object()
        if str(candidate.project_id) != str(id):
            raise Http404
        return Response(
            add_note(candidate, request.user.user_id, request.data.get("text")), status=201
        )


class CandidateNoteItem(CandidateDataView):
    """Changes or removes a note; only its author may."""

    queryset = Candidate.objects.all()
    lookup_url_kwarg = "candidate_id"

    def permitted_roles(self):
        return roles_allowed("candidate.write_note")

    def _candidate(self, id):
        candidate = self.get_object()
        if str(candidate.project_id) != str(id):
            raise Http404
        return candidate

    def patch(self, request, id, candidate_id, note_id):
        candidate = self._candidate(id)
        return Response(
            change_note(candidate, request.user.user_id, note_id, request.data.get("text"))
        )

    def delete(self, request, id, candidate_id, note_id):
        remove_note(self._candidate(id), request.user.user_id, note_id)
        return Response(status=204)


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
                "outdated": score.outdated,
                "label": score.label,
                "borderline": score.borderline,
                "strengths": score.strengths,
                "risks": score.risks,
                "interview_questions": score.interview_questions,
                "guide_note": score.guide_note,
            }
        )


class ProjectCandidates(CandidateDataView):
    """The project's candidates, ranked: one sorted page at a time, only this company's."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request, id):
        return Response(ranked_list(self.get_object(), request.query_params))


class CandidateComparison(CandidateDataView):
    """Two to four chosen candidates side by side (`?ids=a,b`)."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("candidate.view")

    def get(self, request, id):
        return Response(side_by_side(self.get_object(), request.query_params))


class CandidateMatrix(CandidateDataView):
    """The filtered candidates against all requirements; takes the candidate list's filters."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("candidate.view")

    def get(self, request, id):
        return Response(matrix(self.get_object(), request.query_params))
