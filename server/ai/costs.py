"""What an AI call cost, from the model's prices at the moment of the call."""

import logging
from decimal import Decimal

from .models import AiModel

logger = logging.getLogger(__name__)

TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)
COST_PLACES = Decimal("0.000001")


def price_call(model_name, tokens_in, tokens_out):
    """The estimated cost of one call. A model with no price in the models list costs 0, and a
    warning is logged so the missing price is noticed."""
    model = AiModel.objects.filter(name=model_name).first()
    if model is None:
        logger.warning(
            "No price is set for AI model %s, so its calls are counted as free.", model_name
        )
        return Decimal(0)
    cost = (
        tokens_in * model.input_price_per_million + tokens_out * model.output_price_per_million
    ) / TOKENS_PER_PRICE_UNIT
    return cost.quantize(COST_PLACES)
