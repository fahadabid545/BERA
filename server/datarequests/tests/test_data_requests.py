"""Data requests: logged by hand, moved forward, completed, and fed into the overview."""

from datetime import timedelta

import pytest
from django.utils import timezone

from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from companies.models import Company
from core.tests.factories import make_company
from cvs.tests.test_ai_reading import set_setting
from datarequests.models import DataRequest

pytestmark = pytest.mark.django_db
URL = "/api/admin/data-requests/"
OVERVIEW = "/api/admin/dashboard/"
DETAIL = "/api/admin/dashboard/detail/"
DAY = timedelta(days=1)


def today():
    return timezone.localdate()


def body(of_company, **over):
    return {
        "company": of_company.pk,
        "kind": "export",
        "requested_by": "Fake Requester",
        "received_on": today().isoformat(),
        **over,
    }


@pytest.fixture(params=["super", "support"])
def admin(request):
    return admin_client(request.param)[0]


@pytest.fixture
def company():
    return make_company()


def log(admin, company, **over):
    reply = admin.post(URL, body(company, **over), format="json")
    assert reply.status_code == 201, reply.json()
    return max(reply.json()["items"], key=lambda item: item["id"])


class TestLogging:
    def test_both_roles_log_a_request_that_is_due_in_30_days(self, admin, company):
        item = log(admin, company, received_on=(today() - 3 * DAY).isoformat(), note="Fake note")
        assert item["status"] == "open"
        assert item["company"] == company.name
        assert item["due_on"] == (today() + 27 * DAY).isoformat()
        assert item["overdue"] is False
        assert item["note"] == "Fake note"

    def test_the_number_of_days_is_a_platform_setting(self, admin, company):
        set_setting("data_requests.due_days", 10)
        item = log(admin, company)
        assert item["due_on"] == (today() + 10 * DAY).isoformat()

    def test_an_old_request_is_overdue(self, admin, company):
        item = log(admin, company, received_on=(today() - 31 * DAY).isoformat())
        assert item["overdue"] is True

    def test_a_request_due_today_is_not_overdue_yet(self, admin, company):
        item = log(admin, company, received_on=(today() - 30 * DAY).isoformat())
        assert (item["due_on"], item["overdue"]) == (today().isoformat(), False)

    def test_it_is_audited_without_who_asked_or_the_note(self, admin, company):
        log(admin, company, note="Fake note")
        event = AuditEvent.objects.get(kind="admin.data_request_created")
        assert event.company_id == company.pk
        assert "Fake Requester" not in str(event.details)
        assert "Fake note" not in str(event.details)

    @pytest.mark.parametrize(
        "over, field",
        [
            ({"company": 999_999}, "company"),
            ({"kind": "rename"}, "kind"),
            ({"requested_by": ""}, "requested_by"),
            ({"received_on": "nope"}, "received_on"),
            ({"received_on": (timezone.localdate() + DAY).isoformat()}, "received_on"),
            ({"note": "x" * 301}, "note"),
        ],
    )
    def test_a_bad_form_is_refused_and_nothing_is_stored(self, admin, company, over, field):
        reply = admin.post(URL, body(company, **over), format="json")
        assert reply.status_code == 400
        assert field in reply.json()["error"]["fields"]
        assert DataRequest.objects.count() == 0

    def test_an_unknown_field_is_refused(self, admin, company):
        assert admin.post(URL, body(company, status="completed"), format="json").status_code == 400

    def test_the_request_must_be_signed_in_as_an_admin(self, client, company):
        assert client.post(URL, body(company), format="json").status_code == 401


