from django.db import migrations, models


def number_existing_candidates(apps, schema_editor):
    """Existing candidates are numbered in the order they were added, project by project."""
    Candidate = apps.get_model("cvs", "Candidate")
    last_in_project = {}
    for candidate in Candidate.objects.order_by("created_at", "pk"):
        number = last_in_project.get(candidate.project_id, 0) + 1
        last_in_project[candidate.project_id] = number
        Candidate.objects.filter(pk=candidate.pk).update(number=number)


class Migration(migrations.Migration):

    dependencies = [
        ("cvs", "0027_stage_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidate",
            name="number",
            field=models.PositiveIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.RunPython(number_existing_candidates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="candidate",
            constraint=models.UniqueConstraint(
                fields=("project", "number"), name="candidate_number_in_project"
            ),
        ),
    ]
