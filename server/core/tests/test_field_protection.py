import base64

import pytest
from django.core.exceptions import FieldError
from django.db import connection
from django.db.migrations.writer import MigrationWriter

from core.errors import AppError
from core.field_protection import (
    decrypt_text,
    encrypt_text,
    lookup_hash,
    normalize_email,
    normalize_phone,
)
from core.protected_fields import LookupHashField
from core.tests.protected_model import ProtectedPerson

PURPOSE = "test_person.email"
EMAIL = "jo.reader@example.com"
PHONE = "+1 (555) 010-0100"


@pytest.fixture
def people_table(db):
    with connection.schema_editor() as editor:
        editor.create_model(ProtectedPerson)
    yield
    with connection.schema_editor() as editor:
        editor.delete_model(ProtectedPerson)


def raw_row(person):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT email, email_lookup, phone FROM protected_field_tests_protectedperson"
            " WHERE id = %s",
            [person.pk],
        )
        return cursor.fetchone()


class TestEncryption:
    @pytest.mark.parametrize("text", [EMAIL, "", "Zoë Ångström ✓", "x" * 5000])
    def test_a_value_reads_back_exactly(self, text):
        assert decrypt_text(encrypt_text(text, PURPOSE), PURPOSE) == text

    def test_the_stored_text_does_not_contain_the_value(self):
        stored = encrypt_text(EMAIL, PURPOSE)
        assert EMAIL not in stored and "example" not in stored
        assert EMAIL.encode() not in base64.urlsafe_b64decode(stored)

    def test_the_same_value_is_stored_differently_each_time(self):
        assert encrypt_text(EMAIL, PURPOSE) != encrypt_text(EMAIL, PURPOSE)

    def test_a_value_copied_to_another_column_cannot_be_read_there(self):
        with pytest.raises(AppError) as caught:
            decrypt_text(encrypt_text(EMAIL, PURPOSE), "test_person.phone")
        assert caught.value.code == "protected_value_unreadable"

    def test_the_wrong_key_cannot_read_a_value(self, settings):
        stored = encrypt_text(EMAIL, PURPOSE)
        settings.FIELD_KEYS = {**settings.FIELD_KEYS, "encryption": "a-different-key-" + "z" * 30}
        with pytest.raises(AppError):
            decrypt_text(stored, PURPOSE)

    @pytest.mark.parametrize("damage", ["", "not base64 !!", "AAAA", "AQ=="])
    def test_damaged_text_is_refused_without_revealing_why(self, damage):
        with pytest.raises(AppError) as caught:
            decrypt_text(damage, PURPOSE)
        assert caught.value.message == "Something went wrong."
        assert caught.value.status_code == 500

    def test_a_changed_byte_is_noticed(self):
        raw = bytearray(base64.urlsafe_b64decode(encrypt_text(EMAIL, PURPOSE)))
        raw[-1] ^= 1
        with pytest.raises(AppError):
            decrypt_text(base64.urlsafe_b64encode(bytes(raw)).decode(), PURPOSE)


class TestLookupHash:
    def test_the_same_value_gives_the_same_hash(self):
        assert lookup_hash(EMAIL, PURPOSE) == lookup_hash(EMAIL, PURPOSE)

    def test_the_hash_is_hexadecimal_and_hides_the_value(self):
        digest = lookup_hash(EMAIL, PURPOSE)
        assert len(digest) == 64 and int(digest, 16) >= 0
        assert "example" not in digest

    def test_other_values_other_purposes_and_other_keys_give_other_hashes(self, settings):
        original = lookup_hash(EMAIL, PURPOSE)
        assert lookup_hash("someone.else@example.com", PURPOSE) != original
        assert lookup_hash(EMAIL, "test_person.phone") != original
        settings.FIELD_KEYS = {**settings.FIELD_KEYS, "hash": "a-different-key-" + "z" * 30}
        assert lookup_hash(EMAIL, PURPOSE) != original

    def test_changing_the_encryption_key_leaves_hashes_alone(self, settings):
        original = lookup_hash(EMAIL, PURPOSE)
        settings.FIELD_KEYS = {**settings.FIELD_KEYS, "encryption": "a-different-key-" + "z" * 30}
        assert lookup_hash(EMAIL, PURPOSE) == original

    def test_changing_the_hash_key_leaves_encryption_alone(self, settings):
        stored = encrypt_text(EMAIL, PURPOSE)
        settings.FIELD_KEYS = {**settings.FIELD_KEYS, "hash": "a-different-key-" + "y" * 30}
        assert decrypt_text(stored, PURPOSE) == EMAIL


