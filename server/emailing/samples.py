"""Example values for every template, used by the development test command and the tests."""

from .links import build_link


def sample_values(template_name):
    link = build_link("/example", token="sample-token-for-development")
    shared = {"name": "Fake Person", "link": link, "when": "1 January 2030, 09:00 UTC"}
    return {
        "verify_email": {**shared, "expires_in_hours": 24},
        "reset_password": {**shared, "expires_in_hours": 1},
        "team_invite": {
            "inviter_name": "Fake Owner",
            "company_name": "Fake Test Company",
            "link": link,
            "expires_in_days": 7,
        },
        "password_changed": shared,
        "email_changed": shared,
        "new_sign_in": {**shared, "device": "Firefox on Windows", "place": "Berlin, Germany"},
        "usage_notice": {
            **shared,
            "title": "You have used 80% of your plan",
            "message": "Your company has used 80% of its included analyses this month.",
        },
        "payment_problem": {
            **shared,
            "message": "We could not take your last payment. Please update your payment method.",
        },
    }[template_name]
