"""Who may use the API: only a company that is in good standing and has a subscription that is
active and paid for (or granted free by an admin). Used when a key is made and on every request,
so a key stops working the moment the company stops qualifying."""

from companies.models import Company, CompanyUser
from core.errors import AppError
from plans.subscriptions import State, effective_state, get_subscription

# A cancelled subscription still runs to the end of the period that was paid for.
API_STATES = frozenset({State.ACTIVE, State.CANCELLED, State.GRANTED_FREE})
CLOSED_CODE = "api_access_closed"
CLOSED_MESSAGE = "API access needs an active paid or free subscription."


def closed_error():
    return AppError(CLOSED_CODE, CLOSED_MESSAGE, status_code=403)


def is_open(company_id, creator_id):
    company = Company.objects.filter(pk=company_id).first()
    creator = CompanyUser.objects.filter(pk=creator_id).first()
    return bool(
        company
        and company.status == Company.Status.ACTIVE
        and creator
        and creator.status == CompanyUser.Status.ACTIVE
        and effective_state(get_subscription(company_id)) in API_STATES
    )
