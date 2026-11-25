"""Contact messages are kept for `contact.retention_days`, then a daily job deletes them. Only
a count is logged."""

import logging
from datetime import timedelta

from django.utils import timezone

from core.jobs import logged_job
from platform_settings.service import get_setting

from .models import ContactMessage

logger = logging.getLogger(__name__)


@logged_job
def purge_old_messages():
    cutoff = timezone.now() - timedelta(days=get_setting("contact.retention_days"))
    deleted, _ = ContactMessage.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        logger.info("Deleted %s old contact messages.", deleted)
