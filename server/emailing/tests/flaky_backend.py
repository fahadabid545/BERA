"""A pretend email provider for the tests that fails on demand."""

import smtplib

from django.core.mail.backends.base import BaseEmailBackend


class FlakyBackend(BaseEmailBackend):
    failures_left = 0
    error = smtplib.SMTPServerDisconnected
    delivered = []
    attempts = 0

    @classmethod
    def reset(cls, failures=0, error=smtplib.SMTPServerDisconnected):
        cls.failures_left, cls.error, cls.delivered, cls.attempts = failures, error, [], 0

    def send_messages(self, email_messages):
        FlakyBackend.attempts += 1
        if FlakyBackend.failures_left > 0:
            FlakyBackend.failures_left -= 1
            raise FlakyBackend.error("provider unavailable")
        FlakyBackend.delivered.extend(email_messages)
        return len(email_messages)
