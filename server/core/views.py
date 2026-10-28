from django.db import OperationalError, connection
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .errors import AppError


@api_view(["GET"])
def health(request):
    try:
        connection.ensure_connection()
    except OperationalError as error:
        raise AppError(
            "database_unavailable", "The database is not reachable.", status_code=503
        ) from error
    return Response({"status": "ok"})
