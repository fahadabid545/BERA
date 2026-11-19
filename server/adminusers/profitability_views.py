"""Cost versus revenue for super admins: the figures, and the PKR to USD rate they use."""

from rest_framework.response import Response

from adminusers import profitability
from adminusers.control_serializers import PkrRateSerializer
from adminusers.control_views import ControlView
from adminusers.role_matrix import require_action


class CostVersusRevenue(ControlView):
    action = "payment.view"

    def get(self, request):
        require_action(request.user, self.action)
        return Response(profitability.cost_versus_revenue(request.query_params))


class PkrRate(ControlView):
    action = "settings.change"

    def put(self, request):
        values = self.checked(PkrRateSerializer)
        rate = profitability.set_rate(
            values["pkr_per_usd"], by=self.admin(), reason=values["reason"]
        )
        return Response({"pkr_per_usd": rate})
