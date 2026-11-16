from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.role_matrix import require_action
from core.throttles import live
from signin.authentication import AdminAuthentication

from . import overview


class AdminDashboardView(APIView):
    """Both admin roles may open the overview; what a role may not see (money, AI) is left out
    of the answer, and the routes behind it refuse that role."""

    authentication_classes = [AdminAuthentication]

    def check(self, request):
        require_action(request.user, "usage.view")
        return request.user.role


class AdminDashboard(AdminDashboardView):
    def get_throttles(self):
        return [throttle() for throttle in live()]

    def get(self, request):
        return Response(overview.overview(self.check(request), request.query_params.get("days")))


class AdminDashboardDetail(AdminDashboardView):
    def get(self, request):
        role = self.check(request)
        params = request.query_params
        return Response(
            overview.detail(role, params.get("kind"), params.get("key"), params.get("days"))
        )


class AdminDashboardReport(AdminDashboardView):
    def get(self, request):
        body = overview.report(self.check(request), request.query_params.get("days"))
        if request.query_params.get("as") != "csv":
            return Response(body)
        response = HttpResponse(overview.report_csv(body), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="bera-platform-report-{body["generated_on"]}.csv"'
        )
        return response
