"""A throwaway model for the tests, so the fields are proven on a real table.

It lives under an app name that is not installed, so it never reaches the real migrations.
"""

from django.db import models

from core.field_protection import normalize_email, normalize_phone
from core.protected_fields import EncryptedTextField, LookupHashField


class ProtectedPerson(models.Model):
    email = EncryptedTextField(purpose="test_person.email", null=True)
    email_lookup = LookupHashField(
        of="email", purpose="test_person.email", normalize=normalize_email
    )
    phone = EncryptedTextField(purpose="test_person.phone", null=True)
    phone_lookup = LookupHashField(
        of="phone", purpose="test_person.phone", normalize=normalize_phone
    )

    class Meta:
        app_label = "protected_field_tests"
