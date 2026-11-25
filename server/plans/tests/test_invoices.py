import logging
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditEvent
from companies.models import Company
from core.errors import AppError
from core.tests.factories import make_company, make_company_user
from emailing.models import OutgoingEmail
from plans import stripe_client
from plans import subscriptions as subs
from plans.models import BillingDetails, Invoice, PaymentEvent
from plans.tests.test_payment_notifications import SECRET, at, event_of, send
from plans.tests.test_plan_change import client_of, plan_of

pytestmark = pytest.mark.django_db
DETAILS = "/api/company/billing/details/"
INVOICES = "/api/company/billing/invoices/"
CHECKOUT = "/api/company/billing/checkout/"
SUB = "sub_test_1"
TAX = "TAX-123/45"
GOOD = {
    "name": "Fake Trading Ltd",
    "address_line1": "1 Fake Street",
    "address_line2": "Floor 2",
    "city": "Faketown",
    "state": "Fakeshire",
    "postal_code": "FK1 2AB",
    "country": "GB",
    "tax_number": TAX,
}
PDF = "https://invoice.example.test/pdf/1"
HOSTED = "https://invoice.example.test/hosted/1"


class FakeProvider:
    def __init__(self):
        self.created = []
        self.updated = []
        self.sessions = []
        self.fail_update = False

    def create_customer(self, **sent):
        self.created.append(sent)
        return f"cus_test_{len(self.created)}"

    def update_customer(self, customer_id, **sent):
        if self.fail_update:
            raise AppError("payment_provider_error", "Plain.", status_code=502)
        self.updated.append((customer_id, sent))

    def create_session(self, **sent):
        self.sessions.append(sent)
        return type(
            "Session",
            (),
            {"id": f"cs_test_{len(self.sessions)}", "url": "https://pay.example.test/1"},
        )()


@pytest.fixture
def provider():
    fake = FakeProvider()
    with (
        patch.object(stripe_client, "create_customer", fake.create_customer),
        patch.object(stripe_client, "update_customer", fake.update_customer),
        patch.object(stripe_client, "create_checkout_session", fake.create_session),
    ):
        yield fake


@pytest.fixture(autouse=True)
def webhook_secret():
    with override_settings(STRIPE_WEBHOOK_SECRET=SECRET):
        yield


@pytest.fixture
def company():
    return make_company(country="PK")


@pytest.fixture
def owner_user(company):
    return make_company_user(company, role="owner")


@pytest.fixture
def owner(owner_user):
    return client_of(owner_user)


@pytest.fixture
def plan():
    return plan_of("Fake Plan", "10.00")


def put(client, **changes):
    return client.put(DETAILS, {**GOOD, **changes}, format="json")


def subscribed(company, plan):
    subs.activate(
        company.pk, plan, period_start=at(1), period_end=at(2),
        stripe_customer_id="cus_test_1", stripe_subscription_id=SUB,
    )  # fmt: skip


def invoice_event(company, plan, *, invoice_id="in_test_1", number="INV-0001", **extra):
    invoice = {
        "id": invoice_id,
        "object": "invoice",
        "number": number,
        "customer": "cus_test_1",
        "subscription": SUB,
        "subscription_details": {
            "metadata": {"company_id": str(company.pk), "plan_id": str(plan.pk)}
        },
        "billing_reason": "subscription_cycle",
        "amount_paid": 1000,
        "amount_due": 1000,
        "currency": "usd",
        "customer_name": "Fake Trading Ltd",
        "customer_address": {
            "line1": "1 Fake Street",
            "line2": "",
            "city": "Faketown",
            "state": "",
            "postal_code": "FK1 2AB",
            "country": "GB",
        },  # fmt: skip
        "custom_fields": [{"name": stripe_client.TAX_NUMBER_FIELD, "value": TAX}],
        "hosted_invoice_url": HOSTED,
        "invoice_pdf": PDF,
        "lines": {
            "data": [{"period": {"start": int(at(2).timestamp()), "end": int(at(3).timestamp())}}]
        },
        **extra,
    }
    return event_of("invoice.paid", invoice, created=at(2, 1))


@pytest.fixture
def invoiced(company, owner_user, plan):
    subscribed(company, plan)
    send(invoice_event(company, plan))
    return Invoice.objects.get(company=company)


