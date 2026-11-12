"""The kinds of entry in a company's activity log. Kinds marked as not built yet are listed so
the rule exists before the feature does: whoever builds the feature calls `record`."""

KINDS = frozenset(
    {
        "upload",  # not built yet
        "stage_change",  # not built yet
        "download",  # not built yet
        "share",  # not built yet
        "invite_sent",
        "invite_resent",
        "invite_revoked",
        "invite_accepted",
        "member_removed",
        "ownership_transferred",
        "setting_changed",  # not built yet
    }
)
