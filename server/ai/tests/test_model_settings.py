import logging
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ai import client
from ai.client import AiAnswer, call_ai
from ai.models import AiModel
from audit.models import AuditEvent
from core.tests.factories import make_admin_user, make_company, make_company_user
from plans import subscriptions as subs
from plans.models import Plan
from platform_settings.service import clear_cache, get_setting
from projects.models import Project
from signin import service
from usage import service as usage

pytestmark = pytest.mark.django_db
URL = "/api/admin/ai/models/"
SELECTION = "/api/admin/ai/models/selection/"
REASON = "A test reason."


def admin_client(role="super"):
    admin = make_admin_user(role=role)
    issued = service.start_session(user_id=admin.pk, role=role, company_id=None, kind="admin")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}"), admin


@pytest.fixture
def boss():
    return admin_client("super")[0]


def add(boss, name, input_price="1", output_price="2", **extra):
    return boss.post(
        URL,
        {
            "name": name,
            "input_price_per_million": input_price,
            "output_price_per_million": output_price,
            **extra,
        },
        format="json",
    )


def company_with_plan():
    company = make_company()
    now = timezone.now()
    plan = Plan.objects.create(
        name="Basic",
        status="active",
        price_usd=10,
        cvs_per_month=100,
        cvs_per_project=50,
        max_projects=5,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=10_000_000,
    )
    subs.activate(company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30))
    return company


def make_project(company, **fields):
    return Project.objects.create(
        company=company,
        title="T",
        job_description="t",
        reading_model=fields.pop("reading_model", "standin-reading-model"),
        created_by=make_company_user(company),
        **fields,
    )


def model_named(name):
    return AiModel.objects.get(name=name)


def audit_kinds():
    return list(AuditEvent.objects.order_by("id").values_list("kind", flat=True))


class TestTheList:
    def test_the_platform_starts_with_two_stand_in_models_that_are_chosen(self, boss):
        data = boss.get(URL).json()
        assert {entry["name"] for entry in data["models"]} == {
            "standin-reading-model",
            "standin-scoring-model",
        }
        assert data["choice"] == {
            "reading": "standin-reading-model",
            "scoring": "standin-scoring-model",
        }

    def test_each_model_shows_its_prices_and_where_it_is_in_use(self, boss):
        make_project(make_company())
        reading = next(
            m for m in boss.get(URL).json()["models"] if m["name"] == "standin-reading-model"
        )
        assert reading["chosen_for"] == ["reading"]
        assert reading["projects"] == {"reading": 1, "scoring": 0}
        assert reading["input_price_per_million"] == "0.0000"


class TestOnlySuperAdminsMayUseIt:
    def test_support_cannot_read_or_change_anything(self):
        support, _ = admin_client("support")
        assert support.get(URL).status_code == 403
        assert support.post(URL, {}, format="json").status_code == 403
        assert support.patch(f"{URL}1/", {}, format="json").status_code == 403
        assert support.put(SELECTION, {}, format="json").status_code == 403
        assert not AuditEvent.objects.filter(kind__startswith="admin.model").exists()

    def test_nobody_signed_in_and_company_members_are_refused(self):
        assert APIClient().get(URL).status_code == 401
        person = make_company_user(make_company())
        issued = service.start_session(
            user_id=person.pk, role="owner", company_id=person.company_id, kind="company"
        )
        company = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert company.get(URL).status_code == 401


