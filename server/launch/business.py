"""Items 1 to 5: who can recover accounts, the plans and their prices, and the legal pages."""

from rest_framework.test import APIRequestFactory

from adminusers.models import AdminUser
from adminusers.role_matrix import SUPER_ONLY, roles_allowed
from audit.events import KINDS
from plans.public_views import public_plans
from plans.service import active_plans, missing_for_active
from platform_settings import legal_documents, legal_review
from platform_settings.service import get_setting

from .results import item, not_ok, ok

REQUIRED_PLANS = ("Starter", "Growth", "Scale")
ENOUGH_SUPER_ADMINS = 2
RESET_KIND = "admin.company_two_step_off"


def two_step_reset(_context):
    parts = []
    if roles_allowed("company_user.two_step_off") == SUPER_ONLY:
        parts.append(ok("Only a super admin may reset two-step."))
    else:
        parts.append(not_ok("The two-step reset is open to more than super admins."))
    kind = KINDS.get(RESET_KIND)
    if kind is not None and kind.reason_required:
        parts.append(ok("The reset is audited with a reason."))
    else:
        parts.append(not_ok("The two-step reset is not audited with a required reason."))
    return item(1, "Two-step reset by a super admin is audited", parts)


def super_admins(_context):
    count = AdminUser.objects.filter(
        role=AdminUser.Role.SUPER, status=AdminUser.Status.ACTIVE
    ).count()
    if count >= ENOUGH_SUPER_ADMINS:
        part = ok(f"{count} active super admins.")
    else:
        part = not_ok(
            f"Only {count} active super admin(s); create at least {ENOUGH_SUPER_ADMINS}, so "
            "a lost device can always be reset by another one."
        )
    return item(2, "At least two active super admins", [part])


def _plan_problems(name):
    found = list(active_plans().filter(name=name))
    if len(found) != 1:
        return [f"{name}: {len(found)} active plans with this name (needs exactly one)."]
    plan = found[0]
    problems = [f"{name}: {number} is not filled in." for number in missing_for_active(plan)]
    if plan.price_usd is None or plan.price_usd <= 0:
        problems.append(f"{name}: no price in US dollars.")
    return problems


def plans(_context):
    problems = [problem for name in REQUIRED_PLANS for problem in _plan_problems(name)]
    parts = [not_ok(problem) for problem in problems] or [ok("All three plans are ready.")]
    return item(3, "Starter, Growth and Scale are active with prices and numbers", parts)


def pricing_page(_context):
    """Asks the real public route what a visitor sees and compares it with the plans."""
    answer = public_plans(APIRequestFactory().get("/api/plans/"))
    if answer.status_code != 200:
        return item(
            4,
            "The pricing page shows only active plans, with matching prices",
            [not_ok("The pricing page does not load.")],
        )
    shown = {each["id"]: each for each in answer.data}
    active = {plan.pk: plan for plan in active_plans()}
    problems = []
    if set(shown) != set(active):
        problems.append("The pricing page does not show exactly the active plans.")
    for plan_id, plan in active.items():
        each = shown.get(plan_id)
        if each and (plan.price_usd is None or each["price"]["amount"] != f"{plan.price_usd:.2f}"):
            problems.append(f"{plan.name}: the page price does not match the plan.")
    parts = [not_ok(problem) for problem in problems] or [ok("The page matches the plans.")]
    return item(4, "The pricing page shows only active plans, with matching prices", parts)


def _all_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_all_text(each) for each in value.values())
    if isinstance(value, list):
        return " ".join(_all_text(each) for each in value)
    return ""


def legal_pages(_context):
    review = legal_review.status()
    parts = []
    if not review["text_in_place"]:
        parts.append(not_ok("The Terms and Privacy text is not in place."))
    if not review["reviewed"]:
        parts.append(not_ok("The legal text is not marked as reviewed (or changed since)."))
    elif not review["reviewer_name"] or review["reviewed_version"] != review["current_version"]:
        parts.append(not_ok("The review has no reviewer name or is for other text."))
    privacy = _all_text(legal_documents.PRIVACY).lower()
    days = str(get_setting("backup.retention_days"))
    if "backup" not in privacy or days not in privacy:
        parts.append(
            not_ok(
                "The Privacy text must say that deleted data stays in backups for up to "
                f"{days} days."
            )
        )
    return item(5, "Legal pages are ready and reviewed", parts or [ok("Ready and reviewed.")])
