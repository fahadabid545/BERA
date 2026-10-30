"""One stand-in model for each kind of company object the product will have.

They only exist while testing. The tables are created inside each test (see the
`object_tables` fixture), so no migration or real feature is needed.
"""

from django.db import models

from core.models import CompanyOwnedModel


def stand_in(name):
    return type(
        name,
        (CompanyOwnedModel,),
        {
            "__module__": __name__,
            "title": models.CharField(max_length=50, default="x"),
            "Meta": type("Meta", (), {"app_label": "signin"}),
        },
    )


KINDS_OF_OBJECT = {
    name: stand_in(name) for name in ("Project", "Candidate", "StoredFile", "Report", "Invoice")
}
