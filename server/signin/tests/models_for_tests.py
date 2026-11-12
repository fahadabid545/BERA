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


# Every kind of company data the product will hold, named in the isolation ticket: projects,
# CVs, results, users (tested with the real model), files, usage, invoices, exports and shared
# reports. Add a name here when a new kind of company data is planned.
KINDS_OF_OBJECT = {
    name: stand_in(name)
    for name in (
        "Project",
        "Candidate",
        "Cv",
        "Result",
        "StoredFile",
        "Report",
        "SharedReport",
        "Export",
        "UsageRecord",
        "Invoice",
    )
}
