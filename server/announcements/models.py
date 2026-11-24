from django.db import models
from django.db.models import F, Q

from core.models import CompanyOwnedModel

# The column size; the length people may actually write is the `announcements.max_message_length`
# setting, which may never be set above this.
MESSAGE_COLUMN_LENGTH = 2000


class Announcement(models.Model):
    """A banner admins show in the company panel between two moments, to everyone, to the
    companies on one plan, or to chosen companies. It belongs to the platform, not to a company."""

    class Target(models.TextChoices):
        EVERYONE = "everyone"
        PLAN = "plan"
        COMPANIES = "companies"

    message = models.CharField(max_length=MESSAGE_COLUMN_LENGTH)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    target = models.CharField(max_length=10, choices=Target.choices)
    # A plan that is deleted takes its banners with it: they would have nobody left to reach.
    plan = models.ForeignKey("plans.Plan", null=True, on_delete=models.CASCADE, related_name="+")
    companies = models.ManyToManyField("companies.Company", related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(target__in=["everyone", "plan", "companies"]),
                name="announcement_target_is_known",
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="announcement_ends_after_start"
            ),
            models.CheckConstraint(
                condition=Q(target="plan", plan__isnull=False)
                | (~Q(target="plan") & Q(plan__isnull=True)),
                name="announcement_plan_only_for_plan_target",
            ),
        ]


class AnnouncementDismissal(CompanyOwnedModel):
    """One person closed one banner. It stays closed for them; everyone else still sees it."""

    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey("companies.CompanyUser", on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "user"], name="one_dismissal_per_person_and_banner"
            ),
        ]
