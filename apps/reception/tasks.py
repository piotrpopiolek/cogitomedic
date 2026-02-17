from __future__ import annotations

from django.tasks import task


@task(queue_name="imports")
def run_daily_import() -> None:
    """
    Run the daily import pipeline for reception queue entries.

    Execution logic is intentionally placeholder for now and will be
    implemented in the import/integrations step.
    """
    return
