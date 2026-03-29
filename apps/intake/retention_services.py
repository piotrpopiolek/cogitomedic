"""Local intake PDF retention: delete file and clear health-related payloads after HiDrive archive."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.db import transaction
from django.db.utils import OperationalError
from django.utils import timezone

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError
from apps.core.retention_payloads import RETENTION_CLEARED_INTAKE_SNAPSHOT
from apps.intake.models import IntakeDocumentVersion, IntakePdfStatus
from apps.operations.services import create_audit_event
from apps.outbox.services import RetentionCleanupResult, _try_delete_file


def _process_single_intake_version_retention(
    version_id: uuid.UUID,
    *,
    older_than_days: int,
    dry_run: bool,
    threshold: datetime,
) -> tuple[bool, bool]:
    """Returns (deleted, skipped_not_safe)."""
    try:
        with transaction.atomic():
            try:
                version = (
                    IntakeDocumentVersion.objects.select_for_update(nowait=True)
                    .select_related(
                        "intake_form",
                        "intake_form__queue_entry",
                        "intake_form__queue_entry__daily_queue",
                    )
                    .get(
                        id=version_id,
                        pdf_generation_status=IntakePdfStatus.COMPLETED,
                        created_at__lte=threshold,
                        local_pdf_deleted_at__isnull=True,
                    )
                )
            except IntakeDocumentVersion.DoesNotExist:
                return False, False

            if not version.hidrive_sent:
                create_audit_event(
                    event_type="INTAKE_RETENTION_FILE_SKIPPED",
                    patient_id=version.intake_form.queue_entry.patient_id,
                    context_clinic_site_id=version.intake_form.queue_entry.daily_queue.clinic_site_id,
                    metadata={
                        "intake_document_version_id": str(version.id),
                        "reason": "NOT_SAFE_FOR_DELETION",
                    },
                )
                return False, True

            if dry_run:
                return False, False

            now = timezone.now()
            _try_delete_file(version.pdf_local_path)
            intake_form = version.intake_form
            version.local_pdf_deleted_at = now
            version.pdf_local_path = None
            version.snapshot_payload = dict(RETENTION_CLEARED_INTAKE_SNAPSHOT)
            version.save(
                update_fields=[
                    "local_pdf_deleted_at",
                    "pdf_local_path",
                    "snapshot_payload",
                ]
            )
            intake_form.anamnesis_payload = {}
            intake_form.body_map_data = []
            intake_form.save(update_fields=["anamnesis_payload", "body_map_data", "updated_at"])

            create_audit_event(
                event_type="INTAKE_RETENTION_FILE_DELETED",
                patient_id=intake_form.queue_entry.patient_id,
                context_clinic_site_id=intake_form.queue_entry.daily_queue.clinic_site_id,
                metadata={
                    "intake_document_version_id": str(version.id),
                    "older_than_days": older_than_days,
                },
            )
            return True, False
    except OperationalError:
        return False, False


def run_intake_retention_cleanup(*, older_than_days: int = 30, dry_run: bool = True) -> RetentionCleanupResult:
    if older_than_days <= 0:
        raise DomainError(
            domain_message("other.domain.retention_days_positive"),
            api_message_key="other.domain.retention_days_positive",
        )

    threshold = timezone.now() - timedelta(days=older_than_days)
    candidate_ids = list(
        IntakeDocumentVersion.objects.filter(
            pdf_generation_status=IntakePdfStatus.COMPLETED,
            created_at__lte=threshold,
            local_pdf_deleted_at__isnull=True,
        )
        .order_by("created_at")
        .values_list("id", flat=True)
    )

    deleted = 0
    skipped_not_safe = 0
    for vid in candidate_ids:
        did_delete, did_skip = _process_single_intake_version_retention(
            vid,
            older_than_days=older_than_days,
            dry_run=dry_run,
            threshold=threshold,
        )
        if did_delete:
            deleted += 1
        if did_skip:
            skipped_not_safe += 1

    return RetentionCleanupResult(
        candidates=len(candidate_ids),
        deleted=deleted,
        skipped_not_safe=skipped_not_safe,
    )