class TestBillingDetails:
    def test_a_new_company_has_none_and_is_told_so(self, owner):
        body = owner.get(DETAILS).json()
        assert body["complete"] is False and body["name"] == "" and body["tax_number"] == ""

    def test_the_owner_saves_and_reads_them_back(self, owner):
        assert put(owner).status_code == 200
        body = owner.get(DETAILS).json()
        assert body == {**GOOD, "complete": True}

    def test_name_and_address_are_required(self, owner):
        reply = owner.put(DETAILS, {"tax_number": TAX}, format="json")
        assert reply.status_code == 400
        assert set(reply.json()["error"]["fields"]) >= {"name", "address_line1", "city", "country"}

    @pytest.mark.parametrize("field", ["name", "address_line1", "city"])
    def test_a_blank_required_field_is_refused(self, owner, field):
        assert put(owner, **{field: "   "}).status_code == 400

    @pytest.mark.parametrize("country", ["ZZ", "XX", "", "GBR"])
    def test_the_country_must_be_a_real_one(self, owner, country):
        assert put(owner, country=country).status_code == 400

    def test_the_other_parts_of_the_address_are_optional(self, owner):
        body = {
            k: v
            for k, v in GOOD.items()
            if k not in ("address_line2", "state", "postal_code", "tax_number")
        }
        assert owner.put(DETAILS, body, format="json").status_code == 200
        assert owner.get(DETAILS).json()["complete"] is True

    @pytest.mark.parametrize("tax", ["", "GB 123 456 789", "pk-1234567-8", "12.34/56", "AB123"])
    def test_the_tax_number_is_optional_and_checked_lightly(self, owner, tax):
        assert put(owner, tax_number=tax).status_code == 200

    @pytest.mark.parametrize("tax", ["<script>", "12345; DROP", "x" * 41, "tax:123", "é123"])
    def test_a_tax_number_with_odd_characters_or_length_is_refused_in_plain_words(self, owner, tax):
        reply = put(owner, tax_number=tax)
        assert reply.status_code == 400 and "tax_number" in reply.json()["error"]["fields"]

    def test_a_field_that_is_not_allowed_is_refused(self, owner):
        assert put(owner, company_id=2).status_code == 400
        assert put(owner, stripe_customer_id="cus_x").status_code == 400

    def test_editing_never_changes_the_locked_sign_up_country(self, company, owner):
        put(owner, country="GB")
        put(owner, country="DE")
        assert Company.objects.get(pk=company.pk).country == "PK"
        assert owner.get(DETAILS).json()["country"] == "DE"

    def test_only_the_owner_can_see_or_change_them(self, company, owner):
        put(owner)
        member = client_of(make_company_user(company, role="member"))
        assert member.get(DETAILS).status_code == 403
        assert put(member, name="Changed").status_code == 403
        assert BillingDetails.objects.get(company=company).name == GOOD["name"]

    def test_a_visitor_cannot(self):
        assert APIClient().get(DETAILS).status_code in (401, 403)

    def test_they_are_stored_encrypted(self, company, owner):
        put(owner)
        with connection.cursor() as cursor:
            cursor.execute("select name, tax_number, address_line1 from plans_billingdetails")
            (row,) = cursor.fetchall()
        assert (
            TAX not in row[1] and GOOD["name"] not in row[0] and GOOD["address_line1"] not in row[2]
        )

    def test_one_company_never_sees_another_companys(self, owner):
        put(owner)
        other = make_company()
        client = client_of(make_company_user(other, role="owner"))
        assert client.get(DETAILS).json()["name"] == ""
        put(client, name="Other Ltd")
        assert owner.get(DETAILS).json()["name"] == GOOD["name"]


