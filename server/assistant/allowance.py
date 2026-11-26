"""The company agent's own AI allowance: the only token limit there is.

Scoring and reading are limited by CVs, never by tokens; asking the agent is limited by the tokens
its questions used in the company's current billing period (`ask.monthly_token_cap`).
"""

from django.db.models import Sum
from django.utils import timezone

from ai.models import AiCall
from core.errors import AppError
from platform_settings.service import get_setting
from usage.service import window_for

ALLOWANCE_USED_CODE = "agent_allowance_used"
ALLOWANCE_USED_MESSAGE = (
    "Your company has used the agent's allowance for this period. "
    "You can ask again when the next period starts."
)


def tokens_used(company_id, now=None):
    now = now or timezone.now()
    start, end = window_for(company_id, now)
    totals = AiCall.objects.filter(
        company_id=company_id,
        purpose=AiCall.Purpose.ASK,
        created_at__gte=start,
        created_at__lt=end,
    ).aggregate(tokens_in=Sum("tokens_in"), tokens_out=Sum("tokens_out"))
    return (totals["tokens_in"] or 0) + (totals["tokens_out"] or 0)


def require_allowance(company_id):
    """Refuses a new question once the period's tokens reach the cap."""
    if tokens_used(company_id) >= get_setting("ask.monthly_token_cap"):
        raise AppError(ALLOWANCE_USED_CODE, ALLOWANCE_USED_MESSAGE, status_code=409)
