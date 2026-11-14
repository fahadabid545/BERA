"""Every kind of event the audit log can hold, and which of them need a written reason.

Adding an action that matters means adding its kind here first; `record` refuses a kind that
is not listed, so nothing is logged under an invented name. Kinds marked as not built yet are
listed so the rule exists before the feature does: whoever builds the feature calls `record`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EventKind:
    name: str
    reason_required: bool = False


def _kinds(*kinds):
    return {kind.name: kind for kind in kinds}


KINDS = _kinds(
    # Sign-ins (company users and admins).
    EventKind("auth.login"),
    EventKind("auth.login_failed"),
    EventKind("auth.two_step_failed"),
    # Security events; the super admins are emailed about these (audit/alerts.py).
    EventKind("security.token_reuse"),
    EventKind("security.permission_refused"),
    EventKind("security.abuse_blocked"),
    EventKind("security.download_volume"),
    # Key company actions.
    EventKind("invite.sent"),
    EventKind("invite.resent"),
    EventKind("invite.revoked"),
    EventKind("invite.accepted"),
    EventKind("team.member_removed"),
    EventKind("team.ownership_transferred"),
    EventKind("project.deleted"),  # not built yet
    EventKind("export.created"),  # not built yet
    EventKind("retention.changed"),  # not built yet
    EventKind("plan.changed"),  # not built yet
    EventKind("subscription.state_changed"),
    # Admin actions. One that changes another account or a company needs a written reason;
    # reading things needs none.
    EventKind("admin.first_super_admin_created"),
    EventKind("admin.role_changed", reason_required=True),
    EventKind("admin.status_changed", reason_required=True),
    EventKind("admin.member_blocked", reason_required=True),
    EventKind("admin.member_unblocked", reason_required=True),
    EventKind("admin.plan_created"),
    EventKind("admin.model_added"),
    EventKind("admin.model_changed", reason_required=True),
    EventKind("admin.models_selected", reason_required=True),
    EventKind("admin.plan_changed", reason_required=True),
    EventKind("admin.plan_deleted", reason_required=True),
    EventKind("admin.free_subscription_granted", reason_required=True),
    EventKind("admin.free_subscription_ended", reason_required=True),
    EventKind("admin.limit_changed", reason_required=True),
    EventKind("admin.two_step_reset", reason_required=True),
    EventKind("admin.company_two_step_off", reason_required=True),
    EventKind("admin.company_suspended", reason_required=True),
    EventKind("admin.company_unsuspended", reason_required=True),
    EventKind("admin.subscription_terminated", reason_required=True),
    # Reserved: opening candidate content is refused for admin and support. An exception would be
    # explicit, time limited and justified in writing, and recorded with this kind.
    EventKind("admin.candidate_data_exception", reason_required=True),
)