class TestAddingModels:
    def test_a_model_is_added_with_its_prices_and_switched_on(self, boss):
        answer = add(boss, "gpt-test", "0.15", "0.6")
        assert answer.status_code == 201
        model = model_named("gpt-test")
        assert (model.input_price_per_million, model.output_price_per_million) == (
            Decimal("0.15"),
            Decimal("0.6"),
        )
        assert model.enabled is True
        assert audit_kinds() == ["admin.model_added"]

    def test_a_model_can_be_added_switched_off(self, boss):
        add(boss, "gpt-off", enabled=False)
        assert model_named("gpt-off").enabled is False

    def test_the_same_name_twice_is_refused(self, boss):
        add(boss, "gpt-test")
        answer = add(boss, "gpt-test")
        assert answer.status_code == 400 and "name" in answer.json()["error"]["fields"]
        assert AiModel.objects.filter(name="gpt-test").count() == 1

    @pytest.mark.parametrize(
        "body",
        [
            {"name": "", "input_price_per_million": "1", "output_price_per_million": "1"},
            {"name": "m", "input_price_per_million": "-1", "output_price_per_million": "1"},
            {"name": "m", "input_price_per_million": "abc", "output_price_per_million": "1"},
            {"name": "m", "input_price_per_million": True, "output_price_per_million": "1"},
            {"name": "m", "input_price_per_million": "1"},
            {"name": "m", "input_price_per_million": "1", "output_price_per_million": "1", "x": 1},
            {"name": "m", "input_price_per_million": "0.00001", "output_price_per_million": "1"},
        ],
    )
    def test_bad_input_is_refused_and_nothing_is_added(self, boss, body):
        before = AiModel.objects.count()
        assert boss.post(URL, body, format="json").status_code == 400
        assert AiModel.objects.count() == before


class TestPricing:
    def test_a_price_change_needs_a_reason_and_is_audited_with_old_and_new(self, boss):
        add(boss, "gpt-test", "1", "2")
        model = model_named("gpt-test")
        assert (
            boss.patch(
                f"{URL}{model.pk}/", {"input_price_per_million": "3"}, format="json"
            ).status_code
            == 400
        )
        answer = boss.patch(
            f"{URL}{model.pk}/",
            {"reason": REASON, "input_price_per_million": "3", "output_price_per_million": "4.5"},
            format="json",
        )
        assert answer.status_code == 200
        model.refresh_from_db()
        assert (model.input_price_per_million, model.output_price_per_million) == (
            3,
            Decimal("4.5"),
        )
        entry = AuditEvent.objects.get(kind="admin.model_changed")
        assert entry.reason == REASON
        assert entry.details["changes"]["input_price_per_million"] == {
            "old": "1.0000",
            "new": "3.0000",
        }

    def test_changing_nothing_is_refused(self, boss):
        add(boss, "gpt-test", "1", "2")
        model = model_named("gpt-test")
        answer = boss.patch(
            f"{URL}{model.pk}/", {"reason": REASON, "input_price_per_million": "1"}, format="json"
        )
        assert answer.status_code == 400 and answer.json()["error"]["code"] == "nothing_changed"

    def test_an_unknown_model_is_not_found(self, boss):
        assert (
            boss.patch(
                f"{URL}999999/", {"reason": REASON, "enabled": False}, format="json"
            ).status_code
            == 404
        )
        assert (
            boss.patch(
                f"{URL}abc/", {"reason": REASON, "enabled": False}, format="json"
            ).status_code
            == 404
        )


class TestPriceChangesNeverAlterPastCosts:
    @pytest.fixture
    def company(self):
        return company_with_plan()

    def stub(self, monkeypatch):
        monkeypatch.setattr(client, "_send", lambda **call: AiAnswer("{}", 1_000_000, 1_000_000))

    def test_a_call_is_priced_when_it_is_made_and_later_price_changes_leave_it_alone(
        self, boss, company, monkeypatch
    ):
        self.stub(monkeypatch)
        add(boss, "gpt-test", "1", "2")
        call_ai(company.pk, purpose="scoring", model="gpt-test", instructions="i", text="t")
        assert usage.current_usage(company.pk)["estimated_cost"] == Decimal("3.000000")
        model = model_named("gpt-test")
        boss.patch(
            f"{URL}{model.pk}/",
            {"reason": REASON, "input_price_per_million": "10", "output_price_per_million": "20"},
            format="json",
        )
        assert usage.current_usage(company.pk)["estimated_cost"] == Decimal("3.000000")
        call_ai(company.pk, purpose="scoring", model="gpt-test", instructions="i", text="t")
        assert usage.current_usage(company.pk)["estimated_cost"] == Decimal("33.000000")

    def test_a_model_with_no_price_costs_nothing_and_a_warning_is_logged(
        self, company, monkeypatch, caplog
    ):
        self.stub(monkeypatch)
        caplog.set_level(logging.WARNING)
        call_ai(company.pk, purpose="scoring", model="not-in-the-list", instructions="i", text="t")
        assert usage.current_usage(company.pk)["estimated_cost"] == Decimal(0)
        assert "No price is set for AI model not-in-the-list" in caplog.text

    def test_a_model_in_the_list_logs_no_warning(self, boss, company, monkeypatch, caplog):
        self.stub(monkeypatch)
        add(boss, "gpt-test")
        caplog.set_level(logging.WARNING)
        call_ai(company.pk, purpose="scoring", model="gpt-test", instructions="i", text="t")
        assert "No price" not in caplog.text


