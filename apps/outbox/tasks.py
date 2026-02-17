from __future__ import annotations

from django.tasks import task


@task(queue_name="outbox")
def process_outbox_events() -> None:
    """
    Process outbox events in background.

    Execution logic is intentionally placeholder for now and will be
    implemented in the outbox/integrations step.
    """
    return


@task(queue_name="retention")
def run_retention_cleanup() -> None:
    """
    Remove eligible local PDFs according to retention policy.

    Execution logic is intentionally placeholder for now and will be
    implemented in the outbox/integrations step.
    """
    return
