from django.http import Http404, HttpResponse
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from companies.models import CompanyUser
from companies.role_matrix import roles_allowed
from core.errors import form_error
from core.throttles import DownloadThrottle, UploadThrottle, limited, live
from platform_settings.service import get_setting
from projects.models import Project
from signin.company_views import CandidateDataView, CompanyObjectView

from .board import board
from .candidate_deletion import delete_candidate
from .charts import company_charts, project_charts
from .company_candidates import candidates_page
from .comparison import matrix, side_by_side
from .dashboard import dashboard, report_csv
from .dashboard import detail as dashboard_detail
from .dashboard import report as dashboard_report
from .detail import candidate_detail
from .download_packages import (
    describe as describe_package,
)
from .download_packages import (
    package_response,
    request_company_export,
    request_package,
    require_owner,
)
from .downloads import cv_file_response, log_download
from .estimate import confirm, estimate
from .file_checks import check_cv_file, check_name_and_size
from .frontier import frontier
from .list_export import export_response
from .models import Candidate, CandidateScore, CvFile, DownloadPackage
from .notes import add_note, change_note, remove_note
from .processing import cancel_unstarted, project_processing, retry_failed
from .ranking import ranked_list
from .service import batch_id_from, upload_cvs, upload_rules
from .shared_reports import create_report, describe, reports_of, revoke_report
from .stages import change_stage
from .text_reading import CvTextUnreadable, read_text


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
        project = self.get_object()
        return Response(upload_rules(project.company_id, request.user.user_id, project))

    def post(self, request, id):
        project = self.get_object()
        sent = request.FILES.getlist("files")
        if not sent:
            raise form_error({"files": "Choose at least one file."})
        uploader = CompanyUser.objects.get(pk=request.user.user_id)
        files = [(file.name, file.size, file.read) for file in sent]
        batch_id = batch_id_from(request.data.get("batch"))
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

    def get_throttles(self):
        return [throttle() for throttle in live()]

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
        return Response(
            estimate(self.get_object(), batch_id_from(request.query_params.get("batch")))
        )

    def post(self, request, id):
        released = confirm(self.get_object(), batch_id_from(request.data.get("batch")))
        return Response({"confirmed": released})


class CancelUnstarted(CandidateDataView):
    """Skips the CVs that have not started, for the whole project or one upload (`batch`)."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("cv.upload")

    def post(self, request, id):
        project = self.get_object()
        skipped = cancel_unstarted(project, batch_id_from(request.data.get("batch")))
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
        return roles_allowed(
            "candidate.delete" if self.request.method == "DELETE" else "candidate.view"
        )

    def get(self, request, id, candidate_id):
        candidate = self.get_object()
        if str(candidate.project_id) != str(id):
            raise Http404
        return Response(candidate_detail(candidate, request.user.user_id))

    def delete(self, request, id, candidate_id):
        candidate = self.get_object()
        if str(candidate.project_id) != str(id):
            raise Http404
        delete_candidate(candidate, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        download = request.query_params.get("download") == "1"
        response = cv_file_response(candidate.cv_file, download=download)
        if download:  # showing a PDF in the page is not a download
            log_download(request.user, candidate.project_id, "cv", 1)
        return response


class ProjectDownloads(CandidateDataView):
    """Asks for a zip of CVs: those of the chosen candidates (`candidate_ids`) or every CV of the
    project (`all`)."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("cv.download")

    def get_throttles(self):
        return [throttle() for throttle in limited(DownloadThrottle)]

    def post(self, request, id):
        project = self.get_object()
        chosen = (
            None if request.data.get("all") is True else request.data.get("candidate_ids") or []
        )
        return Response(
            describe_package(request_package(project, request.user, chosen)), status=201
        )


class CompanyExport(CandidateDataView):
    """Asks for the whole-company export: a zip of every project's CVs and ranked list. Owner
    only; it is offered before the company is deleted."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("company.export")

    def get_throttles(self):
        return [throttle() for throttle in limited(DownloadThrottle)]

    def post(self, request):
        self.get_queryset()  # checks the company and the role
        return Response(
            describe_package(request_company_export(request.user.company_id, request.user)),
            status=201,
        )


class ProjectListExport(CandidateDataView):
    """The ranked list, with the list's filters and sort, as a spreadsheet or PDF (`?as=`)."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("report.download")

    def get_throttles(self):
        return [throttle() for throttle in limited(DownloadThrottle)]

    def get(self, request, id):
        return export_response(
            self.get_object(), request.user, request.query_params, request.query_params.get("as")
        )


