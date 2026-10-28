import logging

from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .errors import AppError

logger = logging.getLogger(__name__)


def error_response(error):
    return Response({"error": error.to_dict()}, status=error.status_code)


def api_exception_handler(exc, context):
    """Turn every failure into the shared `{"error": {...}}` response shape."""
    if isinstance(exc, AppError):
        return error_response(exc)
    if isinstance(exc, ValidationError):
        return error_response(
            AppError("validation_error", "The request is invalid.", exc.detail, 400)
        )
    if isinstance(exc, APIException):
        drf_response = drf_exception_handler(exc, context)
        return error_response(
            AppError(exc.default_code, str(exc.detail), status_code=drf_response.status_code)
        )
    logger.exception("Unhandled error")
    return error_response(
        AppError("internal_error", "Something went wrong. Please try again.", status_code=500)
    )
