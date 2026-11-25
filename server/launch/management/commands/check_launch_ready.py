from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from launch.context import Context
from launch.report import run_all
from launch.results import NOT_OK, OWNER

NOT_PRODUCTION = "Run this on the production server, with the production settings."
FAILED = "NOT READY: at least one item is NOT OK."
DEFAULT_STAGING_ENV = "/etc/bera/staging.env"
DEFAULT_PRODUCTION_ENV = "/etc/bera/production.env"


class Command(BaseCommand):
    help = (
        "Checks everything that can be checked before the launch and prints each item as OK, "
        "NOT OK or owner must confirm. Exits with an error when any item is NOT OK. "
        "There is no option to skip an item."
    )

    def add_arguments(self, parser):
        parser.add_argument("--staging-env", default=DEFAULT_STAGING_ENV)
        parser.add_argument("--production-env", default=DEFAULT_PRODUCTION_ENV)

    def handle(self, *args, **options):
        if settings.APP_ENV != "production":
            raise CommandError(NOT_PRODUCTION)
        context = Context(
            project_folder=Path(settings.BASE_DIR).parent,
            staging_env_file=Path(options["staging_env"]),
            production_env_file=Path(options["production_env"]),
        )
        items = run_all(context)
        for each in items:
            self.stdout.write(f"{each.number:>2}. [{each.status}] {each.title}")
            for note in each.notes:
                self.stdout.write(f"      - {note}")
        failed = sum(1 for each in items if each.status == NOT_OK)
        waiting = sum(1 for each in items if each.status == OWNER)
        self.stdout.write(
            f"{len(items) - failed - waiting} OK, {failed} NOT OK, {waiting} for the owner "
            "to confirm in the README checklist."
        )
        if failed:
            raise CommandError(FAILED)
