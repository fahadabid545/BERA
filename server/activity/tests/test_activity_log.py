from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from activity import service
from activity.events import KINDS
from activity.models import ActivityEntry
from companies.models import CompanyUser
from companies.tests.test_invites import accept, client_of, invite, last_token, setting, team
from core.tests.factories import make_admin_user, make_company, make_company_user
from signin import service as signin

pytestmark = pytest.mark.django_db
URL = "/api/company/activity/"


def entry(company, actor, kind="upload", ago_days=0, **fields):
    made = service.record(kind, company_id=company.pk, actor=actor, **fields)
    if ago_days:
        # created_at is set on creation; move it back the way time would have
        ActivityEntry.objects.filter(pk=made.pk).update(
            created_at=timezone.now() - timedelta(days=ago_days)
        )
    return made


def listing(client, **query):
    response = client.get(URL, query)
    assert response.status_code == 200, response.content
    return response.json()


class TestWhatIsKept:
    def test_an_entry_has_who_what_when_and_the_company(self):
        company, owner = team()
        made = service.record(
            "stage_change",
            company_id=company.pk,
            actor=owner,
            target_kind="candidate",
            target_id="abc",
            details={"from_stage": "New", "to_stage": "Interview"},
        )
        made.refresh_from_db()
        assert (made.company_id, made.actor_id, made.actor_name) == (
            company.pk,
            owner.pk,
            owner.name,
        )
        assert (made.kind, made.target_kind, made.target_id) == ("stage_change", "candidate", "abc")
        assert made.details == {"from_stage": "New", "to_stage": "Interview"} and made.created_at

    def test_every_kind_the_ticket_names_exists(self):
        assert {
            "upload",
            "stage_change",
            "download",
            "share",
            "invite_sent",
            "member_removed",
            "setting_changed",
        } <= KINDS

    def test_an_unknown_kind_fails_loudly(self):
        company, owner = team()
        with pytest.raises(KeyError):
            service.record("something_invented", company_id=company.pk, actor=owner)

    @pytest.mark.parametrize("name", ["cv_text", "password", "token", "secret"])
    def test_details_cannot_hold_secrets_or_cv_text(self, name):
        company, owner = team()
        with pytest.raises(ValueError):
            service.record("upload", company_id=company.pk, actor=owner, details={name: "x"})
        with pytest.raises(ValueError):
            service.record(
                "upload", company_id=company.pk, actor=owner, details={"note": "x" * 500}
            )

    def test_entries_remain_readable_after_the_member_is_removed(self):
        company, owner = team()
        member = make_company_user(company, role="member", name="Fake Leaver")
        entry(company, member)
        CompanyUser.objects.filter(pk=member.pk).update(status="removed")
        assert listing(client_of(owner))["entries"][0]["actor_name"] == "Fake Leaver"
        CompanyUser.objects.filter(pk=member.pk).delete()
        assert listing(client_of(owner))["entries"][0]["actor_name"] == "Fake Leaver"
        assert ActivityEntry.objects.count() == 1


class TestInvitationsAreLogged:
    def test_sending_resending_accepting_and_revoking_each_make_an_entry(self):
        company, owner = team()
        client = client_of(owner)
        first = invite(client).json()["id"]
        client.post(f"/api/company/team/invites/{first}/resend/")
        accept(last_token())
        second = invite(client, "second@example.test").json()["id"]
        client.delete(f"/api/company/team/invites/{second}/")
        entries = list(ActivityEntry.objects.order_by("created_at", "id"))
        assert [e.kind for e in entries] == [
            "invite_sent",
            "invite_resent",
            "invite_accepted",
            "invite_sent",
            "invite_revoked",
        ]
        assert {e.company_id for e in entries} == {company.pk}
        assert entries[0].actor_name == owner.name and entries[0].target_id == first
        assert entries[2].actor_name == "Fake Invitee"

    def test_a_refused_invitation_makes_no_entry(self):
        _, owner = team()
        client = client_of(owner)
        invite(client)
        count = ActivityEntry.objects.count()
        assert invite(client).status_code == 409
        assert ActivityEntry.objects.count() == count

    def test_no_address_is_kept_in_the_entry(self):
        _, owner = team()
        invite(client_of(owner), "private-person@example.test")
        stored = str(list(ActivityEntry.objects.values()))
        assert "private-person" not in stored


