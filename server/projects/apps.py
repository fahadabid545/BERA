from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    name = "projects"

    def ready(self):
        # Registers what the project's deletion must remove (see deletion.py).
        from . import requirements  # noqa: F401
