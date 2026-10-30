"""Every link in an email goes through here.

Only the website's own address is allowed, so an email can never send someone elsewhere, and
a password can never be placed in a link. (Each link's token is made single-use and expiring
by the feature that sends it: verification, reset, invite.)
"""

from urllib.parse import parse_qsl, urlencode, urlsplit

from django.conf import settings

FORBIDDEN_QUERY_NAMES = {"password", "passwd", "pass", "pwd", "secret"}
MAX_LINK_LENGTH = 2000


def build_link(path, **query):
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("A link path must start with a single slash.")
    base = settings.WEB_BASE_URL.rstrip("/")
    return validate_link(f"{base}{path}" + (f"?{urlencode(query)}" if query else ""))


def validate_link(url):
    parts = urlsplit(url)
    site = urlsplit(settings.WEB_BASE_URL)
    if (parts.scheme, parts.netloc) != (site.scheme, site.netloc) or "@" in parts.netloc:
        raise ValueError("An email link must point to the Bera website.")
    names = {name.lower() for name, _ in parse_qsl(parts.query + "&" + parts.fragment)}
    if names & FORBIDDEN_QUERY_NAMES:
        raise ValueError("An email link must never carry a password.")
    if len(url) > MAX_LINK_LENGTH:
        raise ValueError("An email link is too long.")
    return url
