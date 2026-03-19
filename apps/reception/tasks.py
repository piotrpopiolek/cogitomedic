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


@task(queue_name="imports")
def run_patient_xlsx_import(
    batch_id: str,
    stored_file_path: str,
) -> None:
    """Process XLSX patient import batch in the background."""
    import uuid

    from apps.reception.xlsx_import import process_patient_xlsx_import_batch

    process_patient_xlsx_import_batch(
        batch_id=uuid.UUID(batch_id),
        stored_file_path=stored_file_path,
    )