class TestACompanySeesOnlyItsOwn:
    def test_the_list_holds_only_the_signed_in_companys_entries(self):
        company, owner = team()
        other_company, other_owner = team(company=make_company(name="Fake Other Ltd"))
        entry(company, owner, "upload")
        entry(other_company, other_owner, "download")
        mine = listing(client_of(owner))["entries"]
        theirs = listing(client_of(other_owner))["entries"]
        assert [e["kind"] for e in mine] == ["upload"]
        assert [e["kind"] for e in theirs] == ["download"]

    def test_a_company_id_in_the_request_changes_nothing(self):
        company, owner = team()
        other_company, other_owner = team(company=make_company(name="Fake Other Ltd"))
        entry(other_company, other_owner, "download")
        response = client_of(owner).get(URL, {"company": str(other_company.pk)})
        assert response.status_code == 400  # not a thing the request may say
        assert listing(client_of(owner))["entries"] == []

    def test_other_companies_ids_are_never_in_the_answer(self):
        company, owner = team()
        other_company, other_owner = team(company=make_company(name="Fake Other Ltd"))
        theirs = entry(other_company, other_owner)
        assert str(theirs.pk) not in str(listing(client_of(owner)))

    def test_only_the_owner_may_read_it(self):
        company, owner = team()
        member = make_company_user(company, role="member")
        entry(company, owner)
        response = client_of(member).get(URL)
        assert (response.status_code, response.json()["error"]["code"]) == (403, "not_allowed")

    def test_visitors_and_admins_are_refused(self):
        assert APIClient().get(URL).status_code == 401
        admin = make_admin_user()
        issued = signin.start_session(user_id=admin.pk, role="super", company_id=None, kind="admin")
        assert (
            APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}").get(URL).status_code
            == 401
        )

    def test_only_reading_is_allowed(self):
        _, owner = team()
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client_of(owner), method)(URL).status_code == 405


class TestRetention:
    def test_entries_older_than_the_platform_default_are_not_listed(self):
        company, owner = team()
        entry(company, owner, "upload", ago_days=179)
        entry(company, owner, "download", ago_days=181)
        assert [e["kind"] for e in listing(client_of(owner))["entries"]] == ["upload"]

    def test_the_period_follows_the_platform_setting(self):
        company, owner = team()
        entry(company, owner, "upload", ago_days=40)
        setting("retention.default_days", 30)
        assert listing(client_of(owner))["entries"] == []
        setting("retention.default_days", 90)
        assert len(listing(client_of(owner))["entries"]) == 1

    def test_the_purge_deletes_only_expired_entries_of_every_company(self):
        company, owner = team()
        other_company, other_owner = team(company=make_company(name="Fake Other Ltd"))
        keep = entry(company, owner, ago_days=10)
        entry(company, owner, ago_days=200)
        entry(other_company, other_owner, ago_days=300)
        assert service.purge_expired_entries() == 2
        assert list(ActivityEntry.objects.all()) == [keep]


class TestPaging:
    def test_newest_first_in_pages_with_nothing_lost_or_repeated(self):
        company, owner = team()
        setting("activity.page_size", 2)
        for number in range(5):
            entry(company, owner, "upload", ago_days=0, details={"n": number})
            ActivityEntry.objects.filter(details={"n": number}).update(
                created_at=timezone.now() - timedelta(minutes=10 - number)
            )
        client, seen, before = client_of(owner), [], None
        while True:
            page = listing(client, **({"before": before} if before else {}))
            assert len(page["entries"]) <= 2
            seen += [e["details"]["n"] for e in page["entries"]]
            before = page["next_before"]
            if not before:
                break
        assert seen == [4, 3, 2, 1, 0]

    def test_a_bad_before_value_is_refused(self):
        _, owner = team()
        assert client_of(owner).get(URL, {"before": "yesterday-ish"}).status_code == 400


