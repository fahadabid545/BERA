from . import request_context


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
