from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from companies.country_detection import detect_country
from core.permissions import PublicAccess

from .pricing import price_for
from .service import active_plans


def describe_for_visitor(plan, country):
    """Only what the pricing page shows: no status, subscriber count or waiting changes."""
    price = price_for(plan, country)
    return {
        "id": plan.pk,
        "name": plan.name,
        "description": plan.description,
        "price": {"currency": price.currency, "amount": f"{price.amount:.2f}", "note": price.note},
        "cvs_per_month": plan.cvs_per_month,
        "cvs_per_project": plan.cvs_per_project,
        "max_projects": plan.max_projects,
        "max_team_accounts": plan.max_team_accounts,
        "max_top_n": plan.max_top_n,
    }


@api_view(["GET"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the pricing page is shown before there is an account
def public_plans(request):
    country = detect_country(request)
    plans = active_plans().order_by("display_order", "id")
    return Response([describe_for_visitor(plan, country) for plan in plans])
