from __future__ import annotations

from django.tasks import task

from apps.outbox.services import process_outbox_events as process_outbox_events_service


@task(queue_name="outbox")
def process_outbox_events() -> None:
    process_outbox_events_service()


@task(queue_name="retention")
def run_retention_cleanup() -> None:
    """
    Remove eligible local PDFs according to retention policy.

    Execution logic is intentionally placeholder for now and will be
    implemented in the outbox/integrations step.
    """
    return
