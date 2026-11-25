from rest_framework.response import Response

from signin.company_views import CompanyObjectView

from .models import Subscription
from .renewal import cancel_renewal, open_billing_portal, resume_renewal


class RenewalView(CompanyObjectView):
    """The signed-in owner's own company only; no company id or customer id is ever taken from
    the request."""

    queryset = Subscription.objects.all()
    required_action = "billing.pay"
    serializer_class = None


class CancelRenewalView(RenewalView):
    def post(self, request):
        self.get_queryset()  # checks the role and the company
        cancel_renewal(request.user.company_id, by=request.user)
        return Response({"result": "cancelled"})


class ResumeRenewalView(RenewalView):
    def post(self, request):
        self.get_queryset()
        resume_renewal(request.user.company_id, by=request.user)
        return Response({"result": "resumed"})


class BillingPortalView(RenewalView):
    def post(self, request):
        self.get_queryset()
        return Response({"url": open_billing_portal(request.user.company_id, by=request.user)})
