from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from companies.models import CompanyUser
from companies.role_matrix import roles_allowed
from core.errors import form_error
from core.throttles import UploadThrottle, limited
from projects.models import Project
from signin.company_views import CompanyObjectView

from .service import upload_cvs, upload_rules


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
