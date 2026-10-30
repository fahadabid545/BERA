from datetime import timedelta

import pytest
from django.utils import timezone

from core.errors import AppError
from emailing.link_tokens import consume_link_token, issue_link_token, retire_link_tokens
from emailing.models import LinkToken

pytestmark = pytest.mark.django_db


def refused(token, purpose="verify_email"):
    with pytest.raises(AppError) as caught:
        consume_link_token(token, purpose)
    return caught.value


def test_a_good_token_returns_who_it_was_for_and_is_marked_used():
    token = issue_link_token("verify_email", 42, 24)
    assert consume_link_token(token, "verify_email") == 42
    assert LinkToken.objects.get().used_at is not None


def test_it_works_only_once():
    token = issue_link_token("verify_email", 42, 24)
    consume_link_token(token, "verify_email")
    error = refused(token)
    assert (error.code, error.message) == ("link_used", "This link has already been used.")


def test_it_stops_working_when_it_expires():
    token = issue_link_token("verify_email", 42, 24)
    LinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    error = refused(token)
    assert (error.code, error.message) == ("link_expired", "This link has expired.")
    assert LinkToken.objects.get().used_at is None


def test_a_made_up_token_is_not_valid():
    error = refused("x" * 43)
    assert (error.code, error.message) == ("link_invalid", "This link is not valid.")


def test_a_token_cannot_be_used_for_another_purpose():
    token = issue_link_token("reset_password", 42, 1)
    assert refused(token, "verify_email").code == "link_invalid"
    assert LinkToken.objects.get().used_at is None  # the attempt did not spend it
    assert consume_link_token(token, "reset_password") == 42


def test_a_used_and_expired_token_says_used():
    token = issue_link_token("verify_email", 42, 24)
    consume_link_token(token, "verify_email")
    LinkToken.objects.update(expires_at=timezone.now() - timedelta(hours=1))
    assert refused(token).code == "link_used"


def test_two_people_clicking_at_once_cannot_both_succeed(monkeypatch):
    token = issue_link_token("verify_email", 42, 24)
    from emailing import link_tokens

    original = link_tokens.LinkToken.objects.filter

    def rival_gets_there_first(*args, **kwargs):
        queryset = original(*args, **kwargs)
        if kwargs.get("used_at__isnull"):  # the moment just before the final update
            LinkToken.objects.filter(token_hash=queryset.first().token_hash).update(
                used_at=timezone.now()
            )
        return queryset

    monkeypatch.setattr(link_tokens.LinkToken.objects, "filter", rival_gets_there_first)
    assert refused(token).code == "link_used"


def test_a_newer_link_cancels_the_older_ones_for_the_same_person_and_purpose():
    old = issue_link_token("verify_email", 42, 24)
    other_person = issue_link_token("verify_email", 43, 24)
    other_purpose = issue_link_token("reset_password", 42, 1)
    retire_link_tokens("verify_email", 42)
    assert refused(old).code == "link_used"
    assert consume_link_token(other_person, "verify_email") == 43
    assert consume_link_token(other_purpose, "reset_password") == 42