class TestChoosingTheModels:
    def two_models(self, boss):
        add(boss, "reader-2")
        add(boss, "scorer-2")
        return model_named("reader-2"), model_named("scorer-2")

    def select(self, boss, reading, scoring, **extra):
        return boss.put(
            SELECTION,
            {"reason": REASON, "reading_model": reading.pk, "scoring_model": scoring.pk, **extra},
            format="json",
        )

    def test_the_choice_applies_to_new_projects_only(self, boss):
        company = company_with_plan()
        old = make_project(company)
        reader, scorer = self.two_models(boss)
        answer = self.select(boss, reader, scorer)
        assert answer.status_code == 200
        assert answer.json()["choice"] == {"reading": "reader-2", "scoring": "scorer-2"}
        clear_cache()
        old.refresh_from_db()
        assert (old.reading_model, old.scoring_model) == (
            "standin-reading-model",
            "standin-scoring-model",
        )
        from projects.service import create_project

        owner = old.created_by
        new = create_project(
            owner, title="New", job_description="d" * 600, acknowledge_warnings=True
        )
        assert (new.reading_model, new.scoring_model) == ("reader-2", "scorer-2")

    def test_a_new_project_pins_the_scoring_model_beside_the_reading_model(self):
        project = make_project(make_company())
        assert project.scoring_model == get_setting("ai.scoring_model")

    def test_the_choice_is_audited_with_the_reason(self, boss):
        reader, scorer = self.two_models(boss)
        self.select(boss, reader, scorer)
        entry = AuditEvent.objects.get(kind="admin.models_selected")
        assert entry.reason == REASON
        assert entry.details["changes"]["reading_model"] == {
            "old": "standin-reading-model",
            "new": "reader-2",
        }

    def test_a_reason_is_required(self, boss):
        reader, scorer = self.two_models(boss)
        answer = boss.put(
            SELECTION, {"reading_model": reader.pk, "scoring_model": scorer.pk}, format="json"
        )
        assert answer.status_code == 400
        assert get_setting("ai.reading_model") == "standin-reading-model"

    def test_a_model_that_is_switched_off_cannot_be_chosen(self, boss):
        add(boss, "off-model", enabled=False)
        reader, _ = self.two_models(boss)
        answer = self.select(boss, model_named("off-model"), reader)
        assert answer.status_code == 400
        assert answer.json()["error"]["code"] == "model_not_enabled"
        assert get_setting("ai.reading_model") == "standin-reading-model"

    def test_an_unknown_model_cannot_be_chosen(self, boss):
        reader, _ = self.two_models(boss)
        answer = boss.put(
            SELECTION,
            {"reason": REASON, "reading_model": 999999, "scoring_model": reader.pk},
            format="json",
        )
        assert answer.status_code == 400

    def test_choosing_what_is_already_chosen_changes_nothing(self, boss):
        reading = model_named("standin-reading-model")
        scoring = model_named("standin-scoring-model")
        answer = self.select(boss, reading, scoring)
        assert answer.status_code == 400 and answer.json()["error"]["code"] == "nothing_changed"


