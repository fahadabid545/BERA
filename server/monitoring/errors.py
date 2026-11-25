"""Counting server errors, so a burst of them can raise an alert. Counts only."""

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import ErrorCount

logger = logging.getLogger(__name__)
KEEP_FOR = timedelta(days=1)


def _this_minute():
    return timezone.now().replace(second=0, microsecond=0)


def count_server_error():
    """Called wherever the app answers with a server error. Never raises: counting must not turn
    one failure into two, and it fails exactly when the database is down."""
    minute = _this_minute()
    try:
        if ErrorCount.objects.filter(minute=minute).update(count=F("count") + 1):
            return
        try:
            with transaction.atomic():
                ErrorCount.objects.create(minute=minute, count=1)
        except IntegrityError:  # another request created it a moment ago
            ErrorCount.objects.filter(minute=minute).update(count=F("count") + 1)
    except Exception as error:
        logger.warning("A server error could not be counted (%s).", type(error).__name__)


def errors_in_the_last(minutes):
    since = _this_minute() - timedelta(minutes=minutes - 1)
    return ErrorCount.objects.filter(minute__gte=since).aggregate(total=Sum("count"))["total"] or 0


def forget_old_counts():
    ErrorCount.objects.filter(minute__lt=timezone.now() - KEEP_FOR).delete()
