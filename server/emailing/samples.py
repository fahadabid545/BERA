"""Example values for every template, used by the development test command and the tests."""

from .links import build_link
from .rendering import duration_text


def sample_values(template_name):
    link = build_link("/example", token="sample-token-for-development")
    shared = {"name": "Fake Person", "link": link, "when": "1 January 2030, 09:00 UTC"}
    return {
        "verify_email": {**shared, "expires_in": duration_text(24, "hour")},
        "reset_password": {**shared, "expires_in": duration_text(1, "hour")},
        "team_invite": {
            "inviter_name": "Fake Owner",
            "company_name": "Fake Test Company",
            "link": link,
            "expires_in": duration_text(7, "day"),
        },
        "admin_invite": {
            "inviter_name": "Fake Super Admin",
            "role_name": "support",
            "link": link,
            "expires_in": duration_text(7, "day"),
        },
        "password_changed": shared,
        "email_changed": shared,
        "new_sign_in": {**shared, "device": "Firefox on Windows", "place": "Germany"},
        "already_registered": {"name": shared["name"], "link": link},
        "usage_notice": {
            **shared,
            "title": "You have used 80% of your plan",
            "message": "Your company has used 80% of its included analyses this month.",
        },
        "account_notice": {
            **shared,
            "title": "Your company account was suspended",
            "message": "Your company account was suspended. Please contact support.",
        },
        "security_alert": {
            **shared,
            "what": "A sign-in token that had already been used was presented again.",
        },
        "confirm_new_email": {**shared, "expires_in": duration_text(24, "hour")},
        "contact_message": {
            "sender_name": shared["name"],
            "sender_email": "user@example.com",
            "message": "Hello, I have a question.",
            "link": link,
        },
        "download_ready": {**shared, "expires_in": duration_text(24, "hour")},
        "deletion_scheduled": shared,
        "retention_warning": {**shared, "files": "12 CVs"},
        "batch_finished": {
            **shared,
            "project": "Fake Test Project",
            "summary": "12 CVs were scored",
        },
        "subscription_ending": shared,
        "trial_ending": shared,
        "subscription_renewing": {**shared, "plan": "Fake Plan", "amount": "USD 10.00"},
        "payment_problem": {
            **shared,
            "message": "We could not take your last payment. Please update your payment method.",
        },
        "ai_spend_alert": {
            **shared,
            "period": "daily",
            "period_name": "today",
            "spent": "52.40",
            "limit": "50.00",
        },
    }[template_name]
