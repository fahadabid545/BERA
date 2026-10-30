"""Reads the sign-in of a request. A route picks the kind of people it is for.

    class ProjectList(APIView):
        authentication_classes = [CompanyAuthentication]

Tokens are taken from the sign-in cookie or the Authorization header, never from the address.
"""

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import NotAuthenticated

from core import request_context

from . import service
from .cookies import access_cookie_name
from .csrf import SAFE_METHODS, enforce_csrf
from .kinds import ADMIN, COMPANY

BEARER_PREFIX = b"bearer "


def read_access_token(request, kind):
    """(token, came_from_cookie), or (None, False) when the request has no credentials."""
    header = get_authorization_header(request)
    if header:
        if not header.lower().startswith(BEARER_PREFIX):
            raise NotAuthenticated()
        return header[len(BEARER_PREFIX) :].decode("latin-1").strip(), False
    cookie = request.COOKIES.get(access_cookie_name(kind))
    return (cookie, True) if cookie else (None, False)


class KindAuthentication(BaseAuthentication):
    kind = None

    def authenticate(self, request):
        token, from_cookie = read_access_token(request, self.kind)
        if token is None:
            return None  # IsSignedIn gives the "not signed in" answer
        user = service.verify_access_token(token, self.kind)
        if from_cookie and request.method not in SAFE_METHODS:
            enforce_csrf(request)
        request_context.bind_actor(user.user_id, user.company_id)
        return user, None

    def authenticate_header(self, request):
        return "Bearer"


class CompanyAuthentication(KindAuthentication):
    kind = COMPANY


class AdminAuthentication(KindAuthentication):
    kind = ADMIN
