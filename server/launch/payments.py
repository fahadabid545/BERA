"""Item 6: live payments. The server can see the mode and the webhook secret; taxes, the billing
portal and the test-mode trials are decisions or Stripe settings only the owner can confirm."""

from django.conf import settings

from plans.stripe_client import LIVE_KEY_PREFIXES

from .results import item, not_ok, ok, owner


def live_payments(_context):
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    parts = []
    if key.startswith(LIVE_KEY_PREFIXES) and settings.STRIPE_ALLOW_LIVE_KEYS:
        parts.append(ok("A live Stripe key is in use, allowed by the explicit flag."))
    else:
        parts.append(
            not_ok(
                "Live payments are not on: needs a live Stripe key and "
                "STRIPE_ALLOW_LIVE_KEYS=true in production."
            )
        )
    if not (settings.STRIPE_WEBHOOK_SECRET or "").strip():
        parts.append(not_ok("The Stripe webhook secret is not set."))
    parts += [
        owner("Taxes (BERA-170) are decided and written down before going live."),
        owner("The Stripe webhook receives events (send a test event from Stripe)."),
        owner("The Stripe billing portal allows card updates and invoices only."),
        owner(
            "A test payment, a refund and a failed payment were tried in test mode and "
            "behaved correctly."
        ),
    ]
    return item(6, "Live payments, taxes, webhook and billing portal", parts)
