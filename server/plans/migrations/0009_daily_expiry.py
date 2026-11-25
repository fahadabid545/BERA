from django.db import migrations

JOB = "plans.subscriptions.expire_lapsed_subscriptions"
NAME = "End subscriptions whose period or grace period is over"
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
        ("plans", "0008_plan_changes"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]
    operations = [migrations.RunPython(schedule_job, unschedule_job)]
