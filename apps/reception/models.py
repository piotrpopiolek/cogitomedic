from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

class PatientIdentityStatus(models.TextChoices):
    CONFIRMED = "CONFIRMED", "Confirmed"
    TEMPORARY = "TEMPORARY", "Temporary"


class PatientExternalSource(models.TextChoices):
    DOCTOLIB_EXPORT = "DOCTOLIB_EXPORT", "Doctolib Export"
    OTHER = "OTHER", "Other"


class QueueShift(models.TextChoices):
    FULL_DAY = "FULL_DAY", "Full day"
    MORNING = "MORNING", "Morning"
    AFTERNOON = "AFTERNOON", "Afternoon"
    EVENING = "EVENING", "Evening"


class QueueSource(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    IMPORT = "IMPORT", "Import"


class QueueStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"


class QueueEntryStatus(models.TextChoices):
    WAITING = "WAITING", "Waiting"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    PATIENT_COMPLETED = "PATIENT_COMPLETED", "Patient completed"
    DOCTOR_IN_PROGRESS = "DOCTOR_IN_PROGRESS", "Doctor in progress"
    PUBLISHED = "PUBLISHED", "Published"
    CANCELLED = "CANCELLED", "Cancelled"


class ImportType(models.TextChoices):
    DAILY_FILE_IMPORT = "DAILY_FILE_IMPORT", "Daily file import"
    EMERGENCY_TEMPLATE_IMPORT = "EMERGENCY_TEMPLATE_IMPORT", "Emergency template import"


class ImportSourceSystem(models.TextChoices):
    DOCTOLIB_EXPORT = "DOCTOLIB_EXPORT", "Doctolib export"
    OTHER = "OTHER", "Other"


class ImportStatus(models.TextChoices):
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS", "Completed with errors"
    FAILED = "FAILED", "Failed"


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    doctolib_patient_id = models.CharField(max_length=64, blank=True, null=True, unique=True)
    identity_status = models.CharField(
        max_length=20,
        choices=PatientIdentityStatus.choices,
        default=PatientIdentityStatus.TEMPORARY,
    )
    identity_alert_created_at = models.DateTimeField(blank=True, null=True)
    identity_resolution_due_at = models.DateTimeField(blank=True, null=True)
    street = models.CharField(max_length=150, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country_code = models.CharField(max_length=2, default="DE")
    external_source = models.CharField(
        max_length=30, choices=PatientExternalSource.choices, blank=True, null=True
    )
    external_source_id = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "patient"
        indexes = [
            models.Index(fields=["last_name", "first_name", "date_of_birth"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["identity_status", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["external_source", "external_source_id"],
                name="patient_external_unique",
            ),
            models.CheckConstraint(
                condition=Q(phone__regex=r"^[0-9+() -]{7,20}$"),
                name="patient_phone_format",
            ),
            models.CheckConstraint(
                condition=Q(
                    identity_status__in=[
                        PatientIdentityStatus.CONFIRMED,
                        PatientIdentityStatus.TEMPORARY,
                    ]
                ),
                name="patient_identity_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(doctolib_patient_id__isnull=False)
                | (
                    Q(identity_alert_created_at__isnull=False)
                    & Q(identity_resolution_due_at__isnull=False)
                ),
                name="patient_temp_identity_requires_alert",
            ),
            models.CheckConstraint(
                condition=Q(identity_resolution_due_at__isnull=True)
                | Q(identity_alert_created_at__isnull=True)
                | Q(identity_resolution_due_at__gte=F("identity_alert_created_at")),
                name="patient_identity_due_after_alert",
            ),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        self.identity_status = (
            PatientIdentityStatus.CONFIRMED
            if self.doctolib_patient_id
            else PatientIdentityStatus.TEMPORARY
        )
        super().save(*args, **kwargs)


class PatientContactHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="contact_history")
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="changed_contacts",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "patient_contact_history"


class ClinicSite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clinic_site"


class ConsultingRoom(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinic_site = models.ForeignKey(ClinicSite, on_delete=models.RESTRICT, related_name="rooms")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "consulting_room"
        constraints = [
            models.UniqueConstraint(
                fields=["clinic_site", "code"],
                name="consulting_room_site_code_unique",
            )
        ]


class DailyQueue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    queue_date = models.DateField()
    clinic_site = models.ForeignKey(ClinicSite, on_delete=models.RESTRICT, related_name="daily_queues")
    consulting_room = models.ForeignKey(
        ConsultingRoom, on_delete=models.RESTRICT, related_name="daily_queues"
    )
    shift_code = models.CharField(max_length=20, choices=QueueShift.choices, default=QueueShift.FULL_DAY)
    source = models.CharField(max_length=20, choices=QueueSource.choices, default=QueueSource.MANUAL)
    status = models.CharField(max_length=20, choices=QueueStatus.choices, default=QueueStatus.OPEN)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="created_queues"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "daily_queue"
        indexes = [
            models.Index(fields=["queue_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["queue_date", "clinic_site", "consulting_room", "shift_code"],
                name="daily_queue_unique_slot",
            )
        ]


class QueueEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daily_queue = models.ForeignKey(DailyQueue, on_delete=models.CASCADE, related_name="entries")
    patient = models.ForeignKey(Patient, on_delete=models.RESTRICT, related_name="queue_entries")
    active_session = models.ForeignKey(
        "PatientFormSession",
        on_delete=models.RESTRICT,
        blank=True,
        null=True,
        related_name="+",
    )
    entry_status = models.CharField(
        max_length=30,
        choices=QueueEntryStatus.choices,
        default=QueueEntryStatus.WAITING,
    )
    position_no = models.IntegerField()
    visit_external_id = models.CharField(max_length=100, blank=True, null=True)
    appointment_time = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_queue_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "queue_entry"
        indexes = [
            models.Index(fields=["daily_queue", "entry_status", "position_no"]),
            models.Index(fields=["patient", "-created_at"]),
            models.Index(fields=["active_session"]),
            models.Index(
                fields=["daily_queue", "position_no"],
                name="qentry_active_pos_idx",
                condition=Q(entry_status__in=[QueueEntryStatus.WAITING, QueueEntryStatus.IN_PROGRESS]),
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["daily_queue", "position_no"],
                name="queue_entry_position_unique",
            ),
            models.UniqueConstraint(
                fields=["daily_queue", "visit_external_id"],
                condition=Q(visit_external_id__isnull=False),
                name="queue_entry_visit_external_unique",
            ),
        ]


class TabletDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    device_code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tablet_device"


class PatientFormSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    queue_entry = models.ForeignKey(
        QueueEntry, on_delete=models.CASCADE, related_name="form_sessions"
    )
    tablet_device = models.ForeignKey(
        TabletDevice,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sessions",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    form_locale = models.CharField(max_length=10, default="de-DE")
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(blank=True, null=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_form_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "patient_form_session"
        indexes = [
            models.Index(fields=["queue_entry", "consumed_at"]),
            models.Index(fields=["queue_entry", "-created_at"]),
            models.Index(fields=["form_locale", "-created_at"]),
            models.Index(
                fields=["expires_at"],
                name="session_unconsumed_expires_idx",
                condition=Q(consumed_at__isnull=True),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="session_expiry_after_create",
            ),
            models.CheckConstraint(
                condition=Q(form_locale__regex=r"^(de|en)(-[A-Z]{2})?$"),
                name="session_locale_format",
            ),
            models.CheckConstraint(
                condition=Q(consumed_at__isnull=True) | Q(consumed_at__lte=F("expires_at")),
                name="session_consumed_before_expiry",
            ),
        ]

    @classmethod
    def issue_token(cls, queue_entry: QueueEntry, created_by_user_id: str, minutes: int = 20) -> str:
        token_plain = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token_plain.encode("utf-8")).hexdigest()
        session = cls.objects.create(
            queue_entry=queue_entry,
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(minutes=minutes),
            created_by_user_id=created_by_user_id,
        )
        queue_entry.active_session = session
        queue_entry.save(update_fields=["active_session", "updated_at"])
        return token_plain


class PatientImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_file_name = models.CharField(max_length=255)
    source_file_sha256 = models.CharField(max_length=64)
    import_type = models.CharField(
        max_length=40,
        choices=ImportType.choices,
        default=ImportType.DAILY_FILE_IMPORT,
    )
    source_system = models.CharField(
        max_length=40,
        choices=ImportSourceSystem.choices,
        default=ImportSourceSystem.DOCTOLIB_EXPORT,
    )
    status = models.CharField(max_length=30, choices=ImportStatus.choices, default=ImportStatus.PROCESSING)
    total_rows = models.IntegerField(default=0)
    inserted_rows = models.IntegerField(default=0)
    error_rows = models.IntegerField(default=0)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="import_batches"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "patient_import_batch"
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["source_system", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_rows__gte=0)
                & Q(inserted_rows__gte=0)
                & Q(error_rows__gte=0),
                name="import_batch_non_negative_counts",
            )
        ]


class PatientImportError(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        PatientImportBatch, on_delete=models.CASCADE, related_name="errors"
    )
    row_number = models.IntegerField()
    error_code = models.CharField(max_length=50)
    error_message = models.TextField()
    raw_row = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "patient_import_error"
        constraints = [
            models.CheckConstraint(condition=Q(row_number__gt=0), name="import_error_row_positive")
        ]
