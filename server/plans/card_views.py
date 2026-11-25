from rest_framework.response import Response

from .card import card_on_file, check_card_update, open_card_update
from .renewal_views import RenewalView


class CardView(RenewalView):
    def get(self, request):
        self.get_queryset()  # the owner of this company only (billing.pay)
        response = Response({"card": card_on_file(request.user.company_id)})
        response["Cache-Control"] = "no-store"
        return response


class CardUpdateView(RenewalView):
    def post(self, request):
        self.get_queryset()
        return Response({"url": open_card_update(request.user.company_id, by=request.user)})


class CardCheckView(RenewalView):
    def post(self, request):
        self.get_queryset()
        return Response({"result": check_card_update(request.user.company_id, by=request.user)})
