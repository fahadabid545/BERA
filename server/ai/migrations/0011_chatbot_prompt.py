from django.db import migrations, models

from ai.default_prompts import CHATBOT_PROMPT


def add_the_first_chatbot_prompt(apps, schema_editor):
    PromptVersion = apps.get_model("ai", "PromptVersion")
    PromptCounter = apps.get_model("ai", "PromptCounter")
    PromptVersion.objects.get_or_create(kind="chatbot", number=1, defaults={"text": CHATBOT_PROMPT})
    PromptCounter.objects.get_or_create(kind="chatbot", defaults={"last_number": 1})


class Migration(migrations.Migration):
    dependencies = [("ai", "0010_ask_bera")]

    operations = [
        migrations.RemoveConstraint(model_name="promptversion", name="prompt_kind_is_known"),
        migrations.AlterField(
            model_name="promptversion",
            name="kind",
            field=models.CharField(
                choices=[
                    ("reading", "Reading"),
                    ("scoring", "Scoring"),
                    ("ask", "Ask"),
                    ("chatbot", "Chatbot"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="promptversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind__in", ["reading", "scoring", "ask", "chatbot"])),
                name="prompt_kind_is_known",
            ),
        ),
        migrations.RunPython(add_the_first_chatbot_prompt, migrations.RunPython.noop),
    ]
