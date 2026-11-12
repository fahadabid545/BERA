import getpass

from django.core.management.base import BaseCommand, CommandError

from adminusers.first_super_admin import create_first_super_admin
from core.errors import AppError


class Command(BaseCommand):
    help = (
        "Create the first super admin. Run once on the server; it refuses if any admin exists. "
        "The password is typed at a hidden prompt, never given as an option."
    )

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--email", required=True)

    def handle(self, *args, name, email, **options):
        password = getpass.getpass("Password: ")
        if getpass.getpass("Password (again): ") != password:
            raise CommandError("The two passwords are not the same.")
        try:
            create_first_super_admin(name=name, email=email, password=password)
        except AppError as error:
            raise CommandError(error.message) from error
        self.stdout.write(
            "The first super admin was created. They set up their authenticator app "
            "at their first login."
        )