class TestEditsAreAudited:
    def entries(self):
        return list(AuditEvent.objects.filter(kind="billing.details_changed").order_by("id"))

    def test_an_edit_records_old_and_new_values(self, owner):
        put(owner)
        put(owner, city="Newtown")
        changes = self.entries()[-1].details["changes"]
        assert changes == {"city": {"old": "Faketown", "new": "Newtown"}}

    def test_the_first_save_records_what_was_set(self, owner):
        put(owner)
        changes = self.entries()[0].details["changes"]
        assert changes["name"] == {"old": "", "new": GOOD["name"]}

    def test_the_tax_number_is_only_ever_recorded_as_changed(self, owner):
        put(owner)
        put(owner, tax_number="NEW-999")
        everything = str([entry.details for entry in self.entries()])
        assert self.entries()[-1].details["changes"] == {
            "tax_number": {"old": "hidden", "new": "changed"}
        }
        assert TAX not in everything and "NEW-999" not in everything

    def test_saving_the_same_values_records_nothing(self, owner):
        put(owner)
        put(owner)
        assert len(self.entries()) == 1

    def test_the_actor_is_the_owner_of_the_company(self, company, owner_user, owner):
        put(owner)
        entry = self.entries()[0]
        assert (entry.actor_id, entry.company_id) == (owner_user.pk, company.pk)

    def test_the_tax_number_is_never_logged_or_emailed(self, owner, caplog):
        with caplog.at_level(logging.DEBUG):
            put(owner)
            owner.get(DETAILS)
        assert TAX not in caplog.text
        assert not any(TAX in mail.text_body for mail in OutgoingEmail.objects.all())


class TestTheProviderCustomer:
    def test_an_edit_before_any_payment_calls_the_provider_for_nothing(self, owner, provider):
        put(owner)
        assert provider.created == [] and provider.updated == []

    def test_an_edit_after_a_customer_exists_updates_it(self, company, owner, provider):
        put(owner)
        BillingDetails.objects.filter(company=company).update(stripe_customer_id="cus_test_9")
        put(owner, city="Newtown", tax_number="")
        customer_id, sent = provider.updated[0]
        assert customer_id == "cus_test_9"
        assert sent["address"]["city"] == "Newtown" and sent["tax_number"] == ""

    def test_a_provider_failure_leaves_the_old_details(self, company, owner, provider):
        put(owner)
        BillingDetails.objects.filter(company=company).update(stripe_customer_id="cus_test_9")
        provider.fail_update = True
        assert put(owner, city="Newtown").status_code == 502
        assert owner.get(DETAILS).json()["city"] == "Faketown"
        assert len(AuditEvent.objects.filter(kind="billing.details_changed")) == 1


class TestFirstPaymentNeedsThem:
    def test_checkout_is_refused_until_name_and_address_are_filled(self, owner, provider, plan):
        reply = owner.post(CHECKOUT, {"plan_id": plan.pk}, format="json")
        assert (reply.status_code, reply.json()["error"]["code"]) == (
            409,
            "billing_details_required",
        )
        assert "name" in reply.json()["error"]["fields"]
        assert provider.sessions == [] and provider.created == []

    def test_an_incomplete_record_is_refused_too(self, company, owner, provider, plan):
        put(owner)
        BillingDetails.objects.filter(company=company).update(city="")
        reply = owner.post(CHECKOUT, {"plan_id": plan.pk}, format="json")
        assert reply.json()["error"]["fields"] == {"city": "This is required."}

    def test_with_details_the_customer_is_made_for_them_and_the_page_uses_it(
        self, company, owner, provider, plan
    ):
        put(owner)
        assert owner.post(CHECKOUT, {"plan_id": plan.pk}, format="json").status_code == 200
        sent = provider.created[0]
        assert (sent["name"], sent["tax_number"]) == (GOOD["name"], TAX)
        assert sent["address"]["country"] == "GB" and sent["company_id"] == company.pk
        assert provider.sessions[0]["customer_id"] == "cus_test_1"
        assert BillingDetails.objects.get(company=company).stripe_customer_id == "cus_test_1"

    def test_the_customer_is_made_once(self, owner, provider, plan):
        put(owner)
        owner.post(CHECKOUT, {"plan_id": plan.pk}, format="json")
        other = plan_of("Fake Other", "20.00")
        owner.post(CHECKOUT, {"plan_id": other.pk}, format="json")
        assert len(provider.created) == 1

    def test_a_provider_failure_while_making_the_customer_leaves_nothing_open(
        self, company, owner, provider, plan
    ):
        put(owner)

        def fail(**sent):
            raise AppError("payment_provider_error", "Plain.", status_code=502)

        with patch.object(stripe_client, "create_customer", fail):
            assert owner.post(CHECKOUT, {"plan_id": plan.pk}, format="json").status_code == 502
        from plans.models import CheckoutAttempt

        assert not CheckoutAttempt.objects.filter(company=company).exists()


