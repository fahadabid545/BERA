"""One private route for each kind of user, to test reading a sign-in."""

import logging

from django.urls import path
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.response import Response

from signin.authentication import AdminAuthentication, CompanyAuthentication

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"


def who(request):
    user = request.user
    return Response({"user_id": user.user_id, "role": user.role, "company_id": user.company_id})


@api_view(["GET", "POST"])
@authentication_classes([CompanyAuthentication])
def company_route(request):
    return who(request)


@api_view(["GET", "POST"])
@authentication_classes([AdminAuthentication])
def admin_route(request):
    return who(request)


@api_view(["GET"])
@authentication_classes([CompanyAuthentication])
def log_route(request):
    logging.getLogger(__name__).info("doing the work")
    return Response({})


urlpatterns = [
    path("api/company-only/", company_route),
    path("api/admin-only/", admin_route),
    path("api/log-something/", log_route),
]
