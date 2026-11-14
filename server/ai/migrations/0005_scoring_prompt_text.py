from django.db import migrations

from ai.default_prompts import SCORING_PROMPT, STAND_IN_SCORING_PROMPT


def write_the_first_scoring_prompt(apps, schema_editor):
    """Scoring version 1 was only a stand-in that nothing used. It now holds the instructions for
    judging a CV against each requirement. A version somebody edited is left as it is."""
    PromptVersion = apps.get_model("ai", "PromptVersion")
    PromptVersion.objects.filter(
        kind="scoring", number=1, text=STAND_IN_SCORING_PROMPT
    ).update(text=SCORING_PROMPT)


class Migration(migrations.Migration):
    dependencies = [("ai", "0004_first_prompt_versions")]
    operations = [migrations.RunPython(write_the_first_scoring_prompt, migrations.RunPython.noop)]
