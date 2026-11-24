"""The system emails. One layout (templates/emailing/message.*) gives every one of them the
platform name (a setting), a heading, a main button and a plain-text version; this file holds
the words.

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
        subject="Verify your email address for {app_name}",
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
        subject="Reset your {app_name} password",
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
        subject="{inviter_name} invited you to {company_name} on {app_name}",
        heading="You are invited",
        paragraphs=(
            "{inviter_name} invited you to join {company_name} on {app_name}.",
            "The invitation works once and expires in {expires_in}.",
        ),
        button_label="Accept invitation",
        variables=("inviter_name", "company_name", "link", "expires_in"),
    ),
    "admin_invite": EmailTemplate(
        subject="{inviter_name} invited you to the {app_name} admin team",
        heading="You are invited",
        paragraphs=(
            "{inviter_name} invited you to join the {app_name} admin team as {role_name}.",
            "The invitation works once and expires in {expires_in}. You choose your password "
            "there, and set up two-step verification when you first sign in.",
        ),
        button_label="Accept invitation",
        variables=("inviter_name", "role_name", "link", "expires_in"),
    ),
    "password_changed": EmailTemplate(
        subject="Your {app_name} password was changed",
        heading="Your password was changed",
        paragraphs=(
            GREETING,
            "Your password was changed on {when}.",
            "If this was not you, reset your password now.",
        ),
        button_label="Reset password",
        variables=("name", "when", "link"),
    ),
    "security_alert": EmailTemplate(
        subject="{app_name} security alert",
        heading="Security alert",
        paragraphs=(
            GREETING,
            "{what}",
            "It happened on {when}. Further alerts of this kind are held back for a while.",
        ),
        button_label="Open the audit log",
        variables=("name", "what", "when", "link"),
    ),
    "email_changed": EmailTemplate(
        subject="Your {app_name} email address was changed",
        heading="Your email address was changed",
        paragraphs=(
            GREETING,
            "The email address on your account was changed on {when}.",
            "If this was not you, contact support at {support_email} right away.",
        ),
        button_label="Contact support",
        variables=("name", "when", "link"),
    ),
    "new_sign_in": EmailTemplate(
        subject="New sign-in to your {app_name} account",
        heading="New sign-in",
        paragraphs=(
            GREETING,
            "We noticed a new sign-in on {when} from {device} in {place}.",
            "If this was you, no action is needed. If not, reset your password now.",
        ),
        button_label="Reset password",
        variables=("name", "when", "device", "place", "link"),
    ),
    "already_registered": EmailTemplate(
        subject="Someone tried to sign up to {app_name} with your email address",
        heading="You already have an account",
        paragraphs=(
            GREETING,
            "Someone tried to create a {app_name} account with your email address, which already "
            "has one.",
            "If this was you, log in. If you forgot your password, you can reset it from the "
            "login page. If it was not you, you can ignore this email.",
        ),
        button_label="Log in",
        variables=("name", "link"),
    ),
    "usage_notice": EmailTemplate(
        subject="{app_name}: {title}",
        heading="{title}",
        paragraphs=(GREETING, "{message}"),
        button_label="View billing",
        variables=("name", "title", "message", "link"),
    ),
    "account_notice": EmailTemplate(
        subject="{app_name}: {title}",
        heading="{title}",
        paragraphs=(GREETING, "{message}"),
        button_label="Open {app_name}",
        variables=("name", "title", "message", "link"),
    ),
    "confirm_new_email": EmailTemplate(
        subject="Confirm your new email address for {app_name}",
        heading="Confirm your new email address",
        paragraphs=(
            GREETING,
            "You asked to use this address for your {app_name} account. The link works once and "
            "expires in {expires_in}.",
            "If you did not ask for this, ignore this email. Nothing changes.",
        ),
        button_label="Confirm email address",
        variables=("name", "link", "expires_in"),
    ),
    "download_ready": EmailTemplate(
        subject="Your {app_name} download is ready",
        heading="Your download is ready",
        paragraphs=(
            GREETING,
            "The package of CVs you asked for is ready. Sign in to download it. It stays "
            "available for {expires_in}.",
        ),
        button_label="Open the download",
        variables=("name", "link", "expires_in"),
    ),
    "deletion_scheduled": EmailTemplate(
        subject="Your {app_name} company will be deleted",
        heading="Your company will be deleted",
        paragraphs=(
            GREETING,
            "Deleting your company was requested. Everything in it will be removed for good on "
            "{when}. If this was a mistake, you can undo it until then.",
        ),
        button_label="Undo the deletion",
        variables=("name", "when", "link"),
    ),
    "retention_warning": EmailTemplate(
        subject="Some of your {app_name} data will be deleted soon",
        heading="Data will be deleted soon",
        paragraphs=(
            GREETING,
            "{files} in your projects reach the end of your retention period and will be "
            "deleted from {when}. Download what you need before then, or choose a longer "
            "retention period.",
        ),
        button_label="Open retention settings",
        variables=("name", "files", "when", "link"),
    ),
    "batch_finished": EmailTemplate(
        subject="Your CV upload is finished",
        heading="Your upload is finished",
        paragraphs=(
            GREETING,
            "The CVs you uploaded to {project} are finished: {summary}.",
        ),
        button_label="Open the project",
        variables=("name", "project", "summary", "link"),
    ),
    "subscription_ending": EmailTemplate(
        subject="Your {app_name} subscription is ending soon",
        heading="Your subscription is ending",
        paragraphs=(
            GREETING,
            "Your subscription ends on {when}. After that you can still view and download "
            "your data, but you cannot upload, start projects or score until you renew.",
        ),
        button_label="Open billing",
        variables=("name", "when", "link"),
    ),
    "payment_problem": EmailTemplate(
        subject="There is a problem with your {app_name} payment",
        heading="Payment problem",
        paragraphs=(GREETING, "{message}"),
        button_label="Update payment method",
        variables=("name", "message", "link"),
    ),
    "ai_spend_alert": EmailTemplate(
        subject="AI spending passed its {period} limit",
        heading="AI spending is high",
        paragraphs=(
            GREETING,
            "AI spending for {period_name} reached {spent} US dollars, which is over the limit "
            "of {limit} US dollars.",
        ),
        button_label="Open AI controls",
        variables=("name", "period", "period_name", "spent", "limit", "link"),
    ),
}
