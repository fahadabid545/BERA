"""A visitor creates a company account and becomes its owner.

Whether or not the email is already registered, the visitor gets the same answer in about
the same time, so sign-up cannot be used to find out which emails have accounts.
"""

import hashlib
import logging

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.utils import timezone

from core import rate_limits
from core.field_protection import normalize_email
from emailing.links import build_link
from emailing.service import send_email

from .models import CompanyUser
from .services import create_company_with_owner
from .verification import send_verification_email

logger = logging.getLogger(__name__)

NEUTRAL_MESSAGE = "If this email can be used, we have sent instructions."


def sign_up(*, company_name, name, email, password, country):
    email = normalize_email(email)
    if _email_is_taken(email) or not _create_account(company_name, name, email, password, country):
        _notify_existing_person(email, password)


def _email_is_taken(email):
    return CompanyUser.objects.filter(email=email).exists()


def _create_account(company_name, name, email, password, country):
    """True when the account was created; False when the email turned out to be taken."""
    try:
        with transaction.atomic():
            _, owner = create_company_with_owner(
                company_name=company_name,
                country=country,
                owner_name=name,
                owner_email=email,
                password=password,
                terms_accepted_at=timezone.now(),
            )
            send_verification_email(owner)
    except IntegrityError:
        return False  # someone signed up with this email at the same moment
    return True


def _notify_existing_person(email, password):
    # Hash anyway: creating an account hashes the password, and a faster answer would
    # show that the email was already taken.
    make_password(password)
    person = CompanyUser.objects.filter(email=email).first()
    if person is None:
        logger.error("A sign-up clashed with an email that then could not be found.")
        return
    subject = "email:" + hashlib.sha256(email.encode("utf-8")).hexdigest()
    if rate_limits.hit(rate_limits.SIGN_UP_NOTICE, subject):
        return  # enough notices to this inbox for now; the visitor still sees the same answer
    send_email("already_registered", email, name=person.name, link=build_link("/login"))
