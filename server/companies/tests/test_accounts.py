import pytest
from django.db import IntegrityError, connection, transaction

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser
from companies.services import create_company_with_owner, transfer_ownership
from core.errors import AppError
from core.tests.factories import make_admin_user, make_company, make_company_user

pytestmark = pytest.mark.django_db


def sign_up(email="owner@example.test", company_name="Fake Ltd"):
    return create_company_with_owner(
        company_name=company_name,
        country="DE",
        owner_name="Fake Owner",
        owner_email=email,
        password="a-long-enough-fake-password",
    )


class TestCompany:
    def test_it_has_the_agreed_fields_and_starts_active(self):
        company = Company.objects.create(name="Fake Ltd", country="DE")
        assert (company.name, company.country, company.status) == ("Fake Ltd", "DE", "active")
        assert company.created_at is not None

    def test_the_country_defaults_to_other(self):
        assert Company.objects.create(name="Fake Ltd").country == "ZZ"

    def test_a_company_can_be_suspended_and_nothing_else(self):
        company = make_company(status="suspended")
        assert company.status == "suspended"
        with pytest.raises(IntegrityError), transaction.atomic():
            Company.objects.filter(pk=company.pk).update(status="deleted")


class TestDeletingACompany:
    def test_deleting_one_company_is_refused(self):
        company = make_company()
        with pytest.raises(AppError) as caught:
            company.delete()
        assert caught.value.code == "company_deletion_blocked"
        assert Company.objects.filter(pk=company.pk).exists()

    def test_deleting_many_companies_is_refused(self):
        make_company()
        with pytest.raises(AppError):
            Company.objects.all().delete()
        assert Company.objects.count() == 1

    def test_the_database_itself_refuses_when_the_company_has_people(self):
        company, _ = sign_up()
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # normally checked when committing
            cursor.execute("DELETE FROM companies_company WHERE id = %s", [company.id])


class TestCompanyUser:
    def test_it_has_the_agreed_fields(self):
        _, owner = sign_up()
        assert owner.name == "Fake Owner" and owner.email == "owner@example.test"
        assert owner.role == "owner" and owner.status == "active"
        assert owner.email_verified is False

    def test_the_password_is_only_kept_as_a_strong_hash(self):
        _, owner = sign_up()
        assert owner.password_hash.startswith("argon2$")
        assert "a-long-enough-fake-password" not in owner.password_hash
        assert owner.check_password("a-long-enough-fake-password")
        assert not owner.check_password("another-password")

    def test_the_same_password_is_hashed_differently_each_time(self):
        first, second = make_company_user(), make_company_user()
        first.set_password("the-same-fake-password")
        second.set_password("the-same-fake-password")
        assert first.password_hash != second.password_hash

    def test_an_invited_person_without_a_password_cannot_sign_in(self):
        person = make_company_user(role="member")
        person.set_unusable_password()
        assert not person.check_password("")
        assert not person.check_password("anything")

    @pytest.mark.parametrize(
        "typed", ["Owner@Example.test", "  owner@example.test ", " OWNER@EXAMPLE.TEST  "]
    )
    def test_an_email_in_another_spelling_is_the_same_email(self, typed):
        sign_up()
        with pytest.raises(IntegrityError), transaction.atomic():
            make_company_user(email=typed, role="member")

    def test_an_email_is_stored_trimmed_and_in_lower_case(self):
        person = make_company_user(email="  Jo.Reader@Example.TEST ")
        person.refresh_from_db()
        assert person.email == "jo.reader@example.test"

    def test_a_badly_spelled_email_is_refused_by_the_database_even_without_save(self):
        company = make_company()
        with pytest.raises(IntegrityError), transaction.atomic():
            CompanyUser.objects.bulk_create(
                [CompanyUser(company=company, name="Fake", email="Mixed@Example.test")]
            )

    def test_one_person_cannot_belong_to_two_companies_with_the_same_email(self):
        sign_up(email="shared@example.test", company_name="First Fake Ltd")
        with pytest.raises(IntegrityError), transaction.atomic():
            sign_up(email="Shared@example.test", company_name="Second Fake Ltd")
        assert Company.objects.count() == 1

    def test_a_removed_persons_email_stays_taken(self):
        person = make_company_user(role="member", email="gone@example.test")
        person.status = "removed"
        person.save()
        with pytest.raises(IntegrityError), transaction.atomic():
            make_company_user(email="gone@example.test", role="member")

    @pytest.mark.parametrize("field", ["role", "status"])
    def test_unknown_roles_and_statuses_are_refused_by_the_database(self, field):
        person = make_company_user(role="member")
        with pytest.raises(IntegrityError), transaction.atomic():
            CompanyUser.objects.filter(pk=person.pk).update(**{field: "boss"})

    def test_each_person_belongs_to_exactly_one_company(self):
        assert CompanyUser._meta.get_field("company").null is False
        assert CompanyUser._meta.get_field("company").many_to_many is False


