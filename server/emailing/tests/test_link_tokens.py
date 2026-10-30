import hashlib
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from emailing.link_tokens import issue_link_token
from emailing.models import LinkToken

pytestmark = pytest.mark.django_db


def test_a_token_is_random_long_and_url_safe():
    tokens = {issue_link_token("verify_email", 1, 24) for _ in range(20)}
    assert len(tokens) == 20
    assert all(
        len(token) >= 40 and token.replace("-", "").replace("_", "").isalnum() for token in tokens
    )


def test_only_the_hash_is_stored():
    token = issue_link_token("verify_email", 7, 24)
    stored = LinkToken.objects.get()
    assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored.token_hash
    assert stored.used_at is None and stored.subject_id == 7


def test_it_expires_after_the_given_hours():
    issue_link_token("reset_password", 1, 1)
    stored = LinkToken.objects.get()
    assert timedelta(minutes=59) < stored.expires_at - timezone.now() <= timedelta(hours=1)


def test_the_purpose_is_part_of_the_token():
    issue_link_token("team_invite", 1, 24)
    assert LinkToken.objects.get().purpose == "team_invite"


def test_the_database_refuses_an_unknown_purpose():
    with pytest.raises(IntegrityError), transaction.atomic():
        issue_link_token("log_me_in", 1, 24)
