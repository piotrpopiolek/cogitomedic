from __future__ import annotations

from django.tasks import task

from apps.intake.outbox_services import process_intake_outbox_events as process_intake_outbox_events_service


@task(queue_name="outbox")
def process_intake_outbox_events() -> None:
    process_intake_outbox_events_service()
