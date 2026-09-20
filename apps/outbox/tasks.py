from __future__ import annotations

from django.conf import settings
from django.tasks import task

from apps.outbox import services as outbox_services
from apps.outbox.services import run_retention_cleanup as run_retention_cleanup_service


@task(queue_name="outbox")
def process_outbox_events() -> None:
    outbox_services.process_outbox_events(
        hidrive_adapter=outbox_services.get_hidrive_adapter(),
        sms_adapter=outbox_services.get_sms_adapter(),
    )


@task(queue_name="retention")
def run_retention_cleanup() -> None:
    run_retention_cleanup_service(
        older_than_days=settings.PDF_RETENTION_DAYS,
        dry_run=False,
    )