class TestNormalising:
    @pytest.mark.parametrize(
        ("typed", "wanted"),
        [(" Jo.Reader@Example.com ", EMAIL), ("JO.READER@EXAMPLE.COM", EMAIL)],
    )
    def test_emails_ignore_case_and_outer_spaces(self, typed, wanted):
        assert normalize_email(typed) == wanted

    @pytest.mark.parametrize(
        ("typed", "wanted"),
        [
            ("+1 (555) 010-0100", "+15550100100"),
            ("+15550100100", "+15550100100"),
            ("555.010.0100", "5550100100"),
            ("  +44 20 7946 0000 ", "+442079460000"),
        ],
    )
    def test_phone_numbers_keep_only_digits_and_a_leading_plus(self, typed, wanted):
        assert normalize_phone(typed) == wanted


@pytest.mark.django_db
class TestOnARealTable:
    @pytest.fixture(autouse=True)
    def _table(self, people_table):
        pass

    def test_values_read_back_and_are_unreadable_in_the_database(self):
        person = ProtectedPerson.objects.create(email=EMAIL, phone=PHONE)
        assert ProtectedPerson.objects.get(pk=person.pk).email == EMAIL
        assert ProtectedPerson.objects.get(pk=person.pk).phone == PHONE
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT t::text FROM protected_field_tests_protectedperson t WHERE id = %s",
                [person.pk],
            )
            whole_row = cursor.fetchone()[0]
        assert "example.com" not in whole_row and "555" not in whole_row
        assert EMAIL not in whole_row and PHONE not in whole_row

    def test_the_stored_columns_hold_ciphertext_and_a_hash(self):
        person = ProtectedPerson.objects.create(email=EMAIL, phone=PHONE)
        email, email_lookup, phone = raw_row(person)
        assert email != EMAIL and phone != PHONE
        assert email_lookup == lookup_hash(EMAIL, "test_person.email")

    def test_a_person_is_found_by_the_plain_value_in_any_spelling(self):
        person = ProtectedPerson.objects.create(email=EMAIL, phone=PHONE)
        assert ProtectedPerson.objects.get(email_lookup="  Jo.READER@example.com ") == person
        assert ProtectedPerson.objects.get(phone_lookup="+1 555 010 0100") == person

    def test_an_unknown_value_finds_nobody(self):
        ProtectedPerson.objects.create(email=EMAIL)
        assert not ProtectedPerson.objects.filter(email_lookup="nobody@example.com").exists()

    def test_the_same_email_in_two_rows_is_found_as_a_duplicate(self):
        ProtectedPerson.objects.create(email=EMAIL)
        ProtectedPerson.objects.create(email=EMAIL.upper())
        assert ProtectedPerson.objects.filter(email_lookup=EMAIL).count() == 2

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_an_empty_value_has_no_hash_and_is_found_by_null(self, empty):
        person = ProtectedPerson.objects.create(email=empty)
        assert raw_row(person)[1] is None
        assert ProtectedPerson.objects.filter(email_lookup__isnull=True).count() == 1

    def test_changing_the_value_changes_what_it_is_found_by(self):
        person = ProtectedPerson.objects.create(email=EMAIL)
        person.email = "new.address@example.com"
        person.save()
        assert not ProtectedPerson.objects.filter(email_lookup=EMAIL).exists()
        assert ProtectedPerson.objects.filter(email_lookup="new.address@example.com").exists()

    def test_the_encrypted_column_cannot_be_searched(self):
        with pytest.raises(FieldError):
            ProtectedPerson.objects.filter(email=EMAIL).exists()

    @pytest.mark.parametrize("lookup", ["contains", "startswith", "in", "gt", "iexact"])
    def test_only_an_exact_match_works_on_the_hash(self, lookup):
        value = [EMAIL] if lookup == "in" else EMAIL
        with pytest.raises(FieldError):
            ProtectedPerson.objects.filter(**{f"email_lookup__{lookup}": value}).exists()

    def test_the_fields_can_be_written_into_a_migration(self):
        for name in ("email", "email_lookup"):
            field = ProtectedPerson._meta.get_field(name)
            text, _ = MigrationWriter.serialize(field)
            assert "purpose=" in text
        assert (
            "normalize_email"
            in MigrationWriter.serialize(ProtectedPerson._meta.get_field("email_lookup"))[0]
        )
        assert isinstance(ProtectedPerson._meta.get_field("email_lookup"), LookupHashField)
