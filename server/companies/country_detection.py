"""Which country a visitor is in, to suggest it on the sign-up form.

Cloudflare adds the visitor's country in `CF-IPCountry`. A visitor could write that header
too, so it is believed only when the request came through our own proxy. Unknown or special
values ("XX" unknown, "T1" Tor, anything else) become Other. In development there is no
Cloudflare: Other, or the country named in DEVELOPMENT_PRETEND_COUNTRY.
"""

from django.conf import settings

from core.client_address import came_through_our_proxy

from .countries import COUNTRY_CODES, OTHER_COUNTRY

COUNTRY_HEADER = "CF-IPCountry"


def detect_country(request):
    if settings.APP_ENV == "development":
        return settings.DEVELOPMENT_PRETEND_COUNTRY or OTHER_COUNTRY
    if not came_through_our_proxy(request):
        return OTHER_COUNTRY
    code = request.headers.get(COUNTRY_HEADER, "").strip().upper()
    return code if code in COUNTRY_CODES else OTHER_COUNTRY
