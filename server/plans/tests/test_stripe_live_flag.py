import pytest
from django.test import override_settings

from core.errors import AppError
from plans import stripe_client

TEST_KEY = "sk_test_only9c4e7a1b5d2f8e63"  # nosecret: fake
LIVE_KEY = "sk_live_only9c4e7a1b5d2f8e63"  # nosecret: fake


def test_a_test_key_always_works():
    with override_settings(STRIPE_SECRET_KEY=TEST_KEY, STRIPE_ALLOW_LIVE_KEYS=False):
        assert stripe_client._key() == TEST_KEY


def test_a_live_key_is_refused_without_the_flag():
    with override_settings(STRIPE_SECRET_KEY=LIVE_KEY, STRIPE_ALLOW_LIVE_KEYS=False):
        with pytest.raises(AppError) as caught:
            stripe_client._key()
    assert caught.value.code == "payments_unavailable"


def test_a_live_key_works_only_with_the_flag():
    with override_settings(STRIPE_SECRET_KEY=LIVE_KEY, STRIPE_ALLOW_LIVE_KEYS=True):
        assert stripe_client._key() == LIVE_KEY


def test_something_that_is_not_a_key_is_refused_even_with_the_flag():
    with override_settings(STRIPE_SECRET_KEY="not-a-key", STRIPE_ALLOW_LIVE_KEYS=True):
        with pytest.raises(AppError):
            stripe_client._key()
