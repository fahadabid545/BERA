import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

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
    users = get_user_model().objects
    users.bulk_create(
        [users.model(id=user_id, username=f"user-{user_id}") for user_id in TEST_USER_IDS]
    )
