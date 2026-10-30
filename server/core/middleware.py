from django.http import JsonResponse

from platform_settings.service import get_setting

from . import request_context
from .errors import AppError


class RequestContextMiddleware:
    """Gives every request a reference for the log, also sent back as X-Request-ID."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = request_context.start()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_context.current_reference()
            return response
        finally:
            request_context.finish(token)


# Routes that accept file uploads (path prefixes). The ticket that adds an upload route
# lists it here; every other route only accepts small form-sized requests.
UPLOAD_ROUTE_PREFIXES = ()
METHODS_WITH_BODY = {"POST", "PUT", "PATCH", "DELETE"}
BYTES_PER_KILOBYTE = 1024
BYTES_PER_MEGABYTE = 1024 * 1024


def largest_allowed_request_bytes(path):
    if path.startswith(UPLOAD_ROUTE_PREFIXES):
        files = get_setting("uploads.max_files_per_batch")
        return get_setting("uploads.max_file_size_mb") * files * BYTES_PER_MEGABYTE
    return get_setting("requests.max_form_kilobytes") * BYTES_PER_KILOBYTE


class RequestSizeLimitMiddleware:
    """Refuses oversized requests before their body is read."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in METHODS_WITH_BODY:
            refusal = self.refusal_for(request)
            if refusal is not None:
                return JsonResponse({"error": refusal.to_dict()}, status=refusal.status_code)
        return self.get_response(request)

    def refusal_for(self, request):
        # A body of unknown length could be any size, so it is refused outright.
        if request.META.get("HTTP_TRANSFER_ENCODING"):
            return AppError("length_required", "The request is missing its size.", status_code=411)
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return AppError("bad_request", "The request could not be read.", status_code=400)
        if length < 0:
            return AppError("bad_request", "The request could not be read.", status_code=400)
        if length > largest_allowed_request_bytes(request.path):
            return AppError("request_too_large", "The request is too large.", status_code=413)
        return None
