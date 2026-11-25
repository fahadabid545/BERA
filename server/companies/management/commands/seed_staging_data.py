import io
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from docx import Document

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser
from companies.services import create_company_with_owner
from core.errors import AppError

FAKE_COMPANY_NAME = "Fake Staging Company"
FAKE_OWNER_EMAIL = "owner@example.test"
FAKE_ADMIN_EMAIL = "admin@example.test"
FAKE_CANDIDATES = [
    ("Fake Candidate One", "Fake Backend Developer", "Python, Django and PostgreSQL."),
    ("Fake Candidate Two", "Fake Data Analyst", "SQL, spreadsheets and charts."),
    ("Fake Candidate Three", "Fake Support Agent", "Customer chat and ticket handling."),
]


def require_staging():
    """Fake data goes only into staging: production holds real people, and development has its
    own command with fixed passwords."""
    if settings.APP_ENV != "staging":
        raise AppError(
            "staging_only", "This command only runs when APP_ENV=staging.", status_code=403
        )


def fake_cv(name, title, skills):
    """A small Word file that says plainly it is fake. No real person, address or number."""
    document = Document()
    document.add_heading(name, level=1)
    document.add_paragraph(
        f"{title}. This is a made-up CV for testing. Contact: {FAKE_OWNER_EMAIL}"
    )
    document.add_paragraph(f"Skills: {skills}")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Create a fake admin, company and fake CVs in staging. Staging holds only fake data."

    def handle(self, *args, **options):
        require_staging()
        passwords = {}
        if not AdminUser.objects.filter(email=FAKE_ADMIN_EMAIL).exists():
            passwords["admin"] = secrets.token_urlsafe(18)
            admin = AdminUser(name="Fake Admin", email=FAKE_ADMIN_EMAIL, role=AdminUser.Role.SUPER)
            admin.set_password(passwords["admin"])
            admin.save()
        if not CompanyUser.objects.filter(email=FAKE_OWNER_EMAIL).exists():
            # Random passwords: staging is on the internet, so no fixed, known password.
            passwords["owner"] = secrets.token_urlsafe(18)
            create_company_with_owner(
                company_name=FAKE_COMPANY_NAME,
                country="ZZ",
                owner_name="Fake Company Owner",
                owner_email=FAKE_OWNER_EMAIL,
                password=passwords["owner"],
                email_verified=True,
            )
        self.add_fake_cvs()
        for who, password in passwords.items():
            self.stdout.write(f"New fake {who} password (shown once): {password}")
        self.stdout.write("Fake staging data is ready.")

    def give_fake_company_a_plan(self, company):
        """The fake company needs a plan to upload: the first active one, free for a month."""
        from plans.models import Plan
        from plans.subscriptions import get_subscription, grant_free

        if get_subscription(company.pk).plan_id:
            return True
        plan = Plan.objects.filter(status="active").order_by("id").first()
        if plan is None:
            return False
        admin = AdminUser.objects.get(email=FAKE_ADMIN_EMAIL)
        grant_free(
            company.pk,
            plan,
            period_end=timezone.now() + timedelta(days=30),
            by=admin,
            reason="Fake staging data",
        )
        return True

    def add_fake_cvs(self):
        from cvs.service import upload_cvs
        from projects.models import Project
        from projects.service import create_project

        company = Company.objects.get(name=FAKE_COMPANY_NAME)
        owner = CompanyUser.objects.get(company=company, email=FAKE_OWNER_EMAIL)
        if Project.objects.filter(company=company).exists():
            return
        if not self.give_fake_company_a_plan(company):
            self.stdout.write("Create a plan in the admin panel, then run this again for the CVs.")
            return
        project = create_project(
            owner,
            "Fake Staging Project",
            "A made-up job for testing.",
            acknowledge_warnings=True,
        )
        files = []
        for name, title, skills in FAKE_CANDIDATES:
            data = fake_cv(name, title, skills)
            files.append((f"{name.replace(' ', '-')}.docx", len(data), lambda data=data: data))
        upload_cvs(owner, project, files)
