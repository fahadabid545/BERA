from django.db import migrations

from ai.default_prompts import CV_READING_PROMPT, SCORING_PROMPT

FIRST_VERSIONS = {"reading": CV_READING_PROMPT, "scoring": SCORING_PROMPT}


def add_the_first_versions(apps, schema_editor):
    """Version 1 of each kind: the reading prompt the platform has used so far, and a stand-in
    scoring prompt. Existing projects already pin version 1."""
    PromptVersion = apps.get_model("ai", "PromptVersion")
    PromptCounter = apps.get_model("ai", "PromptCounter")
    for kind, text in FIRST_VERSIONS.items():
        PromptVersion.objects.get_or_create(kind=kind, number=1, defaults={"text": text})
        PromptCounter.objects.get_or_create(kind=kind, defaults={"last_number": 1})


class Migration(migrations.Migration):
    dependencies = [("ai", "0003_promptcounter_promptversion")]
    operations = [migrations.RunPython(add_the_first_versions, migrations.RunPython.noop)]
