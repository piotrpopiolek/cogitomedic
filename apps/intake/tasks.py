from __future__ import annotations

from django.conf import settings
from django.tasks import task

from apps.intake.outbox_services import (
    process_intake_outbox_events as process_intake_outbox_events_service,
)
from apps.intake.retention_services import (
    run_intake_retention_cleanup as run_intake_retention_cleanup_service,
)


@task(queue_name="outbox")
def process_intake_outbox_events() -> None:
    process_intake_outbox_events_service()


@task(queue_name="retention")
def run_intake_retention_cleanup() -> None:
    run_intake_retention_cleanup_service(
        older_than_days=settings.PDF_RETENTION_DAYS,
        dry_run=False,
    )
