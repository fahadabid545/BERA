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
    EventKind("candidate.deleted"),
    EventKind("export.created"),  # not built yet
    EventKind("retention.changed"),
    EventKind("company.deletion_requested"),
    EventKind("company.deletion_undone"),
    EventKind("company.deleted"),
    EventKind("plan.changed"),  # not built yet
    EventKind("subscription.state_changed"),
    # Admin actions. One that changes another account or a company needs a written reason;
    # reading things needs none.
    EventKind("admin.first_super_admin_created"),
    EventKind("admin.invited", reason_required=True),
    EventKind("admin.invite_resent"),
    EventKind("admin.invite_revoked"),
    EventKind("admin.invite_accepted"),
    EventKind("admin.role_changed", reason_required=True),
    EventKind("admin.status_changed", reason_required=True),
    EventKind("admin.member_blocked", reason_required=True),
    EventKind("admin.member_unblocked", reason_required=True),
    EventKind("admin.plan_created"),
    EventKind("admin.model_added"),
    EventKind("admin.model_changed", reason_required=True),
    EventKind("admin.models_selected", reason_required=True),
    EventKind("admin.ai_paused", reason_required=True),
    EventKind("admin.ai_resumed", reason_required=True),
    EventKind("admin.prompt_created"),
    EventKind("admin.prompt_made_current", reason_required=True),
    EventKind("admin.prompt_deleted", reason_required=True),
    EventKind("admin.project_prompt_moved", reason_required=True),
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
    EventKind("admin.pkr_rate_changed", reason_required=True),
    EventKind("admin.ai_spend_alerts_changed", reason_required=True),
    EventKind("admin.ai_playground_budget_changed", reason_required=True),
    EventKind("admin.job_retried"),
    EventKind("admin.job_cancelled"),
    EventKind("admin.setting_changed"),
    EventKind("admin.setting_reset"),
    EventKind("admin.maintenance_changed", reason_required=True),
    EventKind("admin.data_request_created"),
    EventKind("admin.data_request_status_changed"),
    EventKind("admin.announcement_created"),
    EventKind("admin.announcement_edited"),
    EventKind("admin.announcement_deleted"),
    # Reserved: opening candidate content is refused for admin and support. An exception would be
    # explicit, time limited and justified in writing, and recorded with this kind.
    EventKind("admin.candidate_data_exception", reason_required=True),
)
