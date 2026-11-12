"""Creating the very first super admin. There is no public admin sign up; this is the only
way in, and it works only while no admin exists at all (a removed admin still counts)."""

from django.db import connection, transaction

from audit.service import record
from core.errors import AppError
from core.field_protection import normalize_email
from core.passwords import password_problems

from .models import AdminUser

ALREADY_SET_UP = "An admin already exists, so the first super admin cannot be created again."


def create_first_super_admin(*, name, email, password):
    problems = password_problems(password)
    if problems:
        raise AppError("weak_password", " ".join(problems), status_code=400)
    with transaction.atomic():
        # Two setups at once must not both succeed: the second waits here until the first is done.
        with connection.cursor() as cursor:
            cursor.execute("LOCK TABLE adminusers_adminuser IN EXCLUSIVE MODE")
        if AdminUser.objects.exists():
            raise AppError("admin_exists", ALREADY_SET_UP, status_code=409)
        admin = AdminUser(name=name, email=normalize_email(email), role=AdminUser.Role.SUPER)
        admin.set_password(password)
        admin.save()
        record("admin.first_super_admin_created", target=admin)
    return admin
