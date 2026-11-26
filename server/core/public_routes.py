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
        route="api/reports/<str:token>/",
        category="shared_report",
        reason="A shared report is for people without an account. The long random token in the "
        "address is the credential; it shows only the chosen candidates' rank, score, grade, "
        "strengths and risks (and contact details only if the sharer left them in), and an "
        "unknown, expired or revoked link all answer the same.",
    ),
    PublicRoute(
        route="api/health/",
        category="health_check",
        reason="Monitoring must be able to check that the server is up without an account.",
    ),
    PublicRoute(
        route="api/plans/",
        category="website",
        reason="The public pricing page lists the active plans with the price for the "
        "visitor's detected country before an account exists. Hidden and archived plans are "
        "never listed, and it returns no subscriber counts or internal fields.",
    ),
    PublicRoute(
        route="api/legal/",
        category="website",
        reason="The public Terms and Privacy pages show the platform's legal text to visitors "
        "before an account exists. It is the same text for everyone, holds no personal or "
        "account data, and says nothing about whether it was reviewed.",
    ),
    PublicRoute(
        route="api/contact/",
        category="website",
        reason="Anyone may write to the platform from the public contact page before an account "
        "exists. It is limited to 3 messages an hour per address, refuses unknown fields, drops "
        "spam (hidden field, signed form time) without telling the sender, and answers only "
        "with a thank-you, never with anything stored.",
    ),
    PublicRoute(
        route="api/chatbot/status/",
        category="website",
        reason="The public website chat widget must know whether the chat is switched on before "
        "it shows itself to a visitor with no account. It answers only whether the chat is on and "
        "four limit numbers, and holds no personal or account data.",
    ),
    PublicRoute(
        route="api/chatbot/ask/",
        category="website",
        reason="Anyone may ask the public website chatbot a general question before an account "
        "exists. It answers only from the admin's public product documents, reads no company, "
        "candidate or CV data, stores nothing the visitor wrote, is limited per visitor "
        "address and by a daily token cap, and answers every failure with the same message.",
    ),
    PublicRoute(
        route="api/contact/form/",
        category="website",
        reason="The public contact page needs the privacy notice and the signed time the form "
        "was opened (the spam check). It holds no personal or account data.",
    ),
    PublicRoute(
        route="api/auth/company/status/",
        category="website",
        reason="The public pricing page must know whether the visitor is a signed-in owner to "
        "send the Choose plan button to billing or to sign up, and a signed-out visitor must "
        "get an answer, not a redirect. It always answers 200 with only signed_in and can_pay, "
        "uses the normal session rules (one silent renewal), and never says whether an "
        "account exists.",
    ),
    PublicRoute(
        route="api/auth/password-check/",
        category="sign_up",
        reason="Sign up, reset and invite pages show the password rules live while typing, "
        "before an account exists. It only reports which rules a text meets and stores nothing.",
    ),
    PublicRoute(
        route="api/auth/company/login/",
        category="login",
        reason="A company user signs in with email and password before having a session. "
        "Wrong guesses all look alike, are limited per address and pause the account.",
    ),
    PublicRoute(
        route="api/auth/company/login/two-step/",
        category="login",
        reason="After a right password, a person with two-step verification gives the code "
        "before a session starts. The signed, short-lived step from the password check is "
        "the credential, and wrong codes are limited and pause the account.",
    ),
    PublicRoute(
        route="api/auth/company/login/two-step/setup/",
        category="login",
        reason="A member whose company requires two-step verification sets it up at login, "
        "before having a session. The signed, short-lived step from the password check is "
        "the credential.",
    ),
    PublicRoute(
        route="api/auth/company/login/two-step/setup/confirm/",
        category="login",
        reason="Finishes the setup above with a right code and starts the session. The signed, "
        "short-lived step from the password check is the credential, and wrong codes are "
        "limited and pause the account.",
    ),
    PublicRoute(
        route="api/auth/company/accept-invite/",
        category="accept_invite",
        reason="An invited colleague has no account yet. The single-use, expiring secret in "
        "the emailed link is the credential, and the route is limited per address.",
    ),
    PublicRoute(
        route="api/auth/admin/accept-invite/",
        category="accept_invite",
        reason="An invited admin has no account yet. The single-use, expiring secret in the "
        "emailed link is the credential, and the route is rate limited.",
    ),
    PublicRoute(
        route="api/payments/stripe/webhook/",
        category="payment_notification",
        reason="The payment provider reports payments, failures and cancellations here and has "
        "no account. Every request must carry a signature made with the shared webhook secret; "
        "an unsigned, wrongly signed or too old one is refused before its body is read.",
    ),
    PublicRoute(
        route="api/platform/",
        category="website",
        reason="Every screen, signed in or not, shows the platform's name, support address and "
        "maintenance message. It holds no personal or account data.",
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
        route="api/auth/company/confirm-email-change/",
        category="email_verification",
        reason="The link sent to the new address is opened from the inbox, and whoever is "
        "signed in plays no part. The single-use secret in it is the credential.",
    ),
    PublicRoute(
        route="api/auth/company/undo-deletion/",
        category="email_verification",
        reason="The owner opens this link from the email sent when the company deletion was "
        "asked for, and nobody can be signed in then because the company's sessions ended. "
        "The single-use secret in it is the credential, and it works only during the grace "
        "period.",
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
        route="api/auth/company/forgot-password/",
        category="password_reset",
        reason="A person who forgot their password cannot sign in. It answers the same "
        "whatever the email and is limited to 5 per hour per email.",
    ),
    PublicRoute(
        route="api/auth/company/reset-password/",
        category="password_reset",
        reason="The link in the reset email is opened without a session. The single-use, "
        "expiring secret in it is the credential.",
    ),
    PublicRoute(
        route="api/auth/admin/login/",
        category="login",
        reason="An admin signs in with email and password before having a session, and it "
        "only hands out a short-lived step: a session starts after the authenticator code. "
        "Wrong guesses all look alike, are limited per address and pause the account.",
    ),
    PublicRoute(
        route="api/auth/admin/login/two-step/",
        category="login",
        reason="After a right password an admin gives the authenticator code before a session "
        "starts. The signed, short-lived step from the password check is the credential, and "
        "wrong codes are limited and pause the account.",
    ),
    PublicRoute(
        route="api/auth/admin/login/two-step/setup/",
        category="login",
        reason="An admin who has no authenticator yet must set one up before a session starts. "
        "The signed, short-lived step from the password check is the credential.",
    ),
    PublicRoute(
        route="api/auth/admin/login/two-step/setup/confirm/",
        category="login",
        reason="Finishes the admin's authenticator setup with a right code, and only then "
        "starts the session. The signed, short-lived step from the password check is the "
        "credential, and wrong codes are limited and pause the account.",
    ),
    PublicRoute(
        route="api/auth/admin/refresh/",
        category="login",
        reason="The same renewal for admin users, with the admin refresh token.",
    ),
]
