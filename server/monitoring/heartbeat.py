"""The dead-man ping: a plain request to an outside service (Healthchecks.io). The service raises
the alarm when the pings STOP, which covers a dead server, a stopped timer, a broken email path
and any failing check. The request carries nothing: no body, no query, no data about us. The
address itself is a secret (it names our check), so it is never logged."""

import logging
import urllib.request
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 10


def ping(address):
    """True when the service answered. With no address set (development, optional staging) nothing
    is sent and it counts as fine."""
    if not address:
        return True
    if urlsplit(address).scheme != "https":
        logger.error("A heartbeat address is not https, so no ping was sent.")
        return False
    try:
        request = urllib.request.Request(address, method="GET", headers={"User-Agent": "bera"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as answer:  # noqa: S310
            return 200 <= answer.status < 300
    except Exception as error:
        logger.error("A heartbeat ping failed (%s).", type(error).__name__)
        return False
