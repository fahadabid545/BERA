"""Announcement banners: admins write and aim them, companies see and close them."""

from datetime import timedelta

import pytest
from django.utils import timezone

from ai.tests.test_model_settings import admin_client
from announcements.models import Announcement, AnnouncementDismissal
from audit.models import AuditEvent
from companies.tests.test_role_matrix import client_for as company_client
from core.tests.factories import make_company, make_company_user
from cvs.tests.test_ai_reading import set_setting
from plans.models import Plan, Subscription

pytestmark = pytest.mark.django_db
ADMIN_URL = "/api/admin/announcements/"
COMPANY_URL = "/api/company/announcements/"
HOUR = timedelta(hours=1)


def when(offset):
    return (timezone.now() + offset).isoformat()


def body(**over):
    return {
        "message": "Fake maintenance tonight.",
        "starts_at": when(-HOUR),
        "ends_at": when(HOUR),
        "target": "everyone",
        **over,
    }


def make_plan(name="Fake Plan"):
    return Plan.objects.create(name=name)


def put_on_plan(company, plan, state="active"):
    Subscription.objects.update_or_create(
        company=company,
        defaults={
            "plan": plan,
            "state": state,
            "period_end": timezone.now() + 30 * 24 * HOUR,
            "renewal": True,
        },
    )


def make_banner(message="Fake notice", starts=-HOUR, ends=HOUR, target="everyone", **links):
    banner = Announcement.objects.create(
        message=message,
        starts_at=timezone.now() + starts,
        ends_at=timezone.now() + ends,
        target=target,
        plan=links.get("plan"),
    )
    banner.companies.set(links.get("companies", []))
    return banner


def person_client(company=None):
    return company_client(make_company_user(company or make_company(), role="member"))


def shown(client):
    reply = client.get(COMPANY_URL)
    assert reply.status_code == 200
    return [item["message"] for item in reply.json()["items"]]


@pytest.fixture
def boss():
    return admin_client("super")[0]


class TestCreating:
    def test_a_banner_for_everyone_is_stored_and_listed(self, boss):
        reply = boss.post(ADMIN_URL, body(), format="json")
        assert reply.status_code == 201
        [item] = reply.json()["items"]
        assert (item["message"], item["target"], item["status"]) == (
            "Fake maintenance tonight.",
            "everyone",
            "live",
        )

    def test_it_is_aimed_at_a_plan(self, boss):
        plan = make_plan()
        reply = boss.post(ADMIN_URL, body(target="plan", plan=plan.pk), format="json")
        assert reply.status_code == 201
        assert reply.json()["items"][0]["plan"] == "Fake Plan"

    def test_it_is_aimed_at_chosen_companies(self, boss):
        first, second = make_company(), make_company()
        reply = boss.post(
            ADMIN_URL, body(target="companies", companies=[first.pk, second.pk]), format="json"
        )
        assert reply.status_code == 201
        assert reply.json()["items"][0]["company_ids"] == sorted([first.pk, second.pk])

    def test_the_listing_offers_the_plans_and_companies_to_aim_at(self, boss):
        plan, company = make_plan(), make_company(name="Fake Company Ltd")
        listing = boss.get(ADMIN_URL).json()
        assert {"id": plan.pk, "name": "Fake Plan"} in listing["plans"]
        assert {"id": company.pk, "name": "Fake Company Ltd"} in listing["companies"]

    def test_a_banner_that_starts_later_is_listed_as_scheduled(self, boss):
        reply = boss.post(
            ADMIN_URL, body(starts_at=when(HOUR), ends_at=when(2 * HOUR)), format="json"
        )
        assert reply.json()["items"][0]["status"] == "scheduled"

    def test_the_action_is_audited_with_who_and_when_but_not_the_message(self, boss):
        boss.post(ADMIN_URL, body(), format="json")
        event = AuditEvent.objects.get(kind="admin.announcement_created")
        assert event.actor_kind == "admin"
        assert event.created_at is not None
        assert "maintenance" not in str(event.details)

    @pytest.mark.parametrize(
        "over, field",
        [
            ({"message": ""}, "message"),
            ({"message": "x" * 301}, "message"),
            ({"starts_at": "not a date"}, "starts_at"),
            ({"ends_at": when(-2 * HOUR)}, "ends_at"),  # before the start
            ({"starts_at": when(-3 * HOUR), "ends_at": when(-2 * HOUR)}, "ends_at"),  # already over
            ({"target": "nobody"}, "target"),
            ({"target": "plan"}, "plan"),
            ({"target": "plan", "plan": 999_999}, "plan"),
            ({"target": "companies"}, "companies"),
            ({"target": "companies", "companies": []}, "companies"),
            ({"target": "companies", "companies": [999_999]}, "companies"),
            ({"plan": 1}, "plan"),  # a plan with a target that does not use one
            ({"companies": [1]}, "companies"),
        ],
    )
    def test_a_bad_form_is_refused_and_nothing_is_stored(self, boss, over, field):
        reply = boss.post(ADMIN_URL, body(**over), format="json")
        assert reply.status_code == 400
        assert field in reply.json()["error"]["fields"]
        assert Announcement.objects.count() == 0

    def test_the_longest_message_is_a_platform_setting(self, boss):
        set_setting("announcements.max_message_length", 10)
        assert boss.post(ADMIN_URL, body(message="x" * 11), format="json").status_code == 400
        assert boss.post(ADMIN_URL, body(message="x" * 10), format="json").status_code == 201

    def test_an_unknown_field_is_refused(self, boss):
        assert boss.post(ADMIN_URL, body(colour="red"), format="json").status_code == 400