class TestInvoicesAreStored:
    def test_a_paid_notice_stores_the_invoice_with_its_snapshot(self, company, invoiced, plan):
        assert (invoiced.number, invoiced.amount_minor, invoiced.currency) == (
            "INV-0001",
            1000,
            "USD",
        )
        assert invoiced.plan == plan
        assert invoiced.billed_to_name == "Fake Trading Ltd"
        assert "1 Fake Street" in invoiced.billed_to_address and "GB" in invoiced.billed_to_address
        assert invoiced.billed_to_tax_number == TAX
        assert (invoiced.period_start, invoiced.period_end) == (at(2), at(3))

    def test_the_same_invoice_is_kept_once(self, company, invoiced, plan):
        send(invoice_event(company, plan))
        send(invoice_event(company, plan))  # new notice ids for the same invoice
        assert Invoice.objects.filter(company=company).count() == 1

    def test_each_invoice_is_its_own_record(self, company, invoiced, plan):
        send(invoice_event(company, plan, invoice_id="in_test_2", number="INV-0002"))
        assert Invoice.objects.filter(company=company).count() == 2

    def test_a_notice_for_no_company_stores_nothing(self, plan):
        stranger = make_company()
        send(
            invoice_event(
                stranger, plan, subscription="sub_unknown", subscription_details={"metadata": {}}
            )
        )
        assert Invoice.objects.count() == 0

    def test_without_the_providers_copy_the_current_details_are_the_snapshot(
        self, company, owner_user, owner, plan
    ):
        put(owner)
        subscribed(company, plan)
        send(
            invoice_event(
                company, plan, customer_name=None, customer_address=None, custom_fields=None
            )
        )
        stored = Invoice.objects.get(company=company)
        assert stored.billed_to_name == GOOD["name"] and stored.billed_to_tax_number == TAX

    def test_a_missing_file_address_is_kept_empty(self, company, owner_user, plan):
        subscribed(company, plan)
        send(invoice_event(company, plan, hosted_invoice_url=None, invoice_pdf=None))
        stored = Invoice.objects.get(company=company)
        assert (stored.pdf_url, stored.hosted_url) == ("", "")

    def test_the_links_are_stored_encrypted(self, invoiced):
        with connection.cursor() as cursor:
            cursor.execute("select pdf_url, hosted_url from plans_invoice")
            (row,) = cursor.fetchall()
        assert PDF not in row[0] and HOSTED not in row[1]

    def test_the_payment_record_still_counts_once(self, company, invoiced):
        assert PaymentEvent.objects.filter(company=company).count() == 1


class TestEditsNeverChangeOldInvoices:
    def test_new_details_leave_an_issued_invoice_as_it_was(self, company, owner, invoiced):
        put(owner, name="Renamed Ltd", address_line1="9 New Road", tax_number="NEW-1")
        shown = owner.get(INVOICES).json()["invoices"][0]
        assert shown["billed_to_name"] == "Fake Trading Ltd"
        assert (
            "1 Fake Street" in shown["billed_to_address"]
            and "9 New Road" not in shown["billed_to_address"]
        )
        assert shown["billed_to_tax_number"] == TAX
        fresh = Invoice.objects.get(pk=invoiced.pk)
        assert (fresh.billed_to_name, fresh.billed_to_tax_number) == ("Fake Trading Ltd", TAX)

    def test_the_next_invoice_carries_whatever_the_provider_made_it_with(
        self, company, owner, invoiced, plan
    ):
        put(owner, name="Renamed Ltd")
        send(
            invoice_event(
                company,
                plan,
                invoice_id="in_test_2",
                number="INV-0002",
                customer_name="Renamed Ltd",
            )
        )
        names = {
            row["number"]: row["billed_to_name"] for row in owner.get(INVOICES).json()["invoices"]
        }
        assert names == {"INV-0001": "Fake Trading Ltd", "INV-0002": "Renamed Ltd"}


