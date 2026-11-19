"""The admin's companies list and one company's page. Read-only; both admin roles may open them."""

from rest_framework.response import Response

from adminusers import company_directory
from adminusers.control_views import ControlView, _found
from adminusers.role_matrix import require_action
from companies.models import Company


class CompaniesList(ControlView):
    action = "company.view"

    def get(self, request):
        require_action(request.user, self.action)
        return Response(company_directory.list_companies(request.query_params))


class CompanyPage(ControlView):
    action = "company.view"

    def get(self, request, id):
        require_action(request.user, self.action)
        company = _found(Company, id)
        return Response(company_directory.company_detail(company, request.user.role))
