from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.outbox.tasks import process_outbox_events, run_retention_cleanup
from apps.reception.tasks import run_daily_import


class Command(BaseCommand):
    help = "Enqueue configured background tasks using Django Tasks."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--skip-import",
            action="store_true",
            help="Skip enqueuing daily import task.",
        )
        parser.add_argument(
            "--retention-only",
            action="store_true",
            help="Enqueue only retention task.",
        )

    def handle(self, *args, **options) -> None:
        if options["retention_only"]:
            run_retention_cleanup.enqueue()
            self.stdout.write(self.style.SUCCESS("Enqueued: run_retention_cleanup"))
            return

        process_outbox_events.enqueue()
        self.stdout.write(self.style.SUCCESS("Enqueued: process_outbox_events"))

        run_retention_cleanup.enqueue()
        self.stdout.write(self.style.SUCCESS("Enqueued: run_retention_cleanup"))

        if not options["skip_import"]:
            run_daily_import.enqueue()
            self.stdout.write(self.style.SUCCESS("Enqueued: run_daily_import"))
