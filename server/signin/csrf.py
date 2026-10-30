"""Cross-site request protection for requests that carry their sign-in in cookies.

Besides SameSite=Strict on the cookies, a change request must repeat the value of the
readable `bera_csrf` cookie in the `X-CSRF-Token` header. Another site can make the
browser send cookies but cannot read this one, so it cannot fill the header in.
"""

import secrets

from rest_framework.exceptions import PermissionDenied

from .cookies import CSRF_COOKIE, CSRF_HEADER_META

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def enforce_csrf(request):
    cookie = request.COOKIES.get(CSRF_COOKIE, "")
    header = request.META.get(CSRF_HEADER_META, "")
    if not cookie or not secrets.compare_digest(cookie.encode(), header.encode()):
        raise PermissionDenied()
