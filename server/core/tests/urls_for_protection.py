"""A private view, to test the refusal answers."""

from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"


@api_view(["GET"])
def private_view(request):
    return Response({"ok": True})


urlpatterns = [path("api/private/", private_view)]
