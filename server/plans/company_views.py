from rest_framework.response import Response

from signin.company_views import CompanyObjectView

from .models import Subscription
from .summary import plan_and_usage


class PlanAndUsage(CompanyObjectView):
    """The signed-in owner's own company only; no company id is ever taken from the request.
    Read only: a company cannot change its plan or counters from here."""

    queryset = Subscription.objects.all()
    required_action = "billing.view"

    def get(self, request):
        self.get_queryset()  # checks the role and the company
        return Response(plan_and_usage(request.user.company_id))
