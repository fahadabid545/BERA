from django.db import models


class CheckStreak(models.Model):
    """How many checks in a row found one measurement over its limit. Each run of the health
    check is a new process, so the count lives here."""

    name = models.CharField(max_length=40, primary_key=True)
    consecutive = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class ErrorCount(models.Model):
    """How many server errors happened in one minute. A number only: nothing about the request,
    the person or the failure is kept here (the log holds the reference)."""

    minute = models.DateTimeField(primary_key=True)
    count = models.PositiveIntegerField(default=0)
