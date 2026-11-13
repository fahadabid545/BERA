"""Super-admin controls over a company's access. Every route names its action in the role
matrix, so a support admin is refused even when the address is typed in; every change needs a
written reason and is audited."""

from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from companies import admin_controls
from companies.models import Company, CompanyUser
from plans import limit_overrides, subscriptions
from plans.models import Plan
from signin.authentication import AdminAuthentication
from twostep import admin_resets

from .control_serializers import (
    CompanyUserTwoStepSerializer,
    GrantFreeSerializer,
    ReasonSerializer,
    SetLimitSerializer,
)


def _found(model, id):
    try:
        return model.objects.get(pk=id)
    except (model.DoesNotExist, ValueError) as error:
        raise Http404 from error


class ControlView(APIView):
    authentication_classes = [AdminAuthentication]
    action = None  # an action of adminusers/role_matrix.py

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def checked(self, serializer_class):
        require_action(self.request.user, self.action)
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return dict(serializer.validated_data)


def describe_subscription(company_id):
    subscription = subscriptions.get_subscription(company_id)
    return {
        "state": subscriptions.effective_state(subscription),
        "plan_id": subscription.plan_id,
        "period_end": subscription.period_end,
    }


class SuspendCompany(ControlView):
    action = "company.suspend"

    def post(self, request, id):
        values = self.checked(ReasonSerializer)
        company = _found(Company, id)
        admin_controls.suspend_company(company.pk, by=self.admin(), reason=values["reason"])
        return Response({"status": Company.Status.SUSPENDED})


class UnsuspendCompany(ControlView):
    action = "company.suspend"

    def post(self, request, id):
        values = self.checked(ReasonSerializer)
        company = _found(Company, id)
        admin_controls.unsuspend_company(company.pk, by=self.admin(), reason=values["reason"])
        return Response({"status": Company.Status.ACTIVE})


class CompanyLimit(ControlView):
    action = "limit.change"

    def put(self, request, id, name):
        values = self.checked(SetLimitSerializer)
        company = _found(Company, id)
        limit_overrides.set_limit(
            company.pk, name, values["value"], by=self.admin(), reason=values["reason"]
        )
        return Response({"limit": name, "value": values["value"]})

    def delete(self, request, id, name):
        values = self.checked(ReasonSerializer)
        company = _found(Company, id)
        limit_overrides.clear_limit(company.pk, name, by=self.admin(), reason=values["reason"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class GrantFreeSubscription(ControlView):
    action = "subscription.grant_free"

    def post(self, request, id):
        values = self.checked(GrantFreeSerializer)
        company = _found(Company, id)
        plan = _found(Plan, values["plan_id"])
        subscriptions.grant_free(
            company.pk,
            plan,
            period_end=values["period_end"],
            by=self.admin(),
            reason=values["reason"],
        )
        return Response(describe_subscription(company.pk))


class EndFreeSubscription(ControlView):
    action = "subscription.grant_free"

    def post(self, request, id):
        values = self.checked(ReasonSerializer)
        company = _found(Company, id)
        subscriptions.end_free(company.pk, by=self.admin(), reason=values["reason"])
        return Response(describe_subscription(company.pk))


class TerminateSubscription(ControlView):
    action = "subscription.terminate"

    def post(self, request, id):
        values = self.checked(ReasonSerializer)
        company = _found(Company, id)
        subscriptions.terminate(company.pk, by=self.admin(), reason=values["reason"])
        return Response(describe_subscription(company.pk))


class ResetAdminTwoStep(ControlView):
    action = "admin_user.manage"

    def post(self, request, id):
        values = self.checked(ReasonSerializer)
        target = _found(AdminUser, id)
        admin_resets.reset_admin_two_step(target.pk, by=self.admin(), reason=values["reason"])
        return Response({"status": "reset"})


class TurnOffCompanyUserTwoStep(ControlView):
    action = "company_user.two_step_off"

    def post(self, request, id):
        values = self.checked(CompanyUserTwoStepSerializer)
        target = _found(CompanyUser, id)
        admin_resets.turn_off_company_user_two_step(
            target.pk,
            by=self.admin(),
            reason=values["reason"],
            identity_checked=values["identity_checked"],
        )
        return Response({"status": "off"})
