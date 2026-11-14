"""The one function every AI call goes through.

Model settings, Prompt versions and AI usage tracking build on `call_ai`; there must never be a
second way to reach the AI provider. It reads the key from the environment, applies the
platform's timeout, and records the tokens of every answer with the Usage counting functions,
so spend is counted whatever the caller does with the text.

Nothing sent or received is logged: job descriptions and CVs are personal data.
"""

import logging
import time
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from platform_settings.service import get_setting
from usage import service as usage

from .costs import price_call
from .models import AiCall

logger = logging.getLogger(__name__)


class AiUnavailable(Exception):
    """The AI could not give an answer (no key, provider down, timeout, refused)."""


@dataclass(frozen=True)
class AiAnswer:
    text: str
    tokens_in: int
    tokens_out: int


def _send(*, model, instructions, text, max_output_tokens, timeout_seconds):
    """The only place that talks to the provider; tests replace it with a stub."""
    if not settings.OPENAI_API_KEY:
        raise AiUnavailable("No AI key is set.")
    from openai import OpenAI, OpenAIError  # imported here so the app starts without a key

    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout_seconds, max_retries=0)
    try:
        reply = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": text},
            ],
            max_completion_tokens=max_output_tokens,
            response_format={"type": "json_object"},
        )
    except OpenAIError as error:
        raise AiUnavailable(type(error).__name__) from error
    usage_info = reply.usage
    return AiAnswer(
        text=reply.choices[0].message.content or "",
        tokens_in=usage_info.prompt_tokens if usage_info else 0,
        tokens_out=usage_info.completion_tokens if usage_info else 0,
    )


def _record(company_id, started, *, result, failure="", tokens=(0, 0), cost=Decimal(0), **ids):
    """Writes the AiCall row. Only ids, numbers and the purpose are stored."""
    AiCall.objects.create(
        company_id=company_id,
        tokens_in=tokens[0],
        tokens_out=tokens[1],
        estimated_cost=cost,
        duration_ms=round((time.monotonic() - started) * 1000),
        result=result,
        failure=failure[:100],
        **ids,
    )


def call_ai(
    company_id,
    *,
    purpose,
    model,
    instructions,
    text,
    prompt_version=None,
    project_id=None,
    cv_id=None,
    candidate_id=None,
    max_output_tokens=None,
):
    """Asks the AI for a JSON answer, records the tokens it used for the company and writes an
    `AiCall` row for the call (see `models.AiCall`).

    `purpose` is an `AiCall.Purpose`, `model` the one pinned to the project (or the platform
    default) and `instructions` the prompt for the task. The cost is the model's price at the
    moment of the call (see `costs.py`) and is stored with the tokens, so a later price change
    never alters it. A failed call is recorded too, then `AiUnavailable` is raised.
    """
    ids = {
        "purpose": purpose,
        "model": model,
        "prompt_version": prompt_version,
        "project_id": project_id,
        "cv_id": cv_id,
        "candidate_id": candidate_id,
    }
    started = time.monotonic()
    try:
        answer = _send(
            model=model,
            instructions=instructions,
            text=text,
            max_output_tokens=max_output_tokens or get_setting("ai.default_max_output_tokens"),
            timeout_seconds=get_setting("ai.request_timeout_seconds"),
        )
    except AiUnavailable as error:
        logger.warning("The AI call failed.")
        _record(company_id, started, result=AiCall.Result.FAILED, failure=str(error), **ids)
        raise
    cost = price_call(model, answer.tokens_in, answer.tokens_out)
    with transaction.atomic():
        usage.add_tokens(
            company_id,
            answer.tokens_in,
            answer.tokens_out,
            cost,
            cv_id=cv_id,
            project_id=project_id,
        )
        _record(
            company_id,
            started,
            result=AiCall.Result.OK,
            tokens=(answer.tokens_in, answer.tokens_out),
            cost=cost,
            **ids,
        )
    return answer
