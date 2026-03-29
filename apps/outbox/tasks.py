from __future__ import annotations

from django.conf import settings
from django.tasks import task

from apps.outbox.services import process_outbox_events as process_outbox_events_service
from apps.outbox.services import run_retention_cleanup as run_retention_cleanup_service


@task(queue_name="outbox")
def process_outbox_events() -> None:
    process_outbox_events_service()


@task(queue_name="retention")
def run_retention_cleanup() -> None:
    run_retention_cleanup_service(
        older_than_days=settings.PDF_RETENTION_DAYS,
        dry_run=False,
    )
