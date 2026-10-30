from django.core.management.base import BaseCommand

from core.development_only import require_development
from core.errors import AppError
from emailing.catalog import CATALOG
from emailing.models import OutgoingEmail
from emailing.samples import sample_values
from emailing.service import send_email

DEVELOPER_ADDRESS = "developer@example.test"


class Command(BaseCommand):
    help = "Send one example of every system email to the development inbox (.dev-inbox)."

    def handle(self, *args, **options):
        require_development()
        saved = 0
        for template_name in CATALOG:
            email = send_email(
                template_name, DEVELOPER_ADDRESS, now=True, **sample_values(template_name)
            )
            saved += bool(email and email.status == OutgoingEmail.Status.SENT)
        if saved < len(CATALOG):
            raise AppError(
                "test_emails_not_saved",
                f"Only {saved} of {len(CATALOG)} example emails were saved. "
                "Is the database migrated (python manage.py migrate)?",
                status_code=500,
            )
        self.stdout.write(f"{saved} example emails saved in the development inbox.")
