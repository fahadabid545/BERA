from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from companies.models import Company
from core.development_only import require_development

# Obviously fake, development-only accounts. Passwords are set only when an
# account is first created, so running this again never overwrites changes.
FAKE_ADMIN = {
    "username": "fake-admin",
    "email": "admin@example.test",
    "password": "FAKE-admin-password-dev-only",
}
FAKE_COMPANY_OWNER = {
    "username": "fake-company-owner",
    "email": "owner@example.test",
    "password": "FAKE-company-password-dev-only",
}
FAKE_COMPANY_NAME = "Fake Test Company"


class Command(BaseCommand):
    help = "Create a fake admin and a fake company for local development."

    def handle(self, *args, **options):
        require_development()
        user_model = get_user_model()
        _create_user(user_model, FAKE_ADMIN, is_staff=True, is_superuser=True)
        owner = _create_user(user_model, FAKE_COMPANY_OWNER)
        Company.objects.get_or_create(name=FAKE_COMPANY_NAME, defaults={"owner": owner})
        self.stdout.write("Fake development data is ready.")


def _create_user(user_model, account, **flags):
    user, created = user_model.objects.get_or_create(
        username=account["username"], defaults={"email": account["email"], **flags}
    )
    if created:
        user.set_password(account["password"])
        user.save()
    return user
