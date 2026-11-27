from django.db import migrations, models

from ai.default_prompts import SUPPORT_PROMPT

PURPOSES = [
    "reading",
    "scoring",
    "requirement_extraction",
    "playground",
    "ask",
    "chatbot",
    "support",
]
PURPOSE_CHOICES = [
    ("reading", "Reading"),
    ("scoring", "Scoring"),
    ("requirement_extraction", "Requirement Extraction"),
    ("playground", "Playground"),
    ("ask", "Ask"),
    ("chatbot", "Chatbot"),
    ("support", "Support"),
]
KINDS = ["reading", "scoring", "ask", "chatbot", "support"]


def add_the_first_support_prompt(apps, schema_editor):
    PromptVersion = apps.get_model("ai", "PromptVersion")
    PromptCounter = apps.get_model("ai", "PromptCounter")
    PromptVersion.objects.get_or_create(kind="support", number=1, defaults={"text": SUPPORT_PROMPT})
    PromptCounter.objects.get_or_create(kind="support", defaults={"last_number": 1})


class Migration(migrations.Migration):
    dependencies = [("ai", "0013_agent_prompt")]

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
                    ("support", "Support"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="promptversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind__in", KINDS)), name="prompt_kind_is_known"
            ),
        ),
        migrations.RemoveConstraint(model_name="aicall", name="aicall_purpose_is_known"),
        migrations.AlterField(
            model_name="aicall",
            name="purpose",
            field=models.CharField(choices=PURPOSE_CHOICES, max_length=30),
        ),
        migrations.AddConstraint(
            model_name="aicall",
            constraint=models.CheckConstraint(
                condition=models.Q(("purpose__in", PURPOSES)), name="aicall_purpose_is_known"
            ),
        ),
        migrations.RunPython(add_the_first_support_prompt, migrations.RunPython.noop),
    ]
