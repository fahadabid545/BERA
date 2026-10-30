import pytest
from django.core.cache import cache
from django.core.management.color import no_style
from django.db import connection

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser

# The ids the sign-in tests use for people. Sign-ins only work for accounts that exist.
TEST_USER_IDS = range(1, 10)


@pytest.fixture(autouse=True)
def fresh_rate_limit_counts():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def accounts(request):
    if request.node.get_closest_marker("django_db") is None:
        return
    request.getfixturevalue("db")
    company = Company.objects.create(name="Fake Sign-in Tests Ltd")
    CompanyUser.objects.bulk_create(
        [
            CompanyUser(
                id=user_id,
                company=company,
                name=f"Fake Person {user_id}",
                email=f"person{user_id}@example.test",
                role=CompanyUser.Role.MEMBER,
            )
            for user_id in TEST_USER_IDS
        ]
    )
    AdminUser.objects.bulk_create(
        [
            AdminUser(
                id=user_id, name=f"Fake Admin {user_id}", email=f"admin{user_id}@example.test"
            )
            for user_id in TEST_USER_IDS
        ]
    )
    # The ids above were chosen by hand, so later automatic ids must start after them.
    with connection.cursor() as cursor:
        for statement in connection.ops.sequence_reset_sql(
            no_style(), [Company, CompanyUser, AdminUser]
        ):
            cursor.execute(statement)
