import logging
from decimal import Decimal

import pytest

from ai import client
from ai.client import AiAnswer, AiUnavailable, call_ai
from ai.models import AiModel
from core.tests.factories import make_company
from usage import service as usage

pytestmark = pytest.mark.django_db


def stub_provider(monkeypatch, answer=None, error=None):
    seen = {}

    def fake_send(**kwargs):
        seen.update(kwargs)
        if error:
            raise error
        return answer

    monkeypatch.setattr(client, "_send", fake_send)
    return seen


def test_the_answer_comes_back_and_its_tokens_are_counted_for_the_company(monkeypatch):
    company = make_company()
    stub_provider(monkeypatch, AiAnswer("{}", 120, 30))
    answer = call_ai(company.pk, purpose="scoring", model="m", instructions="i", text="t")
    assert answer.text == "{}"
    current = usage.current_usage(company.pk)
    assert (current["tokens_in"], current["tokens_out"]) == (120, 30)


def test_tokens_never_count_as_a_cv(monkeypatch):
    company = make_company()
    stub_provider(monkeypatch, AiAnswer("{}", 10, 10))
    call_ai(company.pk, purpose="scoring", model="m", instructions="i", text="t")
    assert usage.current_usage(company.pk)["cvs_scored"] == 0
    assert usage.waiting_cvs(company.pk) == 0


def test_the_model_prompt_text_and_platform_settings_are_passed_on(monkeypatch):
    company = make_company()
    seen = stub_provider(monkeypatch, AiAnswer("{}", 1, 1))
    call_ai(
        company.pk, purpose="scoring", model="the-model", instructions="the prompt", text="the text"
    )
    assert seen["model"] == "the-model"
    assert seen["instructions"] == "the prompt"
    assert seen["text"] == "the text"
    assert seen["timeout_seconds"] == 60
    assert seen["max_output_tokens"] == 2000


def test_a_failed_call_counts_nothing_and_says_so(monkeypatch):
    company = make_company()
    stub_provider(monkeypatch, error=AiUnavailable("down"))
    with pytest.raises(AiUnavailable):
        call_ai(company.pk, purpose="scoring", model="m", instructions="i", text="t")
    assert usage.current_usage(company.pk)["tokens_in"] == 0


def test_the_cost_comes_from_the_models_prices_at_the_time_of_the_call(monkeypatch):
    company = make_company()
    AiModel.objects.create(
        name="priced", input_price_per_million=Decimal("2"), output_price_per_million=Decimal("10")
    )
    stub_provider(monkeypatch, AiAnswer("{}", 1_000_000, 500_000))
    call_ai(company.pk, purpose="scoring", model="priced", instructions="i", text="t")
    assert usage.current_usage(company.pk)["estimated_cost"] == Decimal("7.000000")


def test_without_a_key_the_real_sender_reports_unavailable(settings):
    settings.OPENAI_API_KEY = ""
    with pytest.raises(AiUnavailable):
        client._send(model="m", instructions="i", text="t", max_output_tokens=10, timeout_seconds=5)


def test_the_text_sent_is_never_logged(monkeypatch, caplog):
    company = make_company()
    stub_provider(monkeypatch, error=AiUnavailable("down"))
    with caplog.at_level(logging.DEBUG), pytest.raises(AiUnavailable):
        call_ai(
            company.pk,
            purpose="scoring",
            model="m",
            instructions="i",
            text="Jane Doe's private text",
        )
    assert "Jane Doe" not in caplog.text


def test_there_is_only_one_place_that_reaches_the_provider():
    from pathlib import Path

    server = Path(client.__file__).parent.parent
    users = [
        path.relative_to(server).as_posix()
        for path in server.rglob("*.py")
        if ".venv" not in path.parts
        and "tests" not in path.parts
        and "from openai" in path.read_text()
    ]
    assert users == ["ai/client.py"]
