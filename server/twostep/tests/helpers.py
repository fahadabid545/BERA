import time

import pyotp
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user
from twostep.service import STEP_SECONDS

PASSWORD = "violet-harbour-lantern-92"  # nosecret: fake test value
LOGIN = "/api/auth/company/login/"


def person(email="owner@example.test", company=None, **fields):
    account = make_company_user(
        company, email=email, name="Fake Owner", **{"email_verified": True, **fields}
    )
    account.set_password(PASSWORD)
    account.save()
    return account


def code_at(secret, steps_from_now):
    """The app code for a step before or after now (the server accepts one step of drift)."""
    step = int(time.time()) // STEP_SECONDS + steps_from_now
    return pyotp.TOTP(secret).generate_otp(step)


def log_in(email="owner@example.test", address="203.0.113.10", **headers):
    return APIClient(REMOTE_ADDR=address, **headers).post(
        LOGIN, {"email": email, "password": PASSWORD}, format="json"
    )


def signed_in_client(account, address="203.0.113.10"):
    """A client with a session, signed in the normal way (no two-step in the way)."""
    from signin import service

    issued = service.start_session(
        user_id=account.pk, role=account.role, company_id=account.company_id, kind="company"
    )
    return APIClient(REMOTE_ADDR=address, HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def turn_on(account):
    """Two-step on for a person, the way the Security page does it. Returns (secret, codes)."""
    client = signed_in_client(account)
    secret = client.post("/api/auth/company/two-step/setup/").json()["secret"]
    response = client.post(
        "/api/auth/company/two-step/setup/confirm/", {"code": code_at(secret, 0)}, format="json"
    )
    account.refresh_from_db()
    return secret, response.json()["recovery_codes"]


def make_company_with_members(suffix=""):
    company = make_company()
    owner = person(f"owner{suffix}@example.test", company, role="owner")
    member = person(f"member{suffix}@example.test", company, role="member")
    return company, owner, member
