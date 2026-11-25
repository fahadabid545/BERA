from django.db import migrations, models

from ai.default_prompts import ASK_PROMPT


def add_the_first_ask_prompt(apps, schema_editor):
    PromptVersion = apps.get_model("ai", "PromptVersion")
    PromptCounter = apps.get_model("ai", "PromptCounter")
    PromptVersion.objects.get_or_create(kind="ask", number=1, defaults={"text": ASK_PROMPT})
    PromptCounter.objects.get_or_create(kind="ask", defaults={"last_number": 1})


class Migration(migrations.Migration):
    dependencies = [("ai", "0009_playground_without_company")]

    operations = [
        migrations.RemoveConstraint(model_name="promptversion", name="prompt_kind_is_known"),
        migrations.AlterField(
            model_name="promptversion",
            name="kind",
            field=models.CharField(
                choices=[("reading", "Reading"), ("scoring", "Scoring"), ("ask", "Ask")],
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="promptversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind__in", ["reading", "scoring", "ask"])),
                name="prompt_kind_is_known",
            ),
        ),
        migrations.RemoveConstraint(model_name="aicall", name="aicall_purpose_is_known"),
        migrations.AlterField(
            model_name="aicall",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("reading", "Reading"),
                    ("scoring", "Scoring"),
                    ("requirement_extraction", "Requirement Extraction"),
                    ("playground", "Playground"),
                    ("ask", "Ask"),
                ],
                max_length=30,
            ),
        ),
        migrations.AddConstraint(
            model_name="aicall",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "purpose__in",
                        ["reading", "scoring", "requirement_extraction", "playground", "ask"],
                    )
                ),
                name="aicall_purpose_is_known",
            ),
        ),
        migrations.RunPython(add_the_first_ask_prompt, migrations.RunPython.noop),
    ]
