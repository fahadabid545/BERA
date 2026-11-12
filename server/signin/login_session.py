"""The last step of every login: a new session, its cookies, and the new-device notice."""

from rest_framework.response import Response

from . import service
from .cookies import set_session_cookies
from .kinds import ADMIN, COMPANY
from .new_sign_in import notify_if_new_sign_in


def finish_company_login(request, person, extra=None):
    # Every sign-in is its own session, so a second device never signs out the first.
    issued = service.start_session(
        user_id=person.pk, role=person.role, company_id=person.company_id, kind=COMPANY
    )
    notify_if_new_sign_in(person, request)
    response = Response({"status": "ok", **(extra or {})})  # the tokens travel only in cookies
    set_session_cookies(response, COMPANY, issued)
    return response


def finish_admin_login(admin):
    issued = service.start_session(user_id=admin.pk, role=admin.role, company_id=None, kind=ADMIN)
    response = Response({"status": "ok"})
    set_session_cookies(response, ADMIN, issued)
    return response
