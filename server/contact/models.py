from django.db import models

from core.protected_fields import EncryptedTextField


class ContactMessage(models.Model):
    """A message sent through the public contact form. It belongs to the platform, not to a
    company. Everything the sender wrote is personal data, so it is stored encrypted and a daily
    job deletes it after the platform's retention period (`contact.retention_days`)."""

    name = EncryptedTextField(purpose="contact_message.name")
    email = EncryptedTextField(purpose="contact_message.email")
    message = EncryptedTextField(purpose="contact_message.message")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
