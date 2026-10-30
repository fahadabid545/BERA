import base64
import json

import jwt
import pytest
from django.conf import settings
from rest_framework.exceptions import NotAuthenticated

from signin import service
from signin.tests.helpers import forge
from signin.tokens import ACCESS, REFRESH, read_token

pytestmark = pytest.mark.django_db
OTHER_SECRET = "test-only-attackers-guess-long-enough-123"


def accepted(token, kind="company", token_type=ACCESS):
    return read_token(token, kind=kind, token_type=token_type)


def refused(token, kind="company", token_type=ACCESS):
    with pytest.raises(NotAuthenticated):
        read_token(token, kind=kind, token_type=token_type)


def test_a_well_formed_token_is_accepted():
    assert accepted(forge())["sub"] == "7"


def unsigned(claims):
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none', 'typ': 'JWT'})}.{part(claims)}."


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
def test_forged_tokens_fail():
    valid_claims = jwt.decode(forge(), options={"verify_signature": False})
    for token in [
        forge(secret=OTHER_SECRET),  # signed with a guessed key
        unsigned({**valid_claims, "iat": 1, "exp": 4102444800}),  # the "none" method
        forge(algorithm="HS512"),  # another method, even with the right key
        "not.a.token",
        "",
        "a" * 5000,
    ]:
        refused(token)


def test_altered_tokens_fail():
    token = forge()
    header, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["role"] = "member"
    claims["sub"] = "1"
    changed = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    refused(f"{header}.{changed}.{signature}")
    refused(token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB"))


def test_expired_tokens_fail():
    refused(forge(issued_ago=3600, lifetime=900))


def test_wrong_audience_and_issuer_fail():
    refused(forge(aud="bera-admin"))
    refused(forge(aud="somewhere-else"))
    refused(forge(iss="someone-else"))


def test_a_company_token_cannot_be_read_as_an_admin_token_and_back():
    refused(forge("company"), kind="admin")
    refused(forge("admin"), kind="company")
    # Even signed with the other kind's key and claiming the other audience's role mix:
    refused(forge("admin", secret=settings.TOKEN_SIGNING_SECRETS["company"]), kind="company")


@pytest.mark.parametrize(
    "missing", ["exp", "iat", "iss", "aud", "sub", "jti", "sid", "typ", "role"]
)
def test_tokens_missing_a_required_claim_fail(missing):
    refused(forge(**{missing: None}))


def test_other_token_types_and_shapes_fail():
    refused(forge(typ="refresh"))  # a refresh token is not an access token
    refused(forge(typ="access"), token_type=REFRESH)
    refused(forge(role="superuser"))  # not a company role
    refused(forge("admin", role="owner"), kind="admin")  # a company role on an admin token
    refused(forge(sub="seven"))
    refused(forge(sid="not-a-uuid"))
    refused(forge(cid=None))  # company token without a company
    refused(forge("admin", cid=3), kind="admin")  # admin token with a company
    refused(forge(cid="3"))


def test_small_clock_differences_are_tolerated_but_large_ones_are_not():
    accepted(forge(issued_ago=900 + 10, lifetime=900))  # expired 10 seconds ago
    accepted(forge(issued_ago=-10))  # issued 10 seconds "in the future"
    refused(forge(issued_ago=900 + 600, lifetime=900))
    refused(forge(issued_ago=-600))


def test_a_real_token_holds_only_the_allowed_claims():
    issued = service.start_session(user_id=7, role="owner", company_id=3, kind="company")
    claims = jwt.decode(issued.access_token, options={"verify_signature": False})
    assert set(claims) == {"iss", "aud", "sub", "role", "cid", "sid", "jti", "typ", "iat", "exp"}
    assert claims["exp"] - claims["iat"] == 15 * 60


def test_the_signing_secrets_are_long_and_different():
    secrets_by_kind = settings.TOKEN_SIGNING_SECRETS
    assert secrets_by_kind["company"] != secrets_by_kind["admin"]
    assert all(len(secret) >= 32 for secret in secrets_by_kind.values())
