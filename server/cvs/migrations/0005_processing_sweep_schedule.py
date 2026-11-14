from django.db import migrations

JOB = "cvs.processing.sweep"
NAME = "Sweep CV processing"
MINUTES = "I"


def schedule_job(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.update_or_create(
        name=NAME, defaults={"func": JOB, "schedule_type": MINUTES, "minutes": 1, "repeats": -1}
    )


def unschedule_job(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("cvs", "0004_processing"), ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more")]
    operations = [migrations.RunPython(schedule_job, unschedule_job)]
