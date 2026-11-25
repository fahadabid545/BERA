"""The emails a person can get besides the account ones (sign-in, password, invites).

An optional kind can be switched off by each person for themselves. A required one is billing
or security: it is always sent, and the choices screen shows it without a switch.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    name: str
    label: str
    required: bool


BATCH_FINISHED = "batch_finished"
USAGE_WARNING = "usage_warning"
USAGE_LIMIT_REACHED = "usage_limit_reached"
SUBSCRIPTION_ENDING = "subscription_ending"
SUBSCRIPTION_RENEWING = "subscription_renewing"
PAYMENT_FAILED = "payment_failed"

KINDS = (
    Kind(BATCH_FINISHED, "Finished uploads", required=False),
    Kind(USAGE_WARNING, "Usage warnings", required=False),
    Kind(USAGE_LIMIT_REACHED, "Usage limit reached", required=False),
    Kind(SUBSCRIPTION_ENDING, "Subscription ending", required=True),
    Kind(SUBSCRIPTION_RENEWING, "Subscription renewing", required=True),
    Kind(PAYMENT_FAILED, "Payment failed", required=True),
)
BY_NAME = {kind.name: kind for kind in KINDS}
