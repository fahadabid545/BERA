from django.core.management.base import BaseCommand, CommandError

from monitoring.service import run_health_check


class Command(BaseCommand):
    help = (
        "Measure disk, memory, waiting jobs, queued emails and server errors; alert the super "
        "admins; and send the heartbeat ping when all is well. Run every 5 minutes by a timer."
    )

    def handle(self, *args, **options):
        measurements, fine = run_health_check()
        for item in measurements:
            self.stdout.write(
                f"{'OVER' if item.over else 'ok  '} {item.name}: {item.value}{item.unit}"
            )
        if not fine:
            raise CommandError("A check is over its limit, or the heartbeat could not be sent.")
