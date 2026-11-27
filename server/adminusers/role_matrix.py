"""What each admin role may do. The one place the admin role rules are written.

A super admin may do everything. Support works with companies, jobs and data requests but
changes nothing about the platform itself. A route names the action it performs
(`required_action = "plan.change"`) and never lists roles, so changing a rule means changing
one line here. The web app mirrors this only to hide what a role cannot use
(`components/admin/navigation.ts`); the server decides on every request.
"""

from core.scoping import require_role

SUPER = "super"
SUPPORT = "support"
BOTH = frozenset({SUPER, SUPPORT})
SUPER_ONLY = frozenset({SUPER})

ROLES_ALLOWED = {
    # What support may do.
    "company.view": BOTH,
    "usage.view": BOTH,
    "job.view": BOTH,
    "job.retry": BOTH,
    "job.cancel": BOTH,
    "team_member.block": BOTH,  # block or unblock
    "data_request.handle": BOTH,
    "feedback.handle": BOTH,
    "support.handle": BOTH,
    "announcement.read": BOTH,
    # Pages only super admins may open (hidden from support, and refused if typed in).
    "plan.view": SUPER_ONLY,
    "ai.view": SUPER_ONLY,
    "chatbot.view": SUPER_ONLY,
    "trial_code.view": SUPER_ONLY,
    "free_access.view": SUPER_ONLY,
    "discount.view": SUPER_ONLY,
    "payment.view": SUPER_ONLY,
    "settings.view": SUPER_ONLY,
    "audit_log.view": SUPER_ONLY,
    "admin_user.view": SUPER_ONLY,
    "advanced.open": SUPER_ONLY,
    # Changes only super admins may make.
    "announcement.create": SUPER_ONLY,
    "announcement.edit": SUPER_ONLY,
    "announcement.delete": SUPER_ONLY,
    "plan.change": SUPER_ONLY,
    "price.change": SUPER_ONLY,
    "model.change": SUPER_ONLY,
    "ai.control": SUPER_ONLY,  # pause or resume all AI work
    "ai.playground": SUPER_ONLY,  # run test scoring and set its monthly budget
    "prompt.change": SUPER_ONLY,
    "discount.manage": SUPER_ONLY,  # make a discount code, switch it, limit it to a plan
    "free_access.manage": SUPER_ONLY,  # invite, revoke and extend beta and permitted access
    "trial_code.manage": SUPER_ONLY,  # make a trial code, switch it on or off
    "chatbot.change": SUPER_ONLY,  # its settings and its knowledge documents
    "settings.change": SUPER_ONLY,
    "legal.review": SUPER_ONLY,  # say that the Terms and Privacy text was reviewed, or take it back
    "limit.change": SUPER_ONLY,
    "subscription.grant_free": SUPER_ONLY,
    "subscription.terminate": SUPER_ONLY,
    "company.suspend": SUPER_ONLY,  # suspend or unsuspend
    "company_user.two_step_off": SUPER_ONLY,
    "admin_user.manage": SUPER_ONLY,
}


def roles_allowed(action):
    """The roles that may do `action`. An unknown action is a mistake in the code, so it
    fails loudly instead of quietly allowing or refusing."""
    return ROLES_ALLOWED[action]


def require_action(user, action):
    """Raises the shared "not allowed" answer unless the admin's role may do `action`."""
    require_role(user, roles_allowed(action))
