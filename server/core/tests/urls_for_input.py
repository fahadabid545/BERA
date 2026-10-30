"""A form view that uses the shared validation, to test it with hostile input."""

from django.urls import path
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from companies.models import Company
from core.permissions import PublicAccess
from core.validation import SafeTextField, StrictSerializer, safe_file_name

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"


class NewProject(StrictSerializer):
    title = SafeTextField(max_length=200)
    notes = SafeTextField(max_length=2000, multiline=True, required=False)
    stage = serializers.ChoiceField(choices=["new", "shortlisted"])
    count = serializers.IntegerField(min_value=1, max_value=100, required=False)
    file_name = serializers.CharField(max_length=1000, required=False)


@api_view(["POST"])
@permission_classes([PublicAccess])
def new_project(request):
    form = NewProject(data=request.data)
    form.is_valid(raise_exception=True)
    values = dict(form.validated_data)
    if "file_name" in values:
        values["file_name"] = safe_file_name(values["file_name"])
    # Looks a company up by the typed title, the way a search box would.
    values["matches"] = Company.objects.filter(name=values["title"]).count()
    return Response(values)


urlpatterns = [path("api/projects/", new_project)]
