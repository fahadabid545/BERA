"""Keeps other websites and injected content from using the API through a user's browser.

OriginPolicyMiddleware refuses requests that a browser says came from a site that is not
one of Bera's own addresses (`ALLOWED_ORIGINS`), and lets the allowed ones read the answer.
SecurityHeadersMiddleware puts the standard protections on every response.
"""

from django.conf import settings
from django.http import HttpResponse, JsonResponse

from .errors import not_allowed

ALLOWED_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
ALLOWED_REQUEST_HEADERS = "Content-Type, X-CSRF-Token, Authorization"
PREFLIGHT_SECONDS = 600

# The API only ever answers with JSON, so nothing it sends may load, run or be framed.
RESPONSE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Resource-Policy": "same-origin",
    # Answers are private to the signed-in person and must not be kept by shared caches.
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        for name, value in RESPONSE_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


class OriginPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        # Requests that do not come from a web page (no Origin) are not what this guards against.
        if origin is None:
            return self.get_response(request)
        if not self.is_allowed(request, origin):
            refusal = not_allowed()
            return JsonResponse({"error": refusal.to_dict()}, status=refusal.status_code)
        if request.method == "OPTIONS" and "Access-Control-Request-Method" in request.headers:
            response = HttpResponse(status=204)
            response["Access-Control-Allow-Methods"] = ALLOWED_METHODS
            response["Access-Control-Allow-Headers"] = ALLOWED_REQUEST_HEADERS
            response["Access-Control-Max-Age"] = str(PREFLIGHT_SECONDS)
        else:
            response = self.get_response(request)
        response["Access-Control-Allow-Origin"] = origin
        response["Access-Control-Allow-Credentials"] = "true"
        response["Vary"] = "Origin"
        return response

    @staticmethod
    def is_allowed(request, origin):
        own_address = f"{request.scheme}://{request.get_host()}"
        return origin == own_address or origin in settings.ALLOWED_ORIGINS
