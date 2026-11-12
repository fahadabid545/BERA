import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def fresh_rate_limit_counts():
    cache.clear()
    yield
    cache.clear()
