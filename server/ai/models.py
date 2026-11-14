from django.db import models
from django.db.models import Q


class AiModel(models.Model):
    """A model the platform may use, with what it costs. `name` is the provider's model id and
    never changes, because projects pin it by name. Prices are per million tokens; a call is
    priced when it is made, so changing a price never touches an earlier cost record."""

    name = models.CharField(max_length=100, unique=True)
    input_price_per_million = models.DecimalField(max_digits=12, decimal_places=4)
    output_price_per_million = models.DecimalField(max_digits=12, decimal_places=4)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(input_price_per_million__gte=0) & Q(output_price_per_million__gte=0),
                name="aimodel_prices_are_not_negative",
            ),
        ]