class TestFilters:
    @pytest.fixture
    def busy(self):
        company, owner = team()
        member = make_company_user(company, role="member", name="Mina Member")
        mine = entry(company, owner, "upload", ago_days=1)
        theirs = entry(company, member, "download", ago_days=5)
        old = entry(company, member, "share", ago_days=20)
        return company, owner, member, mine, theirs, old

    def kinds(self, client, **query):
        return [e["kind"] for e in listing(client, **query)["entries"]]

    def test_by_person(self, busy):
        _, owner, member, *_ = busy
        client = client_of(owner)
        assert self.kinds(client, actor=member.pk) == ["download", "share"]
        assert self.kinds(client, actor=owner.pk) == ["upload"]

    def test_by_date_both_ends_included(self, busy):
        _, owner, *_ = busy
        today = timezone.now().date()
        day = lambda ago: (today - timedelta(days=ago)).isoformat()  # noqa: E731
        client = client_of(owner)
        assert self.kinds(client, since=day(5), until=day(1)) == ["upload", "download"]
        assert self.kinds(client, since=day(2)) == ["upload"]
        assert self.kinds(client, until=day(10)) == ["share"]

    def test_a_day_covers_all_of_that_day(self):
        company, owner = team()
        made = entry(company, owner, "upload")
        stamp = timezone.now().replace(hour=23, minute=59, second=59)
        ActivityEntry.objects.filter(pk=made.pk).update(created_at=stamp)
        day = stamp.date().isoformat()
        assert self.kinds(client_of(owner), since=day, until=day) == ["upload"]

    def test_filters_combine(self, busy):
        _, owner, member, *_ = busy
        since = (timezone.now().date() - timedelta(days=10)).isoformat()
        assert self.kinds(client_of(owner), actor=member.pk, since=since) == ["download"]

    def test_filters_work_with_paging(self, busy):
        _, owner, member, *_ = busy
        setting("activity.page_size", 1)
        client = client_of(owner)
        first = listing(client, actor=member.pk)
        assert [e["kind"] for e in first["entries"]] == ["download"]
        second = listing(client, actor=member.pk, before=first["next_before"])
        assert [e["kind"] for e in second["entries"]] == ["share"]
        assert second["next_before"] is None

    def test_a_first_day_after_the_last_is_refused(self, busy):
        _, owner, *_ = busy
        response = client_of(owner).get(URL, {"since": "2030-02-01", "until": "2030-01-01"})
        assert response.status_code == 400
        assert "until" in response.json()["error"]["fields"]

    @pytest.mark.parametrize("query", [{"actor": "x"}, {"since": "soon"}, {"until": "2030-13-01"}])
    def test_bad_values_are_refused(self, busy, query):
        _, owner, *_ = busy
        assert client_of(owner).get(URL, query).status_code == 400

    def test_another_companys_person_finds_nothing(self, busy):
        _, owner, *_ = busy
        other_company, other_owner = team()
        entry(other_company, other_owner, "upload")
        assert self.kinds(client_of(owner), actor=other_owner.pk) == []

    def test_the_answer_lists_the_people_with_entries_by_name(self, busy):
        _, owner, member, *_ = busy
        people = listing(client_of(owner))["people"]
        assert people == sorted(
            [{"id": owner.pk, "name": owner.name}, {"id": member.pk, "name": "Mina Member"}],
            key=lambda p: p["name"].lower(),
        )

    def test_people_are_only_this_companys_and_within_retention(self, busy):
        company, owner, member, *_ = busy
        other_company, other_owner = team()
        CompanyUser.objects.filter(pk=other_owner.pk).update(name="Outsider Person")
        entry(other_company, CompanyUser.objects.get(pk=other_owner.pk), "upload")
        gone = make_company_user(company, role="member", name="Long Gone")
        entry(company, gone, "upload", ago_days=400)
        names = [p["name"] for p in listing(client_of(owner))["people"]]
        assert "Long Gone" not in names and "Outsider Person" not in names

    def test_a_person_shows_the_name_they_have_most_recently(self, busy):
        company, owner, member, *_ = busy
        CompanyUser.objects.filter(pk=member.pk).update(name="Mina Renamed")
        entry(company, CompanyUser.objects.get(pk=member.pk), "upload")
        people = listing(client_of(owner))["people"]
        assert [p["name"] for p in people if p["id"] == member.pk] == ["Mina Renamed"]
