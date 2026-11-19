from django.db import models

from core.models import CompanyOwnedModel


class NotificationChoice(CompanyOwnedModel):
    """One person's choice for one optional email. No row means the default: it is sent."""

    user = models.ForeignKey("companies.CompanyUser", on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=40)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "kind"], name="one_choice_per_user_and_kind"),
        ]


class NotificationSent(CompanyOwnedModel):
    """Remembers that an email went out, so it never goes out twice. `key` names the occasion
    (an upload, a usage period and level, a subscription end date): ids and dates only."""

    kind = models.CharField(max_length=40)
    key = models.CharField(max_length=120)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "kind", "key"], name="one_notification_per_occasion"
            ),
        ]
