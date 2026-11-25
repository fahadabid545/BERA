from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cvs", "0024_package_without_project")]

    operations = [
        # Turns are only a fairness hint, so the old per-company ones are simply dropped.
        migrations.RunSQL("DELETE FROM cvs_processingturn", migrations.RunSQL.noop),
        migrations.RemoveConstraint(
            model_name="processingturn", name="one_processing_turn_per_company"
        ),
        migrations.AddField(
            model_name="processingturn",
            name="batch_key",
            field=models.UUIDField(default="00000000-0000-0000-0000-000000000000"),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="processingturn",
            constraint=models.UniqueConstraint(
                fields=["batch_key"], name="one_processing_turn_per_batch"
            ),
        ),
    ]
