"""Views that fail on purpose, for testing the error and log behaviour."""

from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"


@api_view(["POST"])
def unexpected_failure(request):
    # A developer mistake: the request body ends up in the exception message.
    raise RuntimeError(f"failed at /srv/app/secret_path.py with {request.data}")


@api_view(["POST"])
def form_mistake(request):
    raise ValidationError({"email": ["Enter a valid email address."]})


urlpatterns = [
    path("api/boom/", unexpected_failure),
    path("api/form/", form_mistake),
]
