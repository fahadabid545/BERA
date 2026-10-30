from django.core.management.base import BaseCommand

from adminusers.models import AdminUser
from companies.models import CompanyUser
from companies.services import create_company_with_owner
from core.development_only import require_development

# Obviously fake, development-only accounts. Passwords are set only when an
# account is first created, so running this again never overwrites changes.
FAKE_ADMIN = {
    "name": "Fake Admin",
    "email": "admin@example.test",
    "password": "FAKE-admin-password-dev-only",
}
FAKE_COMPANY_OWNER = {
    "name": "Fake Company Owner",
    "email": "owner@example.test",
    "password": "FAKE-company-password-dev-only",
}
FAKE_COMPANY_NAME = "Fake Test Company"


class Command(BaseCommand):
    help = "Create a fake admin and a fake company for local development."

    def handle(self, *args, **options):
        require_development()
        _create_admin()
        if not CompanyUser.objects.filter(email=FAKE_COMPANY_OWNER["email"]).exists():
            create_company_with_owner(
                company_name=FAKE_COMPANY_NAME,
                country="ZZ",
                owner_name=FAKE_COMPANY_OWNER["name"],
                owner_email=FAKE_COMPANY_OWNER["email"],
                password=FAKE_COMPANY_OWNER["password"],
                email_verified=True,
            )
        self.stdout.write("Fake development data is ready.")


def _create_admin():
    if AdminUser.objects.filter(email=FAKE_ADMIN["email"]).exists():
        return
    admin = AdminUser(name=FAKE_ADMIN["name"], email=FAKE_ADMIN["email"], role=AdminUser.Role.SUPER)
    admin.set_password(FAKE_ADMIN["password"])
    admin.save()
