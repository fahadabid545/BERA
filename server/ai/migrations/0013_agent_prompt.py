from django.db import migrations

from ai.default_prompts import AGENT_PROMPT


def add_the_agent_prompt(apps, schema_editor):
    """Version 2 of the "ask" prompt is for the company agent; version 1 stays in the history."""
    PromptVersion = apps.get_model("ai", "PromptVersion")
    PromptCounter = apps.get_model("ai", "PromptCounter")
    PromptVersion.objects.get_or_create(kind="ask", number=2, defaults={"text": AGENT_PROMPT})
    PromptCounter.objects.update_or_create(kind="ask", defaults={"last_number": 2})


class Migration(migrations.Migration):
    dependencies = [("ai", "0012_chatbot_calls")]

    operations = [migrations.RunPython(add_the_agent_prompt, migrations.RunPython.noop)]
