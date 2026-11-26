from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from core.throttles import CodeAttemptThrottle, limited
from core.validation import SafeTextField, StrictSerializer
from plans.models import Subscription
from signin.authentication import AdminAuthentication
from signin.company_views import CompanyObjectView

from . import entitlement, service
from .models import FreeAccess, FreeAccessInvite

WHOLE = {"min_value": 1, "max_value": 2_000_000_000}
KINDS = [kind for kind, _ in FreeAccessInvite.Kind.choices]


class NewInvite(StrictSerializer):
    kind = serializers.ChoiceField(choices=KINDS)
    label = SafeTextField(max_length=100, required=False, allow_blank=True, default="")
    email = serializers.EmailField(max_length=254, required=False)
    access_days = serializers.IntegerField(required=False, **WHOLE)
    plan_id = serializers.IntegerField(required=False, **WHOLE)
    max_uses = serializers.IntegerField(required=False, **WHOLE)
    redeem_until = serializers.DateTimeField(required=False)

    def validate(self, values):
        needs = {
            "beta_email": ["email", "access_days"],
            "beta_code": ["access_days", "max_uses"],
            "permitted_email": ["email", "plan_id"],
        }[values["kind"]]
        missing = {name: "This is required." for name in needs if name not in values}
        if missing:
            raise serializers.ValidationError(missing)
        return values


class SwitchInvite(StrictSerializer):
    enabled = serializers.BooleanField()
    also_revoke_users = serializers.BooleanField(required=False, default=False)


class Days(StrictSerializer):
    days = serializers.IntegerField(**WHOLE)


class RedeemInput(StrictSerializer):
    code = SafeTextField(max_length=64)


class FreeAccessAdminView(APIView):
    """Super admins only, checked on every method."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def allow(self, action):
        require_action(self.request.user, action)

    def valid(self, serializer_class):
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class InviteList(FreeAccessAdminView):
    def get(self, request):
        self.allow("free_access.view")
        return Response({"invites": service.list_invites()})

    def post(self, request):
        self.allow("free_access.manage")
        values = self.valid(NewInvite)
        if values["kind"] == "beta_code":
            invite, code = service.invite_code(
                self.admin(),
                label=values["label"],
                access_days=values["access_days"],
                max_uses=values["max_uses"],
                redeem_until=values.get("redeem_until"),
            )
            body = {**service.describe_invite(invite), "code": code}
        else:
            invite = service.invite_email(
                self.admin(),
                kind=values["kind"],
                email=values["email"],
                access_days=values.get("access_days"),
                plan_id=values.get("plan_id"),
                label=values["label"],
            )
            body = service.describe_invite(invite)
        response = Response(body, status=201)
        response["Cache-Control"] = "no-store"  # a code is shown here once and never again
        return response


class InviteDetail(FreeAccessAdminView):
    def patch(self, request, id):
        self.allow("free_access.manage")
        values = self.valid(SwitchInvite)
        invite = service.switch_invite(
            self.admin(),
            id,
            enabled=values["enabled"],
            also_revoke_users=values["also_revoke_users"],
        )
        return Response(service.describe_invite(invite))


class InviteExtend(FreeAccessAdminView):
    def post(self, request, id):
        self.allow("free_access.manage")
        count = service.extend_invite(self.admin(), id, days=self.valid(Days)["days"])
        return Response({"extended": count})


class AccessList(FreeAccessAdminView):
    def get(self, request):
        self.allow("free_access.view")
        query = request.query_params
        page = query.get("page", "1")
        return Response(
            service.list_grants(
                kind=query.get("kind") if query.get("kind") in ("beta", "permitted") else None,
                status=query.get("status"),
                page=int(page) if page.isdigit() and int(page) > 0 else 1,
            )
        )


class AccessDetail(FreeAccessAdminView):
    def delete(self, request, id):
        """Revoke one access."""
        self.allow("free_access.manage")
        grant = service.revoke(self.admin(), id)
        return Response(service.describe_grant(FreeAccess.objects.get(pk=grant.pk)))


class AccessExtend(FreeAccessAdminView):
    def post(self, request, id):
        self.allow("free_access.manage")
        grant = service.extend(self.admin(), id, days=self.valid(Days)["days"])
        return Response(service.describe_grant(FreeAccess.objects.get(pk=grant.pk)))


class AccessRevokeAllBeta(FreeAccessAdminView):
    def post(self, request):
        self.allow("free_access.manage")
        return Response({"revoked": service.revoke_all_beta(self.admin())})


class RedeemBetaCode(CompanyObjectView):
    """The signed-in owner's own company only. Every try counts toward the company's limit."""

    queryset = Subscription.objects.all()
    required_action = "billing.pay"

    def get_throttles(self):
        return [throttle() for throttle in limited(CodeAttemptThrottle)]

    def post(self, request):
        self.get_queryset()  # checks the role and the company
        serializer = RedeemInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        grant = service.redeem_code(request.user.company_id, serializer.validated_data["code"])
        return Response(entitlement.describe(grant))