class TestListing:
    def test_the_owner_lists_invoices_newest_first_without_the_links(
        self, company, owner, invoiced, plan
    ):
        send(invoice_event(company, plan, invoice_id="in_test_2", number="INV-0002"))
        Invoice.objects.filter(provider_invoice_id="in_test_2").update(issued_at=at(3))
        reply = owner.get(INVOICES)
        rows = reply.json()["invoices"]
        assert [row["number"] for row in rows] == ["INV-0002", "INV-0001"]
        assert rows[0]["amount_minor"] == 1000 and rows[0]["currency"] == "USD"
        assert rows[0]["plan_name"] == "Fake Plan"
        assert (rows[0]["can_download"], rows[0]["can_view"]) == (True, True)
        assert "invoice.example.test" not in reply.content.decode()

    def test_a_company_with_none_gets_an_empty_list(self, owner):
        assert owner.get(INVOICES).json() == {"invoices": []}

    def test_a_free_granted_company_has_no_invoices(self, company, owner, plan):
        subs.grant_free(
            company.pk, plan, period_end=timezone.now() + timedelta(days=5), by=None, reason="T"
        )
        assert owner.get(INVOICES).json() == {"invoices": []}
        assert owner.get("/api/company/usage/").json()["state"] == "granted_free"

    def test_only_the_own_companys_invoices_are_listed(self, owner, invoiced, plan):
        other = make_company()
        make_company_user(other, role="owner")
        subs.activate(
            other.pk, plan, period_start=at(1), period_end=at(2),
            stripe_customer_id="cus_other", stripe_subscription_id="sub_other",
        )  # fmt: skip
        send(
            invoice_event(
                other, plan, invoice_id="in_other", number="INV-OTHER", subscription="sub_other"
            )
        )
        assert [row["number"] for row in owner.get(INVOICES).json()["invoices"]] == ["INV-0001"]

    def test_a_member_cannot_list(self, company, invoiced):
        member = client_of(make_company_user(company, role="member"))
        assert member.get(INVOICES).status_code == 403

    def test_a_visitor_cannot(self):
        assert APIClient().get(INVOICES).status_code in (401, 403)


class TestDownloading:
    def link(self, client, invoice, **query):
        return client.get(f"{INVOICES}{invoice.pk}/link/", query)

    def test_the_owner_gets_the_pdf_address_by_default(self, owner, invoiced):
        reply = self.link(owner, invoiced)
        assert (reply.status_code, reply.json()) == (200, {"url": PDF})

    def test_or_the_hosted_page(self, owner, invoiced):
        assert self.link(owner, invoiced, kind="hosted").json() == {"url": HOSTED}

    def test_the_answer_is_never_cached(self, owner, invoiced):
        assert self.link(owner, invoiced)["Cache-Control"] == "no-store"

    def test_another_kind_is_refused(self, owner, invoiced):
        assert self.link(owner, invoiced, kind="zip").status_code == 400

    def test_a_file_that_is_not_ready_is_said_so_plainly(self, owner, invoiced):
        Invoice.objects.filter(pk=invoiced.pk).update(pdf_url="")
        reply = self.link(owner, invoiced)
        assert (reply.status_code, reply.json()["error"]["code"]) == (
            409,
            "invoice_file_unavailable",
        )

    def test_a_member_is_refused_and_gets_no_address(self, company, invoiced):
        member = client_of(make_company_user(company, role="member"))
        reply = self.link(member, invoiced)
        assert reply.status_code == 403 and PDF not in reply.content.decode()

    def test_a_visitor_is_refused(self, invoiced):
        assert self.link(APIClient(), invoiced).status_code in (401, 403)

    def test_another_companys_invoice_looks_exactly_like_none(self, owner, invoiced, plan):
        other = make_company()
        make_company_user(other, role="owner")
        client = client_of(make_company_user(make_company(), role="owner"))
        theirs, nothing = (
            self.link(client, invoiced),
            client.get(f"{INVOICES}00000000-0000-0000-0000-000000000000/link/"),
        )
        assert theirs.status_code == nothing.status_code == 404
        assert theirs.json() == nothing.json()
        assert PDF not in theirs.content.decode()

    def test_the_address_never_reaches_the_audit_log_logs_or_emails(self, owner, invoiced, caplog):
        with caplog.at_level(logging.DEBUG):
            self.link(owner, invoiced)
            owner.get(INVOICES)
        assert PDF not in caplog.text and HOSTED not in caplog.text
        assert "invoice.example.test" not in str(
            list(AuditEvent.objects.values_list("details", flat=True))
        )
        assert not any(
            "invoice.example.test" in mail.text_body for mail in OutgoingEmail.objects.all()
        )


class TestEmailsNeverCarryThem:
    def test_the_payment_flow_sends_no_email_with_invoice_links_or_the_tax_number(
        self, company, owner, invoiced
    ):
        put(owner)
        for mail in OutgoingEmail.objects.all():
            assert "invoice.example.test" not in mail.text_body and TAX not in mail.text_body
