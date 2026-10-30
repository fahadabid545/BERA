"""Where the tokens live in the browser: cookies that page scripts cannot read."""

import secrets

from django.conf import settings

from .kinds import KINDS

CSRF_COOKIE = "bera_csrf"
CSRF_HEADER_META = "HTTP_X_CSRF_TOKEN"
# The refresh token is only sent to its own address, so other requests never carry it.
REFRESH_PATH = "/api/auth/{kind}/"
ACCESS_PATH = "/api/"


def access_cookie_name(kind):
    return f"bera_{kind}_access"


def refresh_cookie_name(kind):
    return f"bera_{kind}_refresh"


def _protected_cookie(response, name, value, *, max_age, path):
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        httponly=True,  # page scripts cannot read it
        secure=not settings.DEBUG,  # only over https outside development
        samesite="Strict",  # never sent with requests started from another site
    )


def set_session_cookies(response, kind, issued):
    _protected_cookie(
        response,
        access_cookie_name(kind),
        issued.access_token,
        max_age=issued.access_seconds,
        path=ACCESS_PATH,
    )
    _protected_cookie(
        response,
        refresh_cookie_name(kind),
        issued.refresh_token,
        max_age=issued.refresh_seconds,
        path=REFRESH_PATH.format(kind=kind),
    )
    # Page scripts must read this one to copy it into the X-CSRF-Token header (see csrf.py).
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=issued.refresh_seconds,
        path="/",
        secure=not settings.DEBUG,
        samesite="Strict",
    )


def clear_session_cookies(response, kind):
    assert kind in KINDS
    response.delete_cookie(access_cookie_name(kind), path=ACCESS_PATH)
    response.delete_cookie(refresh_cookie_name(kind), path=REFRESH_PATH.format(kind=kind))
