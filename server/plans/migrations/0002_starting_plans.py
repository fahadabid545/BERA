from decimal import Decimal

from django.db import migrations

# The owner sets the USD prices, the other limits and the third plan's CV count later. Until a
# plan has every number it stays hidden (it cannot be made active). Names can be edited.
STARTING_PLANS = [
    {"name": "Starter", "price_pkr": Decimal("3000.00"), "cvs_per_month": 250, "display_order": 1},
    {"name": "Growth", "price_pkr": Decimal("5000.00"), "cvs_per_month": 500, "display_order": 2},
    {"name": "Scale", "price_pkr": Decimal("7000.00"), "cvs_per_month": None, "display_order": 3},
]


def create_starting_plans(apps, schema_editor):
    Plan = apps.get_model("plans", "Plan")
    if not Plan.objects.exists():
        for values in STARTING_PLANS:
            Plan.objects.create(status="hidden", **values)


class Migration(migrations.Migration):
    dependencies = [("plans", "0001_initial")]
    operations = [migrations.RunPython(create_starting_plans, migrations.RunPython.noop)]
