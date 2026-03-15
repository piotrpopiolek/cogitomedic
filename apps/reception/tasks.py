from __future__ import annotations

import uuid

from django.tasks import task

# from apps.reception.pdf_import import process_patient_pdf_import_batch  # optional: pdfplumber


@task(queue_name="imports")
def run_daily_import() -> None:
    """
    Run the daily import pipeline for reception queue entries.

    Execution logic is intentionally placeholder for now and will be
    implemented in the import/integrations step.
    """
    return


@task(queue_name="imports")
def run_patient_pdf_import(batch_id: str, stored_file_path: str) -> None:
    from apps.reception.pdf_import import process_patient_pdf_import_batch

    process_patient_pdf_import_batch(
        batch_id=uuid.UUID(batch_id),
        stored_file_path=stored_file_path,
    )
