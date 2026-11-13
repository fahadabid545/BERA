"""What each role of a company may do. The one place the role rules are written.

An owner can do everything in the company. A member works on projects and candidates but
manages nothing about the company itself. A view names the action it performs
(`required_action = "team.invite"`) and never lists roles, so changing a rule means changing
one line here. The web app mirrors this only to hide what a role cannot use; the server
decides on every request.
"""

from core.scoping import require_role

OWNER = "owner"
MEMBER = "member"
EVERYONE = frozenset({OWNER, MEMBER})
OWNER_ONLY = frozenset({OWNER})

ROLES_ALLOWED = {
    "project.view": EVERYONE,
    "project.create": EVERYONE,
    "project.edit": EVERYONE,
    "project.archive": EVERYONE,
    "project.delete": OWNER_ONLY,
    "cv.upload": EVERYONE,
    "cv.download": EVERYONE,
    "candidate.view": EVERYONE,
    "candidate.change_stage": EVERYONE,
    "candidate.write_note": EVERYONE,
    # Both roles may remove an individual candidate; deleting a whole project is the owner's.
    "candidate.delete": EVERYONE,
    "report.download": EVERYONE,
    "report.share": EVERYONE,
    "activity.view": OWNER_ONLY,
    "team.view": OWNER_ONLY,
    "team.invite": OWNER_ONLY,
    "team.remove": OWNER_ONLY,
    "team.transfer_ownership": OWNER_ONLY,
    "billing.view": OWNER_ONLY,
    "settings.change": OWNER_ONLY,
    "advanced.open": OWNER_ONLY,
    "company.delete": OWNER_ONLY,
}


def roles_allowed(action):
    """The roles that may do `action`. An unknown action is a mistake in the code, so it
    fails loudly instead of quietly allowing or refusing."""
    return ROLES_ALLOWED[action]


def require_action(user, action):
    """Raises the shared "not allowed" answer unless the user's role may do `action`."""
    require_role(user, roles_allowed(action))
