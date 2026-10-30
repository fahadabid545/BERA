"""The system emails. One layout (templates/emailing/message.*) gives every one of them the
Bera name, a heading, a main button and a plain-text version; this file holds the words.

Texts use {placeholders} filled from the values the sender passes. Later features that need
another email add an entry here with their own ticket."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailTemplate:
    subject: str
    heading: str
    paragraphs: tuple
    button_label: str
    variables: tuple  # every value the sender must pass; "link" is always one of them


GREETING = "Hi {name},"

CATALOG = {
    "verify_email": EmailTemplate(
        subject="Verify your email address for Bera",
        heading="Verify your email address",
        paragraphs=(
            GREETING,
            "Please confirm that this is your email address. The link works once and "
            "expires in {expires_in}.",
        ),
        button_label="Verify email",
        variables=("name", "link", "expires_in"),
    ),
    "reset_password": EmailTemplate(
        subject="Reset your Bera password",
        heading="Reset your password",
        paragraphs=(
            GREETING,
            "We received a request to reset your password. The link works once and "
            "expires in {expires_in}.",
            "If you did not ask for this, ignore this email. Your password stays the same.",
        ),
        button_label="Reset password",
        variables=("name", "link", "expires_in"),
    ),
    "team_invite": EmailTemplate(
        subject="{inviter_name} invited you to {company_name} on Bera",
        heading="You are invited",
        paragraphs=(
            "{inviter_name} invited you to join {company_name} on Bera.",
            "The invitation works once and expires in {expires_in}.",
        ),
        button_label="Accept invitation",
        variables=("inviter_name", "company_name", "link", "expires_in"),
    ),
    "password_changed": EmailTemplate(
        subject="Your Bera password was changed",
        heading="Your password was changed",
        paragraphs=(
            GREETING,
            "Your password was changed on {when}.",
            "If this was not you, reset your password now.",
        ),
        button_label="Reset password",
        variables=("name", "when", "link"),
    ),
    "email_changed": EmailTemplate(
        subject="Your Bera email address was changed",
        heading="Your email address was changed",
        paragraphs=(
            GREETING,
            "The email address on your account was changed on {when}.",
            "If this was not you, secure your account now.",
        ),
        button_label="Secure my account",
        variables=("name", "when", "link"),
    ),
    "new_sign_in": EmailTemplate(
        subject="New sign-in to your Bera account",
        heading="New sign-in",
        paragraphs=(
            GREETING,
            "We noticed a new sign-in on {when} from {device}, near {place}.",
            "If this was you, no action is needed. If not, secure your account.",
        ),
        button_label="Review sign-ins",
        variables=("name", "when", "device", "place", "link"),
    ),
    "usage_notice": EmailTemplate(
        subject="Bera: {title}",
        heading="{title}",
        paragraphs=(GREETING, "{message}"),
        button_label="View billing",
        variables=("name", "title", "message", "link"),
    ),
    "payment_problem": EmailTemplate(
        subject="There is a problem with your Bera payment",
        heading="Payment problem",
        paragraphs=(GREETING, "{message}"),
        button_label="Update payment method",
        variables=("name", "message", "link"),
    ),
}