class TestMovingForward:
    def test_open_then_in_progress_then_completed_with_the_day_saved(self, admin, company):
        item = log(admin, company)
        url = f"{URL}{item['id']}/"
        assert admin.patch(url, {"status": "in_progress"}, format="json").status_code == 200
        reply = admin.patch(url, {"status": "completed"}, format="json")
        done = next(each for each in reply.json()["items"] if each["id"] == item["id"])
        assert (done["status"], done["completed_on"]) == ("completed", today().isoformat())
        assert done["overdue"] is False

    def test_a_request_may_go_straight_to_completed(self, admin, company):
        item = log(admin, company)
        assert (
            admin.patch(f"{URL}{item['id']}/", {"status": "completed"}, format="json").status_code
            == 200
        )

    @pytest.mark.parametrize(
        "start, back",
        [("completed", "in_progress"), ("completed", "open"), ("in_progress", "open")],
    )
    def test_going_backwards_is_refused(self, admin, company, start, back):
        item = log(admin, company)
        url = f"{URL}{item['id']}/"
        admin.patch(url, {"status": start}, format="json")
        reply = admin.patch(url, {"status": back}, format="json")
        assert reply.status_code == 409
        assert reply.json()["error"]["code"] == "data_request_status_backwards"
        assert DataRequest.objects.get().status == start

    def test_only_a_status_change_is_audited_with_the_old_and_new_status(self, admin, company):
        item = log(admin, company)
        url = f"{URL}{item['id']}/"
        admin.patch(url, {"note": "Fake new note"}, format="json")
        assert not AuditEvent.objects.filter(kind="admin.data_request_status_changed").exists()
        admin.patch(url, {"status": "in_progress"}, format="json")
        event = AuditEvent.objects.get(kind="admin.data_request_status_changed")
        assert (event.details["old_status"], event.details["new_status"]) == ("open", "in_progress")

    def test_the_note_can_change_and_the_due_date_never_does(self, admin, company):
        item = log(admin, company)
        admin.patch(f"{URL}{item['id']}/", {"note": "Fake changed"}, format="json")
        row = DataRequest.objects.get()
        assert (row.note, row.due_on.isoformat()) == ("Fake changed", item["due_on"])

    def test_a_note_that_is_too_long_is_refused(self, admin, company):
        item = log(admin, company)
        reply = admin.patch(f"{URL}{item['id']}/", {"note": "x" * 301}, format="json")
        assert reply.status_code == 400

    def test_an_empty_change_is_refused(self, admin, company):
        item = log(admin, company)
        assert admin.patch(f"{URL}{item['id']}/", {}, format="json").status_code == 400

    def test_an_unknown_request_is_not_found(self, admin):
        assert (
            admin.patch(f"{URL}999999/", {"status": "completed"}, format="json").status_code == 404
        )


class TestListing:
    def test_open_ones_come_first_by_due_date_then_completed(self, admin, company):
        late = log(admin, company, received_on=(today() - 5 * DAY).isoformat())
        early = log(admin, company, received_on=(today() - 20 * DAY).isoformat())
        done = log(admin, company)
        admin.patch(f"{URL}{done['id']}/", {"status": "completed"}, format="json")
        ids = [item["id"] for item in admin.get(URL).json()["items"]]
        assert ids == [early["id"], late["id"], done["id"]]

    def test_it_can_be_filtered_by_status(self, admin, company):
        log(admin, company)
        done = log(admin, company)
        admin.patch(f"{URL}{done['id']}/", {"status": "completed"}, format="json")
        reply = admin.get(URL, {"status": "completed"}).json()
        assert [item["id"] for item in reply["items"]] == [done["id"]]
        assert admin.get(URL, {"status": "nonsense"}).status_code == 400

    def test_the_list_is_capped_by_a_setting_and_gives_the_real_total(self, admin, company):
        set_setting("data_requests.list_limit", 2)
        for _ in range(3):
            log(admin, company)
        reply = admin.get(URL).json()
        assert (len(reply["items"]), reply["total"]) == (2, 3)

    def test_the_companies_to_choose_from_are_offered(self, admin, company):
        assert {"id": company.pk, "name": company.name} in admin.get(URL).json()["companies"]

    def test_the_request_stays_after_its_company_is_deleted(self, admin, company):
        item = log(admin, company)
        name = company.name
        # The deletion flow is tested on its own; a bare company row is all this test needs gone.
        Company.objects.filter(pk=company.pk)._raw_delete(Company.objects.db)
        row = next(each for each in admin.get(URL).json()["items"] if each["id"] == item["id"])
        assert (row["company"], row["company_exists"]) == (name, False)


class TestAttention:
    def pending(self, client):
        return client.get(OVERVIEW).json()["pending"]

    def test_open_and_in_progress_requests_are_counted_for_both_roles(self, admin, company):
        log(admin, company)
        progressing = log(admin, company)
        admin.patch(f"{URL}{progressing['id']}/", {"status": "in_progress"}, format="json")
        assert self.pending(admin)["data_requests"] == 2

    def test_a_completed_request_leaves_the_attention_tab(self, admin, company):
        item = log(admin, company)
        admin.patch(f"{URL}{item['id']}/", {"status": "completed"}, format="json")
        assert self.pending(admin)["data_requests"] == 0

    def test_review_lists_them_most_urgent_first_and_marks_the_overdue_ones(self, admin, company):
        fresh = log(admin, company)
        old = log(admin, company, received_on=(today() - 40 * DAY).isoformat(), kind="deletion")
        done = log(admin, company)
        admin.patch(f"{URL}{done['id']}/", {"status": "completed"}, format="json")
        reply = admin.get(DETAIL, {"kind": "pending", "key": "data_requests"}).json()
        assert reply["total"] == 2
        assert [(i["id"], i["overdue"], i["request_type"]) for i in reply["items"]] == [
            (old["id"], True, "deletion"),
            (fresh["id"], False, "export"),
        ]
        assert reply["items"][0]["company_id"] == company.pk
