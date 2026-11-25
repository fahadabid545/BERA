"""The whole launch check, in the order of the README checklist."""

from . import business, operations, payments, reliability, server_checks

CHECKS = (
    business.two_step_reset,
    business.super_admins,
    business.plans,
    business.pricing_page,
    business.legal_pages,
    payments.live_payments,
    reliability.backups,
    reliability.monitoring,
    server_checks.server_protection,
    operations.volume_test,
    operations.ai_ready,
    operations.email_and_names,
    operations.public_side,
    operations.private_beta,
    server_checks.security_review,
)


def run_all(context):
    return [check(context) for check in CHECKS]