class TestSwitchingModelsOffAndOn:
    def test_a_model_nobody_uses_is_switched_off_at_once_and_back_on(self, boss):
        add(boss, "spare")
        model = model_named("spare")
        off = boss.patch(f"{URL}{model.pk}/", {"reason": REASON, "enabled": False}, format="json")
        assert off.status_code == 200 and not model_named("spare").enabled
        on = boss.patch(f"{URL}{model.pk}/", {"reason": REASON, "enabled": True}, format="json")
        assert on.status_code == 200 and model_named("spare").enabled

    def test_a_model_that_is_chosen_cannot_be_switched_off_without_a_replacement(self, boss):
        add(boss, "other")
        model = model_named("standin-reading-model")
        answer = boss.patch(
            f"{URL}{model.pk}/", {"reason": REASON, "enabled": False}, format="json"
        )
        assert answer.status_code == 409
        error = answer.json()["error"]
        assert error["code"] == "model_in_use"
        assert error["details"]["usage"]["chosen_for"] == ["reading"]
        assert "other" in [option["name"] for option in error["details"]["replacements"]]
        assert model_named("standin-reading-model").enabled
        assert not AuditEvent.objects.filter(kind="admin.model_changed").exists()

    def test_a_replacement_takes_over_the_choice_and_the_projects_pinned_to_the_model(self, boss):
        add(boss, "successor")
        successor = model_named("successor")
        mine = make_project(make_company())
        theirs = make_project(make_company())
        model = model_named("standin-reading-model")
        answer = boss.patch(
            f"{URL}{model.pk}/",
            {"reason": REASON, "enabled": False, "replacement": successor.pk},
            format="json",
        )
        assert answer.status_code == 200
        clear_cache()
        assert not model_named("standin-reading-model").enabled
        assert get_setting("ai.reading_model") == "successor"
        assert get_setting("ai.scoring_model") == "standin-scoring-model"
        for project in (mine, theirs):
            project.refresh_from_db()
            assert project.reading_model == "successor"
            assert project.scoring_model == "standin-scoring-model"
        entry = AuditEvent.objects.get(kind="admin.model_changed")
        assert entry.details["moved_projects"] == 2 and entry.details["moved_choices"] == "reading"

    def test_a_model_only_pinned_by_projects_also_needs_a_replacement(self, boss):
        add(boss, "pinned-only")
        add(boss, "successor")
        project = make_project(make_company(), reading_model="pinned-only")
        model = model_named("pinned-only")
        refused = boss.patch(
            f"{URL}{model.pk}/", {"reason": REASON, "enabled": False}, format="json"
        )
        assert refused.status_code == 409
        assert refused.json()["error"]["details"]["usage"]["projects"]["reading"] == 1
        boss.patch(
            f"{URL}{model.pk}/",
            {"reason": REASON, "enabled": False, "replacement": model_named("successor").pk},
            format="json",
        )
        project.refresh_from_db()
        assert project.reading_model == "successor"
        assert get_setting("ai.reading_model") == "standin-reading-model"

    @pytest.mark.parametrize("which", ["itself", "switched_off", "unknown"])
    def test_a_bad_replacement_is_refused_and_nothing_changes(self, boss, which):
        add(boss, "off", enabled=False)
        model = model_named("standin-reading-model")
        replacement = {
            "itself": model.pk,
            "switched_off": model_named("off").pk,
            "unknown": 999999,
        }[which]
        answer = boss.patch(
            f"{URL}{model.pk}/",
            {"reason": REASON, "enabled": False, "replacement": replacement},
            format="json",
        )
        assert answer.status_code == 409
        assert model_named("standin-reading-model").enabled
        assert get_setting("ai.reading_model") == "standin-reading-model"

    def test_with_no_other_model_switched_on_the_refusal_says_so(self, boss):
        model = model_named("standin-reading-model")
        AiModel.objects.exclude(pk=model.pk).update(enabled=False)
        answer = boss.patch(
            f"{URL}{model.pk}/", {"reason": REASON, "enabled": False}, format="json"
        )
        assert answer.status_code == 409
        assert answer.json()["error"]["details"]["replacements"] == []

    def test_changing_only_the_price_of_a_model_in_use_needs_no_replacement(self, boss):
        model = model_named("standin-reading-model")
        answer = boss.patch(
            f"{URL}{model.pk}/", {"reason": REASON, "input_price_per_million": "5"}, format="json"
        )
        assert answer.status_code == 200
