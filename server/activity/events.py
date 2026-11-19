"""The kinds of entry in a company's activity log. Kinds marked as not built yet are listed so
the rule exists before the feature does: whoever builds the feature calls `record`."""

KINDS = frozenset(
    {
        "upload",  # not built yet
        "stage_change",  # not built yet
        "download",
        "share",
        "invite_sent",
        "invite_resent",
        "invite_revoked",
        "invite_accepted",
        "project_deleted",
        "member_removed",
        "ownership_transferred",
        "setting_changed",
        "candidate_deleted",
        "data_expired",  # done by the daily clean-up, so it has no person
    }
)
