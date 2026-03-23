from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.intake.models import IntakeDocumentVersion, IntakeOutboxEvent, IntakeOutboxEventType, IntakeOutboxStatus
from apps.medical.models import MedicalDocumentVersion
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus


class Command(BaseCommand):
    help = (
        "Reset recent HiDrive upload outbox events (PROCESSED/FAILED) to PENDING and clear "
        "hidrive_* on the linked document version so the worker can upload again."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Max events per stream (medical HIDRIVE_UPLOAD and intake HIDRIVE_UPLOAD_INTAKE_PDF). Default: 20.",
        )
        parser.add_argument(
            "--since-days",
            type=int,
            default=None,
            help="Only consider events created in the last N days (optional).",
        )
        parser.add_argument(
            "--include-dead-letter",
            action="store_true",
            help="Also reset DEAD_LETTER events (default: only PROCESSED and FAILED).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be reset without writing.",
        )

    def handle(self, *args, **options) -> None:
        limit = options["limit"]
        since_days = options["since_days"]
        include_dl = options["include_dead_letter"]
        dry_run = options["dry_run"]

        statuses = [OutboxStatus.PROCESSED, OutboxStatus.FAILED]
        intake_statuses = [IntakeOutboxStatus.PROCESSED, IntakeOutboxStatus.FAILED]
        if include_dl:
            statuses.append(OutboxStatus.DEAD_LETTER)
            intake_statuses.append(IntakeOutboxStatus.DEAD_LETTER)

        now = timezone.now()
        cutoff = None
        if since_days is not None:
            cutoff = now - timedelta(days=since_days)

        def filter_since(qs):
            if cutoff is None:
                return qs
            return qs.filter(created_at__gte=cutoff)

        medical_qs = (
            filter_since(
                OutboxEvent.objects.filter(
                    event_type=OutboxEventType.HIDRIVE_UPLOAD,
                    status__in=statuses,
                )
            )
            .select_related("medical_document_version")
            .order_by("-created_at")[:limit]
        )

        intake_qs = (
            filter_since(
                IntakeOutboxEvent.objects.filter(
                    event_type=IntakeOutboxEventType.HIDRIVE_UPLOAD_INTAKE_PDF,
                    status__in=intake_statuses,
                )
            )
            .select_related("intake_document_version")
            .order_by("-created_at")[:limit]
        )

        medical_list = list(medical_qs)
        intake_list = list(intake_qs)

        self.stdout.write(
            f"Medical HIDRIVE_UPLOAD to reset: {len(medical_list)} "
            f"(limit={limit}, since_days={since_days}, dry_run={dry_run})"
        )
        self.stdout.write(
            f"Intake HIDRIVE_UPLOAD_INTAKE_PDF to reset: {len(intake_list)} "
            f"(limit={limit}, since_days={since_days}, dry_run={dry_run})"
        )

        if dry_run:
            for e in medical_list:
                self.stdout.write(
                    f"  [medical] {e.id} status={e.status} version={e.medical_document_version_id}"
                )
            for e in intake_list:
                self.stdout.write(
                    f"  [intake] {e.id} status={e.status} version={e.intake_document_version_id}"
                )
            return

        with transaction.atomic():
            for e in medical_list:
                self._reset_medical_event(e, now)
            for e in intake_list:
                self._reset_intake_event(e, now)

        self.stdout.write(self.style.SUCCESS("Done."))

    def _reset_medical_event(self, event: OutboxEvent, now) -> None:
        v = event.medical_document_version
        OutboxEvent.objects.filter(pk=event.pk).update(
            status=OutboxStatus.PENDING,
            processed_at=None,
            error_message=None,
            locked_at=None,
            available_at=now,
            retry_count=0,
        )
        MedicalDocumentVersion.objects.filter(pk=v.pk).update(
            hidrive_path=None,
            hidrive_sent=False,
            hidrive_sent_at=None,
        )

    def _reset_intake_event(self, event: IntakeOutboxEvent, now) -> None:
        v = event.intake_document_version
        IntakeOutboxEvent.objects.filter(pk=event.pk).update(
            status=IntakeOutboxStatus.PENDING,
            processed_at=None,
            error_message=None,
            locked_at=None,
            available_at=now,
            retry_count=0,
        )
        IntakeDocumentVersion.objects.filter(pk=v.pk).update(
            hidrive_path=None,
            hidrive_sent=False,
            hidrive_sent_at=None,
        )
