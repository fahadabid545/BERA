from django.db import migrations

from platform_settings.definitions import DEFINITIONS

CHOICE_SETTINGS = ("ai.reading_model", "ai.scoring_model")


def add_the_stand_in_models(apps, schema_editor):
    """The models the platform starts with, so the two choices point at models in the list. They
    cost nothing; a super admin adds the real models with their prices and switches these off."""
    AiModel = apps.get_model("ai", "AiModel")
    for key in CHOICE_SETTINGS:
        AiModel.objects.get_or_create(
            name=DEFINITIONS[key].default,
            defaults={"input_price_per_million": 0, "output_price_per_million": 0},
        )


class Migration(migrations.Migration):
    dependencies = [("ai", "0001_initial")]
    operations = [migrations.RunPython(add_the_stand_in_models, migrations.RunPython.noop)]
