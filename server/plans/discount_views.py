from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from core.throttles import CodeAttemptThrottle, limited
from core.validation import SafeTextField, StrictSerializer
from freeaccess import service as free_access
from platform_settings.service import get_setting
from signin.authentication import AdminAuthentication
from signin.company_views import CompanyObjectView

from . import discounts, trials
from .models import Plan, Subscription

WHOLE = {"min_value": 1, "max_value": 2_000_000_000}


class NewDiscountSerializer(StrictSerializer):
    code = SafeTextField(max_length=40)
    kind = serializers.ChoiceField(choices=["percent", "amount"])
    value = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    duration = serializers.ChoiceField(
        choices=[discounts.ONCE, discounts.MONTHS, discounts.FOREVER]
    )
    months = serializers.IntegerField(required=False, **WHOLE)
    expires_at = serializers.DateTimeField(required=False)
    max_redemptions = serializers.IntegerField(required=False, **WHOLE)
    first_time_only = serializers.BooleanField(required=False)
    plan_id = serializers.IntegerField(required=False, **WHOLE)


class ChangeDiscountSerializer(StrictSerializer):
    enabled = serializers.BooleanField(required=False)
    plan_id = serializers.IntegerField(required=False, allow_null=True, **WHOLE)


class CheckCodeSerializer(StrictSerializer):
    code = SafeTextField(max_length=64)
    plan_id = serializers.IntegerField(required=False, **WHOLE)  # for the price after a discount


def _plan(plan_id):
    plan = Plan.objects.filter(pk=plan_id).first()
    if plan is None:
        raise discounts.problem("plan_id", "Choose an active plan.")
    return plan


class DiscountList(APIView):
    """Super admins only: make discount codes, read them with their use counts."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def get(self, request):
        require_action(request.user, "discount.view")
        return Response({"codes": discounts.list_codes()})

    def post(self, request):
        require_action(request.user, "discount.manage")
        serializer = NewDiscountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        plan_id = values.pop("plan_id", None)
        values["plan"] = _plan(plan_id) if plan_id else None
        discounts.create(self.admin(), values)
        return Response({"codes": discounts.list_codes()}, status=201)


class DiscountDetail(DiscountList):
    def patch(self, request, id):
        require_action(request.user, "discount.manage")
        serializer = ChangeDiscountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if not values:
            raise discounts.problem("enabled", "Nothing was changed.")
        if "enabled" in values:
            discounts.switch(self.admin(), id, enabled=values["enabled"])
        if "plan_id" in values:
            plan = _plan(values["plan_id"]) if values["plan_id"] else None
            discounts.set_plan(self.admin(), id, plan=plan)
        return Response({"codes": discounts.list_codes()})


class CheckCode(CompanyObjectView):
    """The signed-in owner's own company only. A trial code and a discount code are typed into the
    same field: this says which one it is and what it would do, and changes nothing. Every try
    counts toward the company's limit."""

    queryset = Subscription.objects.all()
    required_action = "billing.pay"

    def get_throttles(self):
        return [throttle() for throttle in limited(CodeAttemptThrottle)]

    def post(self, request):
        self.get_queryset()  # checks the role and the company
        serializer = CheckCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        row = trials.usable_code(code)
        if row is not None:
            return Response(
                {
                    "kind": "trial",
                    "plan": row.plan.name,
                    "days": row.days,
                    "cv_limit": row.cv_limit,
                }
            )
        invite = free_access.usable_code(code)
        if invite is not None:
            return Response(
                {
                    "kind": "beta",
                    "days": invite.access_days,
                    "cvs_per_day": get_setting("beta.cvs_per_day"),
                }
            )
        plan_id = serializer.validated_data.get("plan_id")
        plan = (
            Plan.objects.filter(pk=plan_id, status=Plan.Status.ACTIVE).first() if plan_id else None
        )
        if plan_id and plan is None:
            raise discounts.not_usable()  # the same answer for every refusal
        resolved = discounts.resolve(request.user.company_id, code, plan)
        if plan is None:  # only asked whether the code is good: the amounts need a plan
            return Response({"kind": "coupon"})
        return Response({"kind": "coupon", "plan_id": plan.pk, **discounts.preview(resolved, plan)})
