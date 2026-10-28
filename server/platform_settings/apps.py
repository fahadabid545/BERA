from django.apps import AppConfig


class PlatformSettingsConfig(AppConfig):
    name = "platform_settings"

    def ready(self):
        from . import service  # noqa: F401  (connects the cache-clearing signals)
