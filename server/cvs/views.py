from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from companies.models import CompanyUser
from companies.role_matrix import roles_allowed
from core.errors import form_error
from core.throttles import UploadThrottle, limited
from platform_settings.service import get_setting
from projects.models import Project
from signin.company_views import CompanyObjectView

from .file_checks import check_cv_file, check_name_and_size
from .service import upload_cvs, upload_rules
from .text_reading import CvTextUnreadable, read_text


class ProjectCvUpload(CompanyObjectView):
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
        return Response({"results": upload_cvs(uploader, project, files)})


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
