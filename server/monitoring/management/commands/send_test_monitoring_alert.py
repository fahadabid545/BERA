from django.core.management.base import BaseCommand

from audit.alerts import MONITORING_KINDS, send_test_alert_for


class Command(BaseCommand):
    help = (
        "Email every active super admin one test message for each monitoring alert, whatever the "
        "cooldown, to check that they arrive. Nothing is recorded as a real event."
    )

    def handle(self, *args, **options):
        for kind in MONITORING_KINDS:
            sent = send_test_alert_for(kind)
        self.stdout.write(f"{len(MONITORING_KINDS)} test alerts queued for {sent} super admin(s).")
