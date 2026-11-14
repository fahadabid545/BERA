import logging
from decimal import Decimal

import pytest

from ai import client
from ai.client import AiAnswer, AiUnavailable, call_ai
from ai.models import AiCall, AiModel
from core.tests.factories import make_company
from usage import service as usage

pytestmark = pytest.mark.django_db
SECRET_TEXT = "Jane Example, jane@example.com, +1 555 010 0000, 1 Example Street"


def stub(monkeypatch, answer=None, error=None):
    def fake_send(**kwargs):
        if error:
            raise error
        return answer

    monkeypatch.setattr(client, "_send", fake_send)


def ask(company, **changes):
    options = {"purpose": "scoring", "model": "m", "instructions": "i", "text": "t", **changes}
    return call_ai(company.pk, **options)


class TestEveryCallIsRecorded:
    def test_a_call_is_recorded_with_everything_asked_for(self, monkeypatch):
        company = make_company()
        AiModel.objects.create(
            name="priced",
            input_price_per_million=Decimal("2"),
            output_price_per_million=Decimal("10"),
        )
        stub(monkeypatch, AiAnswer("{}", 1_000_000, 500_000))
        ids = {
            "project_id": "11111111-1111-1111-1111-111111111111",
            "cv_id": None,
            "candidate_id": "33333333-3333-3333-3333-333333333333",
        }
        ask(company, model="priced", purpose="reading", prompt_version=4, **ids)
        row = AiCall.objects.get()
        assert row.company_id == company.pk
        assert (str(row.project_id), row.cv_id, str(row.candidate_id)) == (
            ids["project_id"], None, ids["candidate_id"],
        )  # fmt: skip
        assert (row.purpose, row.model, row.prompt_version) == ("reading", "priced", 4)
        assert (row.tokens_in, row.tokens_out) == (1_000_000, 500_000)
        assert row.estimated_cost == Decimal("7.000000")
        assert row.result == "ok" and row.failure == ""
        assert row.duration_ms >= 0 and row.created_at

    @pytest.mark.parametrize(
        "purpose", ["reading", "scoring", "requirement_extraction", "playground"]
    )
    def test_every_purpose_can_be_recorded(self, monkeypatch, purpose):
        stub(monkeypatch, AiAnswer("{}", 1, 1))
        ask(make_company(), purpose=purpose)
        assert AiCall.objects.get().purpose == purpose

    def test_an_unknown_purpose_is_refused_by_the_database(self, monkeypatch):
        from django.db import IntegrityError, transaction

        stub(monkeypatch, AiAnswer("{}", 1, 1))
        with pytest.raises(IntegrityError), transaction.atomic():
            ask(make_company(), purpose="chat")

    def test_each_call_is_its_own_row(self, monkeypatch):
        company = make_company()
        stub(monkeypatch, AiAnswer("{}", 1, 1))
        ask(company)
        ask(company)
        assert AiCall.objects.count() == 2

    def test_the_prompt_version_is_empty_when_the_prompt_has_none(self, monkeypatch):
        stub(monkeypatch, AiAnswer("{}", 1, 1))
        ask(make_company())
        assert AiCall.objects.get().prompt_version is None

    def test_a_model_with_no_price_is_recorded_as_free(self, monkeypatch):
        stub(monkeypatch, AiAnswer("{}", 10, 10))
        ask(make_company(), model="unpriced")
        assert AiCall.objects.get().estimated_cost == 0

    def test_the_stored_cost_is_not_changed_by_a_later_price_change(self, monkeypatch):
        stub(monkeypatch, AiAnswer("{}", 1_000_000, 0))
        model = AiModel.objects.create(
            name="priced", input_price_per_million=Decimal("2"), output_price_per_million=Decimal(1)
        )
        ask(make_company(), model="priced")
        model.input_price_per_million = Decimal("20")
        model.save()
        assert AiCall.objects.get().estimated_cost == Decimal("2.000000")

    def test_the_recorded_tokens_match_what_the_company_is_charged(self, monkeypatch):
        company = make_company()
        stub(monkeypatch, AiAnswer("{}", 120, 30))
        ask(company)
        current = usage.current_usage(company.pk)
        row = AiCall.objects.get()
        assert (row.tokens_in, row.tokens_out) == (current["tokens_in"], current["tokens_out"])


class TestFailedCalls:
    def test_a_failed_call_is_recorded_with_no_tokens_and_no_cost(self, monkeypatch):
        company = make_company()
        stub(monkeypatch, error=AiUnavailable("Timeout"))
        with pytest.raises(AiUnavailable):
            ask(company, purpose="reading", prompt_version=2)
        row = AiCall.objects.get()
        assert (row.result, row.failure) == ("failed", "Timeout")
        assert (row.tokens_in, row.tokens_out, row.estimated_cost) == (0, 0, 0)
        assert (row.purpose, row.model, row.prompt_version) == ("reading", "m", 2)
        assert row.duration_ms >= 0

    def test_a_failed_call_is_still_not_counted_in_usage(self, monkeypatch):
        company = make_company()
        stub(monkeypatch, error=AiUnavailable("down"))
        with pytest.raises(AiUnavailable):
            ask(company)
        assert usage.current_usage(company.pk)["tokens_in"] == 0

    def test_a_long_reason_is_cut_to_fit(self, monkeypatch):
        stub(monkeypatch, error=AiUnavailable("x" * 500))
        with pytest.raises(AiUnavailable):
            ask(make_company())
        assert len(AiCall.objects.get().failure) == 100

    def test_a_success_never_has_a_failure_reason(self):
        from django.db import IntegrityError, transaction

        company = make_company()
        with pytest.raises(IntegrityError), transaction.atomic():
            AiCall.objects.create(
                company=company, purpose="scoring", model="m", duration_ms=1, result="ok",
                failure="oops",
            )  # fmt: skip


class TestNothingPersonalIsStored:
    def test_the_row_holds_no_text_that_was_sent_or_received(self, monkeypatch):
        stub(monkeypatch, AiAnswer(f'{{"note": "{SECRET_TEXT}"}}', 5, 5))
        ask(make_company(), instructions="Read this CV.", text=SECRET_TEXT)
        values = str(AiCall.objects.values().get())
        for piece in ("Jane", "jane@example.com", "555 010", "Example Street", "Read this CV"):
            assert piece not in values

    def test_the_table_has_no_column_that_could_hold_text(self):
        kinds = {f.name: type(f).__name__ for f in AiCall._meta.get_fields() if f.concrete}
        assert "TextField" not in kinds.values()
        assert not {"text", "answer", "prompt", "instructions", "content"} & set(kinds)

    def test_a_failure_reason_is_not_logged_with_the_text(self, monkeypatch, caplog):
        stub(monkeypatch, error=AiUnavailable("down"))
        with caplog.at_level(logging.DEBUG), pytest.raises(AiUnavailable):
            ask(make_company(), text=SECRET_TEXT)
        assert "Jane" not in caplog.text


class TestRecordsAreKept:
    def test_a_record_names_a_project_by_id_only_so_deleting_it_leaves_the_record(
        self, monkeypatch
    ):
        project_id = "11111111-1111-1111-1111-111111111111"
        stub(monkeypatch, AiAnswer("{}", 1, 1))
        ask(make_company(), project_id=project_id)
        field = AiCall._meta.get_field("project_id")
        assert not field.is_relation  # no link, so nothing cascades or blocks a deletion
        assert str(AiCall.objects.get().project_id) == project_id
