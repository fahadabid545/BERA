"""Keeps sessions in step with the account they belong to.

A session ends the moment its person is blocked or removed, or changes their password. Each
check on a request also looks at the account, so a token is refused even where this cannot
run (a bulk update skips signals); ending the session as well means that setting the person
active again later does not bring old tokens back to life.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from adminusers.models import AdminUser
from companies.models import CompanyUser

from . import service
from .kinds import ADMIN, COMPANY
from .service import RevokeReason

KIND_OF_MODEL = {CompanyUser: COMPANY, AdminUser: ADMIN}
ENDING_STATUSES = {"blocked": RevokeReason.BLOCKED, "removed": RevokeReason.REMOVED}


@receiver(pre_save, sender=CompanyUser)
@receiver(pre_save, sender=AdminUser)
def note_password_change(sender, instance, **_):
    stored = sender.objects.filter(pk=instance.pk).values_list("password_hash", flat=True).first()
    # `stored` is None for a new person; an empty string is a real (unset) password.
    instance._password_changed = stored is not None and stored != instance.password_hash


@receiver(post_save, sender=CompanyUser)
@receiver(post_save, sender=AdminUser)
def end_sessions_that_should_not_continue(sender, instance, created, **_):
    if created:
        return
    kind = KIND_OF_MODEL[sender]
    if instance.status in ENDING_STATUSES:
        service.revoke_user_sessions(instance.pk, ENDING_STATUSES[instance.status], kind=kind)
    elif getattr(instance, "_password_changed", False):
        service.revoke_user_sessions(instance.pk, RevokeReason.PASSWORD_CHANGED, kind=kind)
