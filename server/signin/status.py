"""Whether the visitor of a public page is signed in, for pages that show a different button.

It never refuses and never explains: every visitor gets the same two yes-or-no answers, so it
cannot be used to learn whether an account exists. The sign-in rules are the normal ones: the
short-lived access token is checked against the live session and the account, and when it has
ended but the refresh token is still valid, one silent renewal happens first."""

from rest_framework.exceptions import NotAuthenticated

from companies.role_matrix import roles_allowed

from . import service
from .cookies import access_cookie_name, refresh_cookie_name
from .kinds import COMPANY

NOT_SIGNED_IN = {"signed_in": False, "can_pay": False}


def _verified(token):
    try:
        return service.verify_access_token(token, COMPANY) if token else None
    except NotAuthenticated:
        return None


def _renewed(token):
    """The new tokens when the refresh token is valid, otherwise None."""
    try:
        return service.refresh_session(token, COMPANY) if token else None
    except NotAuthenticated:
        return None


def visitor_status(cookies):
    """(answer, new tokens or None). The caller sets the new tokens as the session's cookies."""
    user = _verified(cookies.get(access_cookie_name(COMPANY)))
    renewed = None
    if user is None:
        renewed = _renewed(cookies.get(refresh_cookie_name(COMPANY)))
        user = _verified(renewed.access_token) if renewed else None
    if user is None:
        return NOT_SIGNED_IN, None
    return {"signed_in": True, "can_pay": user.role in roles_allowed("billing.pay")}, renewed
