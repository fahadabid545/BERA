import email
import email.policy
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "List the emails staging saved instead of sending (newest last), or show one with --show. "
        "Staging and development only."
    )

    def add_arguments(self, parser):
        parser.add_argument("--show", help="The file name to read, as listed.")

    def handle(self, *args, **options):
        if settings.APP_ENV == "production":
            raise CommandError("Production sends real email; there is no folder to read.")
        folder = Path(settings.EMAIL_FILE_PATH)
        files = sorted(folder.glob("*.eml")) if folder.is_dir() else []
        if options["show"]:
            return self.show(folder, options["show"])
        if not files:
            self.stdout.write("No saved emails.")
        for file in files:
            message = email.message_from_bytes(file.read_bytes(), policy=email.policy.default)
            self.stdout.write(f"{file.name}  to: {message['To']}  subject: {message['Subject']}")

    def show(self, folder, name):
        file = folder / Path(name).name  # a name only, never a path
        if file.suffix != ".eml" or not file.is_file():
            raise CommandError("No such saved email.")
        message = email.message_from_bytes(file.read_bytes(), policy=email.policy.default)
        body = message.get_body(("plain",))
        self.stdout.write(f"To: {message['To']}\nSubject: {message['Subject']}\n")
        self.stdout.write(body.get_content() if body else "")
