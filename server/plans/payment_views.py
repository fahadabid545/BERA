from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.role_matrix import require_action
from core.validation import StrictSerializer
from signin.authentication import AdminAuthentication

from . import payment_overview
from .models import PaymentEvent


class PaymentListQuery(StrictSerializer):
    """The query string of the list. Unknown or invalid values are refused, not ignored."""

    kind = serializers.ChoiceField(choices=PaymentEvent.Kind.values, required=False)
    company = serializers.IntegerField(min_value=1, max_value=2_000_000_000, required=False)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    page = serializers.IntegerField(min_value=1, max_value=1_000_000, default=1)


class PaymentList(APIView):
    """Super admins only: support must not see payment amounts, so the role is checked here."""

    authentication_classes = [AdminAuthentication]

    def get(self, request):
        require_action(request.user, "payment.view")
        query = PaymentListQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = dict(query.validated_data)
        page = values.pop("page")
        return Response(payment_overview.overview(values, page))
