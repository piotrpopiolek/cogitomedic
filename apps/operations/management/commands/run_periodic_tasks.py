from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.intake.tasks import process_intake_outbox_events, run_intake_retention_cleanup
from apps.outbox.tasks import process_outbox_events, run_retention_cleanup
from apps.reception.tasks import run_daily_import


class Command(BaseCommand):
    help = "Run periodic task enqueue loop (Django Tasks)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--interval-seconds",
            type=int,
            default=300,
            help="How often to enqueue tasks (default: 300 seconds).",
        )
        parser.add_argument(
            "--skip-import",
            action="store_true",
            help="Skip enqueuing daily import task.",
        )
        parser.add_argument(
            "--retention-only",
            action="store_true",
            help="Enqueue only retention task every interval.",
        )

    def handle(self, *args, **options) -> None:
        interval = options["interval_seconds"]
        if interval <= 0:
            raise ValueError("interval-seconds must be positive.")

        skip_import = options["skip_import"]
        retention_only = options["retention_only"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting periodic task scheduler (interval={interval}s, "
                f"skip_import={skip_import}, retention_only={retention_only})"
            )
        )

        try:
            while True:
                now = timezone.now().isoformat()

                if retention_only:
                    run_retention_cleanup.enqueue()
                    self.stdout.write(f"[{now}] Enqueued: run_retention_cleanup")
                    run_intake_retention_cleanup.enqueue()
                    self.stdout.write(f"[{now}] Enqueued: run_intake_retention_cleanup")
                else:
                    process_outbox_events.enqueue()
                    self.stdout.write(f"[{now}] Enqueued: process_outbox_events")

                    process_intake_outbox_events.enqueue()
                    self.stdout.write(f"[{now}] Enqueued: process_intake_outbox_events")

                    run_retention_cleanup.enqueue()
                    self.stdout.write(f"[{now}] Enqueued: run_retention_cleanup")

                    run_intake_retention_cleanup.enqueue()
                    self.stdout.write(f"[{now}] Enqueued: run_intake_retention_cleanup")

                    if not skip_import:
                        run_daily_import.enqueue()
                        self.stdout.write(f"[{now}] Enqueued: run_daily_import")

                self.stdout.flush()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Stopping periodic task scheduler."))
