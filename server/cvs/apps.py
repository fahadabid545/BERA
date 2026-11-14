from django.apps import AppConfig


class CvsConfig(AppConfig):
    name = "cvs"

    def ready(self):
        # Registers what a project's deletion must remove (see projects/deletion.py).
        from . import (  # noqa: F401
            ats_scoring,
            candidates,
            evaluation,
            extra_factors,
            fairness,
            profile_reading,
            scoring,
            service,
            steps,
        )
