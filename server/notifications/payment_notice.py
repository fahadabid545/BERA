"""The email for a failed renewal payment. It is required, so nobody can switch it off. It lives
apart from the other billing emails because the plans app calls it (they read the plans app)."""

from emailing.links import build_link

from .kinds import PAYMENT_FAILED
from .service import notify


def payment_failed(subscription, owner, message):
    """One email each time the subscription goes past due (the date it did is the occasion)."""
    return notify(
        subscription.company_id,
        PAYMENT_FAILED,
        subscription.past_due_since.isoformat(),
        [owner],
        "payment_problem",
        message=message,
        link=build_link("/company/billing"),
    )
