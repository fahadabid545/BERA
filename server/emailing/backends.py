import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class DevInboxBackend(BaseEmailBackend):
    """Development only: saves each message as a readable .eml file, sends nothing."""

    def send_messages(self, email_messages):
        folder = Path(settings.EMAIL_FILE_PATH)
        folder.mkdir(parents=True, exist_ok=True)
        for message in email_messages:
            template = re.sub(r"[^a-z_]", "", message.extra_headers.get("X-Bera-Template", ""))
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            name = f"{stamp}-{template or 'message'}-{secrets.token_hex(3)}.eml"
            (folder / name).write_bytes(message.message().as_bytes())
        return len(email_messages)
