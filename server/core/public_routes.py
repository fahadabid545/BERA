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
    PublicRoute(
        route="api/auth/company/login/",
        category="login",
        reason="A company user signs in with email and password before having a session. "
        "Wrong guesses all look alike, are limited per address and pause the account.",
    ),
    PublicRoute(
        route="api/auth/company/refresh/",
        category="login",
        reason="A company user whose short access token ended must renew it with the refresh "
        "token (a protected cookie), which is itself the credential.",
    ),
    PublicRoute(
        route="api/auth/company/signup/",
        category="sign_up",
        reason="A visitor creates a company account before having one. It answers the same "
        "whether or not the email is taken and is limited per address.",
    ),
    PublicRoute(
        route="api/auth/company/signup/country/",
        category="sign_up",
        reason="The sign-up form shows the visitor's detected country before an account exists. "
        "It returns only a country code.",
    ),
    PublicRoute(
        route="api/auth/company/verify-email/",
        category="email_verification",
        reason="The link in the verification email is opened before the person can sign in. "
        "The single-use secret in it is the credential.",
    ),
    PublicRoute(
        route="api/auth/company/verify-email/resend/",
        category="email_verification",
        reason="A person who cannot sign in until verified asks for a new link. It answers the "
        "same whatever the email and is limited to 3 per hour per email.",
    ),
    PublicRoute(
        route="api/auth/company/logout/",
        category="login",
        reason="Signing out must work even when the short-lived access token has ended, so it "
        "is identified by the refresh cookie, which is itself the credential.",
    ),
    PublicRoute(
        route="api/auth/admin/logout/",
        category="login",
        reason="The same sign-out for admin users, with the admin refresh cookie.",
    ),
    PublicRoute(
        route="api/auth/admin/refresh/",
        category="login",
        reason="The same renewal for admin users, with the admin refresh token.",
    ),
]
