from rest_framework import serializers
from rest_framework.response import Response

from core.throttles import CodeAttemptThrottle, limited
from core.validation import SafeTextField, StrictSerializer
from signin.company_views import CompanyObjectView

from .checkout import confirm_checkout, start_checkout
from .models import Subscription
from .plan_change import cancel_downgrade, request_change


class StartSerializer(StrictSerializer):
    plan_id = serializers.IntegerField(min_value=1)
    code = SafeTextField(max_length=64, required=False)  # a discount code


class ChangeSerializer(StrictSerializer):
    plan_id = serializers.IntegerField(min_value=1)


class ConfirmSerializer(StrictSerializer):
    session_id = serializers.CharField(max_length=255)


class CheckoutView(CompanyObjectView):
    """The signed-in owner's own company only; no company id is ever taken from the request."""

    queryset = Subscription.objects.all()
    required_action = "billing.pay"
    serializer_class = StartSerializer

    def get_throttles(self):
        # Every try of a discount code counts, so codes cannot be guessed through checkout.
        if self.request.method == "POST" and self.request.data.get("code"):
            return [throttle() for throttle in limited(CodeAttemptThrottle)]
        return super().get_throttles()

    def post(self, request):
        self.get_queryset()  # checks the role and the company
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        return Response(
            {
                "url": start_checkout(
                    request.user.company_id,
                    body.validated_data["plan_id"],
                    body.validated_data.get("code"),
                )
            }
        )


class CheckoutConfirmView(CheckoutView):
    """Called by the page the provider sends the person back to. It asks the provider; it does
    not believe the browser."""

    serializer_class = ConfirmSerializer

    def post(self, request):
        self.get_queryset()
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = confirm_checkout(request.user.company_id, body.validated_data["session_id"])
        return Response({"result": result})


class ChangePlanView(CheckoutView):
    """Upgrade (charged now, applied when the payment is confirmed) or downgrade (applied at the
    next renewal) of the signed-in owner's own company."""

    serializer_class = ChangeSerializer

    def get_throttles(self):
        return CompanyObjectView.get_throttles(self)

    def post(self, request):
        self.get_queryset()
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        result, url = request_change(
            request.user.company_id, body.validated_data["plan_id"], by=request.user
        )
        return Response({"result": result, "url": url or None})


class CancelDowngradeView(CheckoutView):
    serializer_class = None

    def post(self, request):
        self.get_queryset()
        cancel_downgrade(request.user.company_id, by=request.user)
        return Response({"result": "downgrade_cancelled"})
