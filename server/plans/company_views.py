from rest_framework.response import Response

from core.throttles import limited, live
from signin.company_views import CompanyObjectView
from usage.report import usage_report

from .models import Subscription
from .summary import plan_and_usage


class PlanAndUsage(CompanyObjectView):
    """The signed-in owner's own company only; no company id is ever taken from the request.
    Read only: a company cannot change its plan or counters from here."""

    queryset = Subscription.objects.all()
    required_action = "billing.view"

    def get_throttles(self):
        return [throttle() for throttle in live()]

    def get(self, request):
        self.get_queryset()  # checks the role and the company
        return Response(plan_and_usage(request.user.company_id))


class UsageHistory(PlanAndUsage):
    """Usage by billing period, by project and by time of upload (`?period=` picks the period).
    Owner only, like the plan figures."""

    def get_throttles(self):
        return [throttle() for throttle in limited()]

    def get(self, request):
        self.get_queryset()  # checks the role and the company
        return Response(usage_report(request.user.company_id, request.query_params.get("period")))
