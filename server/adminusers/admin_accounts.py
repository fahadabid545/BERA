"""Changing an admin's role or status, keeping at least one super admin who can sign in.

A role change needs no extra step to apply at once: every request reads the admin's role
from the database (signin/service.py), not from the token.
"""

from django.db import transaction

from audit.service import record
from core.errors import AppError

from .models import AdminUser

LAST_SUPER_ADMIN = "There must always be one active super admin, so this cannot be done."


def _refuse_if_last_super_admin(admin):
    """Call inside the transaction, after locking the super admins."""
    others = (
        AdminUser.objects.select_for_update()
        .filter(role=AdminUser.Role.SUPER, status=AdminUser.Status.ACTIVE)
        .exclude(pk=admin.pk)
    )
    is_active_super = admin.role == AdminUser.Role.SUPER and admin.status == AdminUser.Status.ACTIVE
    if is_active_super and not others.exists():
        raise AppError("last_super_admin", LAST_SUPER_ADMIN, status_code=409)


def _change(admin_id, by, reason, kind, **fields):
    with transaction.atomic():
        # Two changes at once must not both see "another super admin is still there".
        admin = AdminUser.objects.select_for_update().get(pk=admin_id)
        new_role = fields.get("role", admin.role)
        new_status = fields.get("status", admin.status)
        stays_active_super = (
            new_role == AdminUser.Role.SUPER and new_status == AdminUser.Status.ACTIVE
        )
        if not stays_active_super:
            _refuse_if_last_super_admin(admin)
        changes = {f"{name}_before": getattr(admin, name) for name in fields} | {
            f"{name}_after": value for name, value in fields.items()
        }
        for name, value in fields.items():
            setattr(admin, name, value)
        admin.save(update_fields=list(fields))
        # In the same transaction: without the written reason the change is undone.
        record(kind, actor=by, target=admin, reason=reason, details=changes)
    return admin


def change_role(admin_id, role, *, by, reason):
    """Makes the admin a super admin or support. Demoting the last super admin is refused.
    `by` is the admin doing it; the written reason goes in the audit log."""
    return _change(admin_id, by, reason, "admin.role_changed", role=role)


def set_status(admin_id, status, *, by, reason):
    """Blocks, unblocks or removes an admin. Anything that takes away the last super admin's
    access is refused. `by` is the admin doing it; the written reason goes in the audit log."""
    return _change(admin_id, by, reason, "admin.status_changed", status=status)
