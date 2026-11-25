from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from companies.models import CompanyUser
from core.throttles import CodeAttemptThrottle, limited
from core.validation import SafeTextField, StrictSerializer
from signin.authentication import AdminAuthentication
from signin.company_views import CompanyObjectView

from . import trials
from .models import Subscription, TrialCode

WHOLE = {"min_value": 1, "max_value": 2_000_000_000}
MAX_CODE_LENGTH = 64
NAME_LENGTH = 100


class NewTrialCodeSerializer(StrictSerializer):
    name = SafeTextField(max_length=NAME_LENGTH)
    plan_id = serializers.IntegerField(**WHOLE)
    days = serializers.IntegerField(**WHOLE)
    cv_limit = serializers.IntegerField(**WHOLE)
    expires_at = serializers.DateTimeField()


class SwitchSerializer(StrictSerializer):
    enabled = serializers.BooleanField()


class CodeSerializer(StrictSerializer):
    code = SafeTextField(max_length=MAX_CODE_LENGTH)


class TrialCodeList(APIView):
    """Super admins only: make codes, see their status, switch them on or off."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def get(self, request):
        require_action(request.user, "trial_code.view")
        return Response({"codes": trials.list_codes()})

    def post(self, request):
        require_action(request.user, "trial_code.manage")
        serializer = NewTrialCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        row, code = trials.create_code(
            self.admin(),
            name=values["name"],
            plan=trials.plan_for(values["plan_id"]),
            days=values["days"],
            cv_limit=values["cv_limit"],
            expires_at=values["expires_at"],
        )
        # The code is shown here once and never again; it must not be cached.
        response = Response({**trials.describe_code(row), "code": code}, status=201)
        response["Cache-Control"] = "no-store"
        return response


class TrialCodeDetail(TrialCodeList):
    def patch(self, request, id):
        require_action(request.user, "trial_code.manage")
        serializer = SwitchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = trials.switch_code(self.admin(), id, enabled=serializer.validated_data["enabled"])
        return Response(
            trials.describe_code(TrialCode.objects.select_related("plan").get(pk=row.pk))
        )


class RedeemTrialCode(CompanyObjectView):
    """The signed-in owner's own company only. Every try counts toward the company's limit."""

    queryset = Subscription.objects.all()
    required_action = "billing.pay"

    def get_throttles(self):
        return [throttle() for throttle in limited(CodeAttemptThrottle)]

    def post(self, request):
        self.get_queryset()  # checks the role and the company
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = CompanyUser.objects.get(pk=request.user.user_id)
        subscription = trials.redeem(
            request.user.company_id, owner, serializer.validated_data["code"]
        )
        return Response(trials.describe_trial(subscription))
