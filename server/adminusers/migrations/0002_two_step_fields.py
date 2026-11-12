import core.protected_fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("adminusers", "0001_initial")]

    operations = [
        migrations.RenameField("adminuser", "two_step_set", "two_step_enabled"),
        migrations.AddField(
            "adminuser",
            "two_step_secret",
            core.protected_fields.EncryptedTextField(
                default="", purpose="adminuser.two_step_secret"
            ),
        ),
        migrations.AddField(
            "adminuser", "two_step_last_step", models.BigIntegerField(null=True)
        ),
    ]
