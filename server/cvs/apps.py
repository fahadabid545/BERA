from django.apps import AppConfig


class CvsConfig(AppConfig):
    name = "cvs"

    def ready(self):
        # Registers what a project's deletion must remove (see projects/deletion.py).
        from . import service  # noqa: F401
