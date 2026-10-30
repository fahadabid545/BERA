"""Every address a visitor may use without signing in. Everything else is private.

Adding a route here needs a written reason in the ticket that adds it, repeated in
`reason`. The website pages are served by the web app, not this server, so they do
not appear here.
"""

from dataclasses import dataclass

PUBLIC_CATEGORIES = frozenset(
    {
        "website",
        "sign_up",
        "login",
        "password_reset",
        "email_verification",
        "accept_invite",
        "shared_report",
        "payment_notification",
        "health_check",
    }
)


@dataclass(frozen=True)
class PublicRoute:
    route: str
    category: str
    reason: str


PUBLIC_ROUTES = [
    PublicRoute(
        route="api/health/",
        category="health_check",
        reason="Monitoring must be able to check that the server is up without an account.",
    ),
]
