from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from signin.authentication import AdminAuthentication

from . import service
from .models import PendingPlanChange, Plan
from .serializers import ChangePlanSerializer, CreatePlanSerializer, DeletePlanSerializer
from .subscribers import subscriber_count


def describe(plan):
    pending = PendingPlanChange.objects.filter(plan=plan).first()
    price = lambda value: None if value is None else f"{value:.2f}"  # noqa: E731
    return {
        "id": plan.pk,
        "name": plan.name,
        "description": plan.description,
        "price_usd": price(plan.price_usd),
        "price_pkr": price(plan.price_pkr),
        "cvs_per_month": plan.cvs_per_month,
        "cvs_per_project": plan.cvs_per_project,
        "max_projects": plan.max_projects,
        "max_team_accounts": plan.max_team_accounts,
        "max_top_n": plan.max_top_n,
        "monthly_ai_token_cap": plan.monthly_ai_token_cap,
        "status": plan.status,
        "display_order": plan.display_order,
        "subscribers": subscriber_count(plan),
        "missing_for_active": service.missing_for_active(plan),
        "pending_change": pending.values if pending else None,
    }


class PlanView(APIView):
    """Super admins only: every route here checks the role, so a support admin is refused
    even when the address is typed in."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def plan(self, id):
        try:
            return Plan.objects.get(pk=id)
        except (Plan.DoesNotExist, ValueError) as error:
            raise Http404 from error


class PlanList(PlanView):
    def get(self, request):
        require_action(request.user, "plan.view")
        return Response([describe(plan) for plan in Plan.objects.all()])

    def post(self, request):
        require_action(request.user, "plan.change")
        serializer = CreatePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values.keys() & {"price_usd", "price_pkr"}:
            require_action(request.user, "price.change")
        plan = service.create_plan(self.admin(), values)
        return Response(describe(plan), status=status.HTTP_201_CREATED)


class PlanDetail(PlanView):
    def get(self, request, id):
        require_action(request.user, "plan.view")
        return Response(describe(self.plan(id)))

    def patch(self, request, id):
        require_action(request.user, "plan.change")
        serializer = ChangePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        reason, apply = values.pop("reason"), values.pop("apply", None)
        if values.keys() & {"price_usd", "price_pkr"}:
            require_action(request.user, "price.change")
        self.plan(id)  # not found before anything else is said
        plan, waiting = service.update_plan(self.admin(), id, values, reason=reason, apply=apply)
        return Response({**describe(plan), "waiting_for_renewal": waiting})

    def delete(self, request, id):
        require_action(request.user, "plan.change")
        serializer = DeletePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.plan(id)
        service.delete_plan(self.admin(), id, reason=serializer.validated_data["reason"])
        return Response(status=status.HTTP_204_NO_CONTENT)
