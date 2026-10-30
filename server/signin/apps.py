from django.apps import AppConfig


class SigninConfig(AppConfig):
    name = "signin"

    def ready(self):
        from . import signals  # noqa: F401  (connects the receivers)
