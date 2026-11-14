from django.db import migrations

import core.protected_fields
from core.field_protection import decrypt_text, encrypt_text

FIELDS = ("name", "email", "phone", "address")
TABLE = "cvs_cvcontact"


def _purpose(field):
    return f"cv_contact.{field}"


def encrypt_existing_rows(apps, schema_editor):
    """The columns held plain text until now. Raw SQL, because the model's own fields would
    try to decrypt what is still plain."""
    columns = ", ".join(FIELDS)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT id, {columns} FROM {TABLE}")  # noqa: S608 (fixed names)
        rows = cursor.fetchall()
        for row_id, *values in rows:
            sealed = [encrypt_text(value or "", _purpose(field)) for field, value in zip(FIELDS, values)]
            assignments = ", ".join(f"{field} = %s" for field in FIELDS)
            cursor.execute(f"UPDATE {TABLE} SET {assignments} WHERE id = %s", [*sealed, row_id])  # noqa: S608


def decrypt_existing_rows(apps, schema_editor):
    columns = ", ".join(FIELDS)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT id, {columns} FROM {TABLE}")  # noqa: S608
        for row_id, *values in cursor.fetchall():
            plain = [decrypt_text(value, _purpose(field)) for field, value in zip(FIELDS, values)]
            assignments = ", ".join(f"{field} = %s" for field in FIELDS)
            cursor.execute(f"UPDATE {TABLE} SET {assignments} WHERE id = %s", [*plain, row_id])  # noqa: S608


def encrypted_field(field):
    return core.protected_fields.EncryptedTextField(blank=True, purpose=_purpose(field))


class Migration(migrations.Migration):
    dependencies = [("cvs", "0007_candidates")]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
        *[
            migrations.AlterField(model_name="cvcontact", name=field, field=encrypted_field(field))
            for field in FIELDS
        ],
    ]