class TestEditingAndDeleting:
    def test_an_edit_changes_the_banner_and_is_audited(self, boss):
        banner = make_banner()
        reply = boss.put(f"{ADMIN_URL}{banner.pk}/", body(message="Fake new words"), format="json")
        assert reply.status_code == 200
        banner.refresh_from_db()
        assert banner.message == "Fake new words"
        assert (
            "message" in AuditEvent.objects.get(kind="admin.announcement_edited").details["changed"]
        )

    def test_an_edit_can_end_a_banner_early(self, boss):
        banner = make_banner()
        reply = boss.put(
            f"{ADMIN_URL}{banner.pk}/", body(ends_at=when(-timedelta(minutes=1))), format="json"
        )
        assert reply.status_code == 200
        assert reply.json()["items"][0]["status"] == "expired"

    def test_changing_the_target_forgets_the_old_companies(self, boss):
        company = make_company()
        banner = make_banner(target="companies", companies=[company])
        boss.put(f"{ADMIN_URL}{banner.pk}/", body(), format="json")
        assert banner.companies.count() == 0

    def test_a_bad_edit_changes_nothing(self, boss):
        banner = make_banner()
        reply = boss.put(f"{ADMIN_URL}{banner.pk}/", body(message=""), format="json")
        assert reply.status_code == 400
        banner.refresh_from_db()
        assert banner.message == "Fake notice"

    def test_deleting_removes_it_and_its_dismissals_and_is_audited(self, boss):
        banner = make_banner()
        person = make_company_user(make_company())
        AnnouncementDismissal.objects.create(
            announcement=banner, user=person, company_id=person.company_id
        )
        assert boss.delete(f"{ADMIN_URL}{banner.pk}/").status_code == 200
        assert Announcement.objects.count() == AnnouncementDismissal.objects.count() == 0
        assert AuditEvent.objects.filter(kind="admin.announcement_deleted").count() == 1

    @pytest.mark.parametrize("method", ["put", "delete"])
    def test_an_unknown_banner_is_not_found(self, boss, method):
        send = getattr(boss, method)
        args = (body(),) if method == "put" else ()
        assert send(f"{ADMIN_URL}999999/", *args, format="json").status_code == 404


class TestWhoMayDoWhat:
    def test_support_may_read(self):
        support = admin_client("support")[0]
        make_banner()
        assert support.get(ADMIN_URL).status_code == 200

    def test_support_is_refused_even_when_the_request_is_sent_directly(self):
        support = admin_client("support")[0]
        banner = make_banner()
        assert support.post(ADMIN_URL, body(), format="json").status_code == 403
        edit = support.put(f"{ADMIN_URL}{banner.pk}/", body(message="Fake"), format="json")
        assert edit.status_code == 403
        assert support.delete(f"{ADMIN_URL}{banner.pk}/").status_code == 403
        banner.refresh_from_db()
        assert (Announcement.objects.count(), banner.message) == (1, "Fake notice")

    def test_a_company_person_cannot_use_the_admin_routes(self):
        client = person_client()
        assert client.get(ADMIN_URL).status_code in (401, 403)
        assert client.post(ADMIN_URL, body(), format="json").status_code in (401, 403)

    def test_the_company_list_needs_a_sign_in(self, client):
        assert client.get(COMPANY_URL).status_code == 401


