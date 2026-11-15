from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from core.permissions import PublicAccess

from .shared_reports import view_report


@api_view(["GET"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the people it is shared with have no account
def shared_report(request, token):
    response = Response(view_report(token))
    # A shared report is never kept by browsers or caches, so a revoked link stops at once.
    response["Cache-Control"] = "private, no-store"
    return response
