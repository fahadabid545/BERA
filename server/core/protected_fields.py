"""Model fields for personal data: one stores it encrypted, one lets it be found by a hash.

    email = EncryptedTextField(purpose="candidate.email")
    email_lookup = LookupHashField(of="email", purpose="candidate.email", normalize=normalize_email)

    Candidate.objects.filter(email_lookup="Jo@Example.com")   # finds jo@example.com too

The hash column is filled in on every save. The encrypted column cannot be searched at all.
Changing a purpose, a key or a normaliser makes existing rows unreadable or unfindable, so
treat them as fixed once data exists.
"""

from django.db import models
from django.db.models.lookups import Exact

from .field_protection import decrypt_text, encrypt_text, lookup_hash


class EncryptedTextField(models.TextField):
    def __init__(self, *args, purpose, **kwargs):
        self.purpose = purpose
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, {**kwargs, "purpose": self.purpose}

    def get_prep_value(self, value):
        if value is None:
            return None
        return encrypt_text(str(value), self.purpose)

    def from_db_value(self, value, expression, connection):
        return None if value is None else decrypt_text(value, self.purpose)

    def get_lookup(self, lookup_name):
        # A random nonce means an equality search would silently find nothing. Fail loudly
        # and point to the hash field instead.
        if lookup_name != "isnull":
            return None
        return super().get_lookup(lookup_name)


class LookupHashField(models.CharField):
    def __init__(self, *, of, purpose, normalize, **kwargs):
        self.of, self.purpose, self.normalize = of, purpose, normalize
        kwargs.setdefault("max_length", 64)  # a SHA-256 hash in hexadecimal
        kwargs.setdefault("db_index", True)
        kwargs.setdefault("editable", False)
        kwargs.setdefault("null", True)
        super().__init__(**kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs.update(of=self.of, purpose=self.purpose, normalize=self.normalize)
        return name, path, args, kwargs

    def hash_of(self, plain_text):
        if plain_text is None or not str(plain_text).strip():
            return None
        return lookup_hash(self.normalize(str(plain_text)), self.purpose)

    def pre_save(self, model_instance, add):
        digest = self.hash_of(getattr(model_instance, self.of))
        setattr(model_instance, self.attname, digest)
        return digest

    def get_lookup(self, lookup_name):
        if lookup_name not in ("exact", "isnull"):
            return None
        return super().get_lookup(lookup_name)


@LookupHashField.register_lookup
class MatchesPlainValue(Exact):
    """`field=value` compares the hash of the value, so callers pass the plain text."""

    lookup_name = "exact"

    def get_prep_lookup(self):
        return self.lhs.output_field.hash_of(self.rhs)