class TestWhatACompanyIsShown:
    def test_a_banner_for_everyone_is_shown(self):
        make_banner("Fake for all")
        assert shown(person_client()) == ["Fake for all"]

    def test_expired_and_not_yet_started_banners_are_hidden(self):
        make_banner("Fake over", starts=-3 * HOUR, ends=-HOUR)
        make_banner("Fake later", starts=HOUR, ends=2 * HOUR)
        make_banner("Fake now")
        assert shown(person_client()) == ["Fake now"]

    def test_a_banner_disappears_when_it_ends(self):
        banner = make_banner("Fake ending")
        client = person_client()
        assert shown(client) == ["Fake ending"]
        over = timezone.now() - timedelta(seconds=1)
        Announcement.objects.filter(pk=banner.pk).update(ends_at=over)
        assert shown(client) == []

    def test_several_banners_are_ordered_newest_first(self):
        first = make_banner("Fake oldest")
        second = make_banner("Fake middle")
        third = make_banner("Fake newest")
        Announcement.objects.filter(pk=first.pk).update(created_at=timezone.now() - 3 * HOUR)
        Announcement.objects.filter(pk=second.pk).update(created_at=timezone.now() - 2 * HOUR)
        Announcement.objects.filter(pk=third.pk).update(created_at=timezone.now() - HOUR)
        assert shown(person_client()) == ["Fake newest", "Fake middle", "Fake oldest"]

    def test_a_plan_banner_reaches_only_companies_on_that_plan(self):
        plan, other = make_plan(), make_plan("Fake Other")
        make_banner("Fake for plan", target="plan", plan=plan)
        on_plan, on_other, with_none = make_company(), make_company(), make_company()
        put_on_plan(on_plan, plan)
        put_on_plan(on_other, other)
        assert shown(person_client(on_plan)) == ["Fake for plan"]
        assert shown(person_client(on_other)) == []
        assert shown(person_client(with_none)) == []

    def test_a_plan_banner_no_longer_reaches_a_company_whose_subscription_ended(self):
        plan = make_plan()
        make_banner("Fake for plan", target="plan", plan=plan)
        company = make_company()
        put_on_plan(company, plan, state="expired")
        assert shown(person_client(company)) == []

    def test_a_banner_for_chosen_companies_reaches_only_those(self):
        chosen, other = make_company(), make_company()
        make_banner("Fake chosen", target="companies", companies=[chosen])
        assert shown(person_client(chosen)) == ["Fake chosen"]
        assert shown(person_client(other)) == []

    def test_a_banner_is_never_repeated_when_a_company_is_chosen_twice_over(self):
        company = make_company()
        make_banner("Fake chosen", target="companies", companies=[company])
        assert shown(person_client(company)) == ["Fake chosen"]


class TestDismissing:
    def test_a_dismissed_banner_stays_gone_for_that_person(self):
        banner = make_banner()
        client = person_client()
        assert client.post(f"{COMPANY_URL}{banner.pk}/dismiss/").status_code == 200
        assert shown(client) == []

    def test_it_is_still_shown_to_a_colleague_and_to_other_companies(self):
        banner = make_banner("Fake notice")
        company = make_company()
        closer, colleague = person_client(company), person_client(company)
        closer.post(f"{COMPANY_URL}{banner.pk}/dismiss/")
        assert shown(colleague) == ["Fake notice"]
        assert shown(person_client()) == ["Fake notice"]

    def test_dismissing_twice_is_fine_and_stores_one_row(self):
        banner = make_banner()
        client = person_client()
        for _ in range(2):
            assert client.post(f"{COMPANY_URL}{banner.pk}/dismiss/").status_code == 200
        assert AnnouncementDismissal.objects.count() == 1

    def test_the_dismissal_belongs_to_the_persons_own_company(self):
        banner = make_banner()
        company = make_company()
        person_client(company).post(f"{COMPANY_URL}{banner.pk}/dismiss/")
        assert AnnouncementDismissal.objects.get().company_id == company.pk

    def test_a_banner_aimed_at_another_company_looks_like_one_that_does_not_exist(self):
        mine, theirs = make_company(), make_company()
        banner = make_banner(target="companies", companies=[theirs])
        client = person_client(mine)
        reply = client.post(f"{COMPANY_URL}{banner.pk}/dismiss/")
        missing = client.post(f"{COMPANY_URL}999999/dismiss/")
        assert reply.status_code == missing.status_code == 404
        assert reply.json() == missing.json()
        assert AnnouncementDismissal.objects.count() == 0

    def test_a_banner_that_is_over_cannot_be_dismissed(self):
        banner = make_banner(starts=-3 * HOUR, ends=-HOUR)
        assert person_client().post(f"{COMPANY_URL}{banner.pk}/dismiss/").status_code == 404
