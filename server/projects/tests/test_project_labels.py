import pytest

from core.tests.factories import make_company
from projects.tests.helpers import sign_in

pytestmark = pytest.mark.django_db


def save(client, project, labels):
    return client.put(
        f"/api/company/projects/{project.pk}/preferences/", {"labels": labels}, format="json"
    )


def listed(client, query=""):
    return client.get(f"/api/company/projects/?{query}").json()


class TestLabels:
    def test_labels_are_saved_and_shown_on_the_card(self, owner, project):
        assert save(owner, project, ["Engineering", "Urgent"]).json()["labels"] == [
            "Engineering",
            "Urgent",
        ]
        (card,) = listed(owner)["results"]
        assert card["labels"] == ["Engineering", "Urgent"]

    def test_blanks_are_trimmed_and_repeats_dropped_ignoring_case(self, owner, project):
        result = save(owner, project, ["  Sales ", "sales", "Remote"])
        assert result.json()["labels"] == ["Sales", "Remote"]

    def test_an_empty_label_is_refused(self, owner, project):
        assert save(owner, project, ["   "]).status_code == 400

    def test_a_label_longer_than_the_limit_is_refused(self, owner, project):
        assert save(owner, project, ["x" * 31]).status_code == 400

    def test_more_labels_than_the_limit_is_refused(self, owner, project):
        assert save(owner, project, [f"l{n}" for n in range(6)]).status_code == 400

    def test_all_labels_can_be_removed(self, owner, project):
        save(owner, project, ["Sales"])
        assert save(owner, project, []).json()["labels"] == []

    def test_the_company_list_holds_each_label_once(self, owner, project):
        save(owner, project, ["Sales", "Remote"])
        copy = owner.post(f"/api/company/projects/{project.pk}/duplicate/").json()["id"]
        owner.put(
            f"/api/company/projects/{copy}/preferences/", {"labels": ["Sales"]}, format="json"
        )
        assert listed(owner)["labels"] == ["Remote", "Sales"]

    def test_the_list_filters_by_label(self, owner, project):
        save(owner, project, ["Sales"])
        copy = owner.post(f"/api/company/projects/{project.pk}/duplicate/").json()["id"]
        save_to = f"/api/company/projects/{copy}/preferences/"
        owner.put(save_to, {"labels": ["Remote"]}, format="json")
        assert len(listed(owner)["results"]) == 2
        assert [card["id"] for card in listed(owner, "label=Sales")["results"]] == [str(project.pk)]
        assert listed(owner, "label=Missing")["results"] == []

    def test_another_company_never_sees_the_labels(self, owner, project):
        save(owner, project, ["Sales"])
        _, stranger = sign_in(make_company())
        assert listed(stranger)["labels"] == []

    def test_a_copy_keeps_the_labels(self, owner, project):
        save(owner, project, ["Sales"])
        copy = owner.post(f"/api/company/projects/{project.pk}/duplicate/").json()["id"]
        assert owner.get(f"/api/company/projects/{copy}/preferences/").json()["labels"] == ["Sales"]