class DownloadPackageStatus(CandidateDataView):
    """How a zip is doing: preparing, ready, failed or expired. Only for the person who asked."""

    queryset = DownloadPackage.objects.all()
    lookup_url_kwarg = "package_id"

    def permitted_roles(self):
        return roles_allowed("cv.download")

    def get_throttles(self):
        return [throttle() for throttle in live()]

    def get(self, request, package_id):
        package = self.get_object()
        require_owner(package, request.user)
        return Response(
            {
                **describe_package(package),
                "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
            }
        )


class DownloadPackageFile(DownloadPackageStatus):
    """The zip itself. The role and the owner are checked on every request."""

    def get_throttles(self):
        return [throttle() for throttle in limited(DownloadThrottle)]

    def get(self, request, package_id):
        package = self.get_object()
        require_owner(package, request.user)
        return package_response(request.user, package)


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

    def get_throttles(self):
        return [throttle() for throttle in live()]

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request, id):
        return Response(ranked_list(self.get_object(), request.query_params))


class ProjectBoard(CandidateDataView):
    """The project's candidates in one column for each stage, only this company's."""

    queryset = Project.objects.all()

    def get_throttles(self):
        return [throttle() for throttle in live()]

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request, id):
        return Response(board(self.get_object(), request.query_params))


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

    def get_throttles(self):
        return [throttle() for throttle in live()]

    def permitted_roles(self):
        return roles_allowed("candidate.view")

    def get(self, request, id):
        return Response(matrix(self.get_object(), request.query_params))


class ProjectFrontier(CandidateDataView):
    """The candidates set against two scores, with the ones nobody beats marked."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("candidate.view")

    def get(self, request, id):
        return Response(frontier(self.get_object(), request.query_params))


class ProjectReports(CandidateDataView):
    """The project's shared report links: list them, or make one for the top candidates."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("report.share")

    def get(self, request, id):
        return Response(reports_of(self.get_object()))

    def post(self, request, id):
        report, token = create_report(
            self.get_object(),
            request.user,
            request.data.get("days"),
            request.data.get("hide_contact"),
        )
        # The token is in this answer and nowhere else; it cannot be looked up again.
        return Response({**describe(report), "token": token}, status=201)


class ProjectReportRevoke(CandidateDataView):
    """Stops a report link at once."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("report.share")

    def post(self, request, id, report_id):
        return Response(revoke_report(self.get_object(), request.user, report_id))


class ProjectCharts(CandidateDataView):
    """The numbers of the project's dashboard charts (`?days=` picks the trend period)."""

    queryset = Project.objects.all()

    def get_throttles(self):
        return [throttle() for throttle in live()]

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request, id):
        return Response(project_charts(self.get_object(), request.query_params.get("days")))


class CompanyDashboard(CandidateDataView):
    """The company dashboard's numbers (`?days=` picks the period)."""

    queryset = Project.objects.all()

    def get_throttles(self):
        return [throttle() for throttle in live()]

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request):
        self.get_queryset()  # checks the role and the company
        return Response(dashboard(request.user.company_id, request.query_params.get("days")))


class CompanyCandidates(CandidateDataView):
    """Every candidate of the company in one list (`?flag=`, filters, sort and page)."""

    queryset = Project.objects.all()

    def get_throttles(self):
        return [throttle() for throttle in live()]

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request):
        self.get_queryset()
        return Response(candidates_page(request.user.company_id, request.query_params))


class CompanyDashboardDetail(CandidateDataView):
    """What is behind one card or mark of the dashboard, for its popup."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request):
        self.get_queryset()
        params = request.query_params
        return Response(
            dashboard_detail(
                request.user.company_id,
                params.get("kind"),
                params.get("key"),
                params.get("days"),
                params.get("project"),
            )
        )


class CompanyDashboardReport(CandidateDataView):
    """The dashboard's numbers as a table: JSON for the printable page, CSV for the file."""

    queryset = Project.objects.all()

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request):
        self.get_queryset()
        data = dashboard_report(request.user.company_id, request.query_params.get("days"))
        if request.query_params.get("as") != "csv":
            return Response(data)
        response = HttpResponse(report_csv(data), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="bera-report-{data["generated_on"]}.csv"'
        )
        return response


class CompanyCharts(CandidateDataView):
    """The numbers of the company dashboard's charts: all the company's projects together."""

    queryset = Project.objects.all()

    def get_throttles(self):
        return [throttle() for throttle in live()]

    def permitted_roles(self):
        return roles_allowed("project.view")

    def get(self, request):
        self.get_queryset()  # checks the role and the company
        return Response(company_charts(request.user.company_id, request.query_params.get("days")))
