"""The real network address of a visitor, which a visitor cannot choose.

`X-Forwarded-For` is written by whoever sends the request, and each proxy in front of the
server adds the address it received from at the END of the list. So only the entries our
own proxies added can be believed: with `TRUSTED_PROXY_COUNT` proxies, the visitor's address
is that many places from the end. Anything a visitor writes sits further left and is ignored.
"""

import ipaddress

from django.conf import settings

UNKNOWN = "unknown"
# One household or attacker often controls a whole IPv6 /64, so it counts as one source.
IPV6_PREFIX_BITS = 64


def client_address(request):
    candidate = _candidate(request)
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return UNKNOWN
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/{IPV6_PREFIX_BITS}", strict=False))
    return str(address)


def came_through_our_proxy(request):
    """True when our own proxies handled this request, so headers they add (such as the
    country from Cloudflare) can be believed. Fewer forwarding entries than proxies means
    the request skipped them."""
    proxies = settings.TRUSTED_PROXY_COUNT
    return proxies > 0 and len(_forwarded_entries(request)) >= proxies


def _forwarded_entries(request):
    parts = [part.strip() for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
    return [part for part in parts if part]


def _candidate(request):
    if not came_through_our_proxy(request):
        return request.META.get("REMOTE_ADDR", "")
    return _forwarded_entries(request)[-settings.TRUSTED_PROXY_COUNT]
