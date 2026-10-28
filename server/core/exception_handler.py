import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework.exceptions import APIException, ParseError, ValidationError
from rest_framework.response import Response

from . import request_context
from .errors import AppError

logger = logging.getLogger(__name__)

UNEXPECTED_MESSAGE = "Something went wrong."
NON_FIELD_KEY = "non_field_errors"


def error_response(error):
    return Response({"error": error.to_dict()}, status=error.status_code)


def unexpected_error():
    """The answer for any failure we did not plan for. The reference is in the log."""
    reference = request_context.current_reference() or request_context.new_reference()
    return AppError("internal_error", UNEXPECTED_MESSAGE, status_code=500, reference=reference)


def field_messages(detail, prefix=""):
    """Flatten DRF validation details to {"field": "first message"}."""
    if isinstance(detail, dict):
        pairs = detail.items()
    elif isinstance(detail, list) and detail and not isinstance(detail[0], str):
        pairs = enumerate(detail)
    else:
        message = detail[0] if isinstance(detail, list) and detail else detail
        return {prefix or NON_FIELD_KEY: str(message)}
    messages = {}
    for name, nested in pairs:
        path = f"{prefix}.{name}" if prefix else str(name)
        messages.update(field_messages(nested, path))
    return messages


def validation_error(exc):
    fields = field_messages(exc.detail)
    summary = fields.pop(NON_FIELD_KEY, "Please check the form and try again.")
    return AppError("validation_error", summary, status_code=400, fields=fields or None)


def api_exception_handler(exc, context):
    """Turn every failure into the shared `{"error": {...}}` response shape."""
    if isinstance(exc, AppError):
        if exc.status_code >= 500:
            logger.error("%s: %s", exc.code, exc.message)
        return error_response(exc)
    if isinstance(exc, ValidationError):
        return error_response(validation_error(exc))
    if isinstance(exc, ParseError):
        return error_response(
            AppError("bad_request", "The request could not be read.", status_code=400)
        )
    if isinstance(exc, Http404):
        return error_response(AppError("not_found", "Not found.", status_code=404))
    if isinstance(exc, PermissionDenied):
        return error_response(
            AppError("permission_denied", "You do not have permission to do this.", status_code=403)
        )
    if isinstance(exc, APIException):
        return error_response(
            AppError(exc.default_code, str(exc.detail), status_code=exc.status_code)
        )
    logger.exception("Unexpected error")
    return error_response(unexpected_error())