class TestOwnership:
    def test_creating_a_company_adds_its_one_owner(self):
        company, owner = sign_up()
        assert list(company.users.filter(role="owner")) == [owner]

    def test_a_failed_sign_up_leaves_no_company_behind(self):
        sign_up(email="taken@example.test")
        with pytest.raises(IntegrityError):
            sign_up(email="taken@example.test", company_name="Other Fake Ltd")
        assert Company.objects.count() == 1

    def test_a_second_owner_is_refused(self):
        company, _ = sign_up()
        with pytest.raises(IntegrityError), transaction.atomic():
            make_company_user(company, role="owner")

    def test_two_companies_each_have_their_own_owner(self):
        sign_up(email="one@example.test", company_name="One Fake Ltd")
        sign_up(email="two@example.test", company_name="Two Fake Ltd")
        assert CompanyUser.objects.filter(role="owner").count() == 2

    def test_a_company_can_have_many_members(self):
        company, _ = sign_up()
        for _ in range(3):
            make_company_user(company, role="member")
        assert company.users.count() == 4

    def test_the_owner_cannot_be_demoted_or_removed_directly(self):
        _, owner = sign_up()
        owner.role = "member"
        with pytest.raises(AppError) as caught:
            owner.save()
        assert caught.value.code == "owner_required"
        owner.refresh_from_db()
        owner.status = "removed"
        with pytest.raises(AppError):
            owner.save()
        owner.refresh_from_db()
        assert (owner.role, owner.status) == ("owner", "active")

    def test_the_owner_can_be_blocked_and_keeps_ownership(self):
        _, owner = sign_up()
        owner.status = "blocked"
        owner.save()
        owner.refresh_from_db()
        assert owner.role == "owner"

    def test_ownership_passes_to_an_active_member(self):
        company, owner = sign_up()
        member = make_company_user(company, role="member")
        transfer_ownership(company, member)
        owner.refresh_from_db()
        member.refresh_from_db()
        assert (owner.role, member.role) == ("member", "owner")
        assert company.users.filter(role="owner").count() == 1

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_ownership_cannot_pass_to_someone_who_is_not_active(self, status):
        company, _ = sign_up()
        member = make_company_user(company, role="member", status=status)
        with pytest.raises(AppError) as caught:
            transfer_ownership(company, member)
        assert caught.value.code == "owner_transfer_refused"

    def test_ownership_cannot_pass_to_someone_from_another_company(self):
        company, owner = sign_up()
        _, outsider = sign_up(email="other@example.test", company_name="Other Fake Ltd")
        with pytest.raises(AppError):
            transfer_ownership(company, outsider)
        owner.refresh_from_db()
        assert owner.role == "owner"

    def test_ownership_cannot_pass_to_the_owner_themselves(self):
        company, owner = sign_up()
        with pytest.raises(AppError):
            transfer_ownership(company, owner)


class TestAdminUser:
    def test_it_has_the_agreed_fields(self):
        admin = make_admin_user(role="support")
        assert admin.role == "support" and admin.status == "active"
        assert admin.two_step_set is False
        assert admin.password_hash == "" or admin.password_hash.startswith("argon2$")

    def test_the_password_is_only_kept_as_a_strong_hash(self):
        admin = make_admin_user()
        admin.set_password("a-long-enough-fake-password")
        assert admin.password_hash.startswith("argon2$")
        assert admin.check_password("a-long-enough-fake-password")

    def test_emails_are_unique_in_any_spelling(self):
        make_admin_user(email="staff@example.test")
        with pytest.raises(IntegrityError), transaction.atomic():
            make_admin_user(email=" STAFF@example.test ")

    def test_admins_have_no_company(self):
        assert "company" not in {field.name for field in AdminUser._meta.get_fields()}

    @pytest.mark.parametrize("field", ["role", "status"])
    def test_unknown_roles_and_statuses_are_refused_by_the_database(self, field):
        admin = make_admin_user()
        with pytest.raises(IntegrityError), transaction.atomic():
            AdminUser.objects.filter(pk=admin.pk).update(**{field: "boss"})


class TestKindsAreSeparate:
    def test_they_are_three_tables_and_none_is_shared(self):
        tables = {
            Company._meta.db_table,
            CompanyUser._meta.db_table,
            AdminUser._meta.db_table,
        }
        assert len(tables) == 3

    def test_no_table_holds_credentials_for_both_kinds(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.columns"
                " WHERE table_schema = 'public' AND column_name = 'password_hash'"
            )
            tables = sorted(row[0] for row in cursor.fetchall())
        assert tables == ["adminusers_adminuser", "companies_companyuser"]

    def test_djangos_own_user_table_is_not_used(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('auth_user')")
            assert cursor.fetchone()[0] is None

    def test_the_same_email_may_exist_as_a_company_user_and_an_admin_without_being_linked(self):
        person = make_company_user(email="both@example.test")
        admin = make_admin_user(email="both@example.test")
        assert person.pk is not None and admin.pk is not None
        assert not hasattr(admin, "company_user") and not hasattr(person, "admin_user")

    def test_a_company_users_id_does_not_open_an_admin_sign_in(self):
        from signin import service

        person = make_company_user()
        AdminUser.objects.filter(pk=person.pk).delete()
        issued = service.start_session(
            user_id=person.pk, role="super", company_id=None, kind="admin"
        )
        with pytest.raises(Exception) as caught:
            service.verify_access_token(issued.access_token, "admin")
        assert caught.type.__name__ == "NotAuthenticated"
