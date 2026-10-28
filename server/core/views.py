import logging

from django.db import OperationalError, connection
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .errors import AppError
from .exception_handler import unexpected_error

logger = logging.getLogger(__name__)


@api_view(["GET"])
def health(request):
    try:
        connection.ensure_connection()
    except OperationalError as error:
        raise AppError(
            "database_unavailable", "The database is not reachable.", status_code=503
        ) from error
    return Response({"status": "ok"})


def not_found(request, exception=None):
    error = AppError("not_found", "Not found.", status_code=404)
    return JsonResponse({"error": error.to_dict()}, status=404)


def server_error(request):
    """For failures outside the API framework. The traceback is logged by Django."""
    error = unexpected_error()
    return JsonResponse({"error": error.to_dict()}, status=500)
