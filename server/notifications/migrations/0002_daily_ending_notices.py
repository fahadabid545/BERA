from django.db import migrations

JOB = "notifications.billing_notices.send_ending_notices"
NAME = "Email owners whose subscription is about to end"
DAILY = "D"


def schedule_job(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.update_or_create(
        name=NAME, defaults={"func": JOB, "schedule_type": DAILY, "repeats": -1}
    )


def unschedule_job(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]
    operations = [migrations.RunPython(schedule_job, unschedule_job)]
