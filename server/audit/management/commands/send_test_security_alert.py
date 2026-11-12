from django.core.management.base import BaseCommand

from audit.alerts import send_test_alert


class Command(BaseCommand):
    help = "Email a test security alert to every active super admin, to check delivery."

    def handle(self, *args, **options):
        sent = send_test_alert()
        self.stdout.write(f"Test alert queued for {sent} super admin(s).")
