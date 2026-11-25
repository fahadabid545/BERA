from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cvs", "0025_turns_per_batch")]

    operations = [
        migrations.AddIndex(
            model_name="cvfile",
            index=models.Index(fields=["project", "status"], name="cv_project_status"),
        ),
        migrations.AddIndex(
            model_name="cvfile",
            index=models.Index(fields=["company", "batch_id"], name="cv_company_batch"),
        ),
    ]
