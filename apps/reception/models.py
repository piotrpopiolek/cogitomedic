from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.translation_service import db_gettext_lazy
from apps.medical.name_normalize import compute_incoming_pdf_name_keys
from django.db.models import F, Q
from django.utils import timezone


class QueueShift(models.TextChoices):
    FULL_DAY = "FULL_DAY", db_gettext_lazy(
        "administration.choice_queue_shift_full_day", "Full day"
    )
    MORNING = "MORNING", db_gettext_lazy(
        "administration.choice_queue_shift_morning", "Morning"
    )
    AFTERNOON = "AFTERNOON", db_gettext_lazy(
        "administration.choice_queue_shift_afternoon", "Afternoon"
    )
    EVENING = "EVENING", db_gettext_lazy(
        "administration.choice_queue_shift_evening", "Evening"
    )


class QueueSource(models.TextChoices):
    MANUAL = "MANUAL", db_gettext_lazy(
        "administration.choice_queue_source_manual", "Manual"
    )
    IMPORT = "IMPORT", db_gettext_lazy(
        "administration.choice_queue_source_import", "Import"
    )


class QueueStatus(models.TextChoices):
    OPEN = "OPEN", db_gettext_lazy("administration.choice_queue_status_open", "Open")
    CLOSED = "CLOSED", db_gettext_lazy(
        "administration.choice_queue_status_closed", "Closed"
    )


class QueueEntryStatus(models.TextChoices):
    WAITING = "WAITING", db_gettext_lazy(
        "administration.choice_queue_entry_status_waiting", "Waiting"
    )
    IN_PROGRESS = "IN_PROGRESS", db_gettext_lazy(
        "administration.choice_queue_entry_status_in_progress", "In progress"
    )
    PATIENT_COMPLETED = "PATIENT_COMPLETED", db_gettext_lazy(
        "administration.choice_queue_entry_status_patient_completed",
        "Patient completed",
    )
    DOCTOR_IN_PROGRESS = "DOCTOR_IN_PROGRESS", db_gettext_lazy(
        "administration.choice_queue_entry_status_doctor_in_progress",
        "Doctor in progress",
    )
    PAPER_INTAKE_COMPLETED = "PAPER_INTAKE_COMPLETED", db_gettext_lazy(
        "administration.choice_queue_entry_status_paper_intake_completed",
        "Paper intake completed",
    )
    CANCELLED = "CANCELLED", db_gettext_lazy(
        "administration.choice_queue_entry_status_cancelled", "Cancelled"
    )


class ImportType(models.TextChoices):
    DAILY_FILE_IMPORT = "DAILY_FILE_IMPORT", db_gettext_lazy(
        "administration.choice_import_type_daily_file_import",
        "Daily file import",
    )
    EMERGENCY_TEMPLATE_IMPORT = "EMERGENCY_TEMPLATE_IMPORT", db_gettext_lazy(
        "administration.choice_import_type_emergency_template_import",
        "Emergency template import",
    )


class ImportSourceSystem(models.TextChoices):
    DOCTOLIB_EXPORT = "DOCTOLIB_EXPORT", db_gettext_lazy(
        "administration.choice_import_source_doctolib_export",
        "Doctolib export",
    )
    OTHER = "OTHER", db_gettext_lazy(
        "administration.choice_import_source_other", "Other"
    )


class ImportStatus(models.TextChoices):
    PROCESSING = "PROCESSING", db_gettext_lazy(
        "administration.choice_import_status_processing", "Processing"
    )
    COMPLETED = "COMPLETED", db_gettext_lazy(
        "administration.choice_import_status_completed", "Completed"
    )
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS", db_gettext_lazy(
        "administration.choice_import_status_completed_with_errors",
        "Completed with errors",
    )
    FAILED = "FAILED", db_gettext_lazy(
        "administration.choice_import_status_failed", "Failed"
    )


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(
        max_length=100,
        verbose_name=db_gettext_lazy("administration.field_first_name", "First name"),
    )
    last_name = models.CharField(
        max_length=100,
        verbose_name=db_gettext_lazy("administration.field_last_name", "Last name"),
    )
    date_of_birth = models.DateField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_date_of_birth", "Date of birth"
        ),
    )
    phone = models.CharField(
        max_length=20,
        verbose_name=db_gettext_lazy("administration.field_phone", "Phone"),
    )
    email = models.EmailField(
        verbose_name=db_gettext_lazy("administration.field_email", "Email")
    )
    doctolib_patient_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        verbose_name=db_gettext_lazy(
            "administration.field_doctolib_patient_id", "Doctolib patient id"
        ),
    )
    street = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy("administration.field_street", "Street"),
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy("administration.field_city", "City"),
    )
    postal_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy("administration.field_postal_code", "Postal code"),
    )
    country_code = models.CharField(
        max_length=2,
        default="DE",
        verbose_name=db_gettext_lazy(
            "administration.field_country_code", "Country code"
        ),
    )
    clinic_sites = models.ManyToManyField(
        "reception.ClinicSite",
        db_table="patient_clinic_site",
        related_name="patients",
        blank=True,
        verbose_name=db_gettext_lazy(
            "administration.field_clinic_sites", "Clinic sites"
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_active", "Is active"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=db_gettext_lazy("administration.field_updated_at", "Updated at"),
    )
    anonymization_started_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_anonymization_started_at", "Anonymization started at"
        ),
    )
    anonymized_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_anonymized_at", "Anonymized at"
        ),
    )
    consent_summary = models.JSONField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_consent_summary", "Consent summary"
        ),
    )
    incoming_pdf_name_key_fl = models.CharField(
        max_length=300,
        default="",
        editable=False,
        verbose_name="Incoming PDF name key (first_last)",
    )
    incoming_pdf_name_key_lf = models.CharField(
        max_length=300,
        default="",
        editable=False,
        verbose_name="Incoming PDF name key (last_first)",
    )

    class Meta:
        db_table = "patient"
        verbose_name = db_gettext_lazy("administration.model_patient", "Patient")
        verbose_name_plural = db_gettext_lazy(
            "administration.model_patient_plural", "Patients"
        )
        indexes = [
            models.Index(fields=["last_name", "first_name", "date_of_birth"]),
            models.Index(fields=["phone"]),
            GinIndex(
                fields=["last_name"],
                name="patient_last_name_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
            GinIndex(
                fields=["first_name"],
                name="patient_first_name_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
            models.Index(
                fields=["incoming_pdf_name_key_fl"],
                name="patient_incpdf_key_fl_idx",
            ),
            models.Index(
                fields=["incoming_pdf_name_key_lf"],
                name="patient_incpdf_key_lf_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                name="patient_phone_unique",
            ),
            models.CheckConstraint(
                condition=Q(phone__regex=r"^[0-9]{7,20}$"),
                name="patient_phone_format",
            ),
        ]

    def save(self, *args, **kwargs):
        from apps.reception.phone_utils import normalize_phone_for_patient_storage

        norm = normalize_phone_for_patient_storage(self.phone)
        if norm:
            self.phone = norm
        fl, lf = compute_incoming_pdf_name_keys(self.first_name, self.last_name)
        self.incoming_pdf_name_key_fl = fl[:300]
        self.incoming_pdf_name_key_lf = lf[:300]
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = list(update_fields)
            for key in ("incoming_pdf_name_key_fl", "incoming_pdf_name_key_lf"):
                if key not in update_fields:
                    update_fields.append(key)
            kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        dob = self.date_of_birth.isoformat() if self.date_of_birth else "—"
        return f"{self.last_name} {self.first_name} ({dob})"


class ClinicSite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=db_gettext_lazy("administration.field_code", "Code"),
    )
    name = models.CharField(
        max_length=120,
        verbose_name=db_gettext_lazy("administration.field_name", "Name"),
    )
    pdf_import_default_consulting_room = models.ForeignKey(
        "reception.ConsultingRoom",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        verbose_name=db_gettext_lazy(
            "administration.field_pdf_import_default_consulting_room",
            "PDF import default consulting room",
        ),
    )
    pdf_import_shift_code = models.CharField(
        max_length=20,
        choices=QueueShift.choices,
        default=QueueShift.FULL_DAY,
        verbose_name=db_gettext_lazy(
            "administration.field_pdf_import_shift_code",
            "PDF import shift code",
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_active", "Is active"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )

    class Meta:
        db_table = "clinic_site"
        verbose_name = db_gettext_lazy("administration.model_clinicsite", "Clinic site")
        verbose_name_plural = db_gettext_lazy(
            "administration.model_clinicsite_plural", "Clinic sites"
        )

    def __str__(self) -> str:
        return self.name or self.code or str(self.id)


class ConsultingRoom(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinic_site = models.ForeignKey(
        ClinicSite,
        on_delete=models.RESTRICT,
        related_name="rooms",
        verbose_name=db_gettext_lazy("administration.field_clinicsite", "Clinic site"),
    )
    code = models.CharField(
        max_length=20, verbose_name=db_gettext_lazy("administration.field_code", "Code")
    )
    name = models.CharField(
        max_length=120,
        verbose_name=db_gettext_lazy("administration.field_name", "Name"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_active", "Is active"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )

    class Meta:
        db_table = "consulting_room"
        verbose_name = db_gettext_lazy(
            "administration.model_consultingroom", "Consulting room"
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_consultingroom_plural", "Consulting rooms"
        )
        constraints = [
            models.UniqueConstraint(
                fields=["clinic_site", "code"],
                name="consulting_room_site_code_unique",
            )
        ]

    def __str__(self) -> str:
        return self.name or self.code or str(self.id)


class DailyQueue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    queue_date = models.DateField(
        verbose_name=db_gettext_lazy("administration.field_queue_date", "Queue date")
    )
    clinic_site = models.ForeignKey(
        ClinicSite,
        on_delete=models.RESTRICT,
        related_name="daily_queues",
        verbose_name=db_gettext_lazy("administration.field_clinic_site", "Clinic site"),
    )
    consulting_room = models.ForeignKey(
        ConsultingRoom,
        on_delete=models.RESTRICT,
        related_name="daily_queues",
        verbose_name=db_gettext_lazy(
            "administration.field_consulting_room", "Consulting room"
        ),
    )
    shift_code = models.CharField(
        max_length=20,
        choices=QueueShift.choices,
        default=QueueShift.FULL_DAY,
        verbose_name=db_gettext_lazy("administration.field_shift_code", "Shift code"),
    )
    source = models.CharField(
        max_length=20,
        choices=QueueSource.choices,
        default=QueueSource.MANUAL,
        verbose_name=db_gettext_lazy("administration.field_source", "Source"),
    )
    status = models.CharField(
        max_length=20,
        choices=QueueStatus.choices,
        default=QueueStatus.OPEN,
        verbose_name=db_gettext_lazy("administration.field_status", "Status"),
    )
    assigned_doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="assigned_queues",
        limit_choices_to=Q(groups__name="Doctor"),
        verbose_name=db_gettext_lazy(
            "administration.field_assigned_doctor", "Assigned doctor"
        ),
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_queues",
        verbose_name=db_gettext_lazy(
            "administration.field_created_by_user", "Created by"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=db_gettext_lazy("administration.field_updated_at", "Updated at"),
    )

    class Meta:
        db_table = "daily_queue"
        verbose_name = db_gettext_lazy("administration.model_dailyqueue", "Daily queue")
        verbose_name_plural = db_gettext_lazy(
            "administration.model_dailyqueue_plural", "Daily queues"
        )
        indexes = [
            models.Index(fields=["queue_date"]),
            models.Index(fields=["assigned_doctor", "queue_date", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["queue_date", "clinic_site", "consulting_room", "shift_code"],
                name="daily_queue_unique_slot",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if not self.clinic_site_id or not self.consulting_room_id:
            return
        room_site_id = (
            ConsultingRoom.objects.filter(pk=self.consulting_room_id)
            .values_list("clinic_site_id", flat=True)
            .first()
        )
        if room_site_id is None:
            raise ValidationError(
                {
                    "consulting_room": db_gettext_lazy(
                        "administration.error_daily_queue_consulting_room_not_found",
                        "The selected consulting room does not exist.",
                    )
                }
            )
        if room_site_id != self.clinic_site_id:
            raise ValidationError(
                {
                    "consulting_room": db_gettext_lazy(
                        "administration.error_daily_queue_consulting_room_site_mismatch",
                        "Consulting room must belong to the selected clinic site.",
                    ),
                }
            )

    def __str__(self) -> str:
        room = str(self.consulting_room) if self.consulting_room_id else "?"
        return f"{self.queue_date} – {self.clinic_site} / {room} ({self.get_shift_code_display()})"


class QueueEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daily_queue = models.ForeignKey(
        DailyQueue,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name=db_gettext_lazy("administration.field_daily_queue", "Daily queue"),
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.RESTRICT,
        related_name="queue_entries",
        verbose_name=db_gettext_lazy("administration.field_patient", "Patient"),
    )
    active_session = models.ForeignKey(
        "PatientFormSession",
        on_delete=models.RESTRICT,
        blank=True,
        null=True,
        related_name="+",
        verbose_name=db_gettext_lazy(
            "administration.field_active_session", "Active session"
        ),
    )
    entry_status = models.CharField(
        max_length=30,
        choices=QueueEntryStatus.choices,
        default=QueueEntryStatus.WAITING,
        verbose_name=db_gettext_lazy(
            "administration.field_entry_status", "Entry status"
        ),
    )
    position_no = models.IntegerField(
        verbose_name=db_gettext_lazy("administration.field_position_no", "Position no")
    )
    visit_external_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_visit_external_id", "Visit external id"
        ),
    )
    appointment_time = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_appointment_time", "Appointment time"
        ),
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy("administration.field_notes", "Notes"),
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_queue_entries",
        verbose_name=db_gettext_lazy(
            "administration.field_created_by_user", "Created by"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=db_gettext_lazy("administration.field_updated_at", "Updated at"),
    )
    doctor_list_sort_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_queue_entry_doctor_list_sort_at",
            "Doctor list sort time",
        ),
    )

    class Meta:
        db_table = "queue_entry"
        verbose_name = db_gettext_lazy("administration.model_queueentry", "Queue entry")
        verbose_name_plural = db_gettext_lazy(
            "administration.model_queueentry_plural", "Queue entries"
        )
        indexes = [
            models.Index(fields=["daily_queue", "entry_status", "position_no"]),
            models.Index(fields=["patient", "-created_at"]),
            models.Index(fields=["active_session"]),
            models.Index(
                fields=["daily_queue", "position_no"],
                name="qentry_active_pos_idx",
                condition=Q(
                    entry_status__in=[
                        QueueEntryStatus.WAITING,
                        QueueEntryStatus.IN_PROGRESS,
                    ]
                ),
            ),
            models.Index(
                fields=["-doctor_list_sort_at"],
                name="qentry_doctor_sort_idx",
                condition=Q(doctor_list_sort_at__isnull=False),
            ),
            models.Index(
                fields=["entry_status", "-doctor_list_sort_at", "-id"],
                name="qentry_doc_queue_perf_idx",
                condition=Q(
                    doctor_list_sort_at__isnull=False,
                    entry_status__in=[
                        QueueEntryStatus.WAITING,
                        QueueEntryStatus.PATIENT_COMPLETED,
                        QueueEntryStatus.PAPER_INTAKE_COMPLETED,
                    ],
                ),
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

    def __str__(self) -> str:
        return f"{self.patient} – poz. {self.position_no} ({self.get_entry_status_display()})"


class TabletDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    android_id = models.CharField(
        max_length=128,
        unique=True,
        verbose_name=db_gettext_lazy("administration.field_android_id", "Android id"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_active", "Is active"),
    )
    last_seen_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_last_seen_at", "Last seen at"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )
    clinic_site = models.ForeignKey(
        ClinicSite,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="tablet_devices",
        verbose_name=db_gettext_lazy("administration.field_clinic_site", "Clinic site"),
    )

    class Meta:
        db_table = "tablet_device"
        verbose_name = db_gettext_lazy(
            "administration.model_tabletdevice", "Tablet device"
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_tabletdevice_plural", "Tablet devices"
        )

    def __str__(self) -> str:
        return (
            f"Tablet {self.android_id[:16]}…"
            if len(self.android_id or "") > 16
            else f"Tablet {self.android_id or '?'}"
        )


class PatientFormSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    queue_entry = models.ForeignKey(
        QueueEntry,
        on_delete=models.CASCADE,
        related_name="form_sessions",
        verbose_name=db_gettext_lazy("administration.field_queue_entry", "Queue entry"),
    )
    tablet_device = models.ForeignKey(
        TabletDevice,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sessions",
        verbose_name=db_gettext_lazy(
            "administration.field_tablet_device", "Tablet device"
        ),
    )
    form_locale = models.CharField(
        max_length=10,
        default="de-DE",
        verbose_name=db_gettext_lazy("administration.field_form_locale", "Form locale"),
    )
    expires_at = models.DateTimeField(
        verbose_name=db_gettext_lazy("administration.field_expires_at", "Expires at")
    )
    consumed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy("administration.field_consumed_at", "Consumed at"),
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_form_sessions",
        verbose_name=db_gettext_lazy(
            "administration.field_created_by_user", "Created by"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )

    class Meta:
        db_table = "patient_form_session"
        verbose_name = db_gettext_lazy(
            "administration.model_patientformsession",
            "Patient form session",
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_patientformsession_plural",
            "Patient form sessions",
        )
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
                condition=Q(form_locale__regex=r"^(de|en|pl)(-[A-Z]{2})?$"),
                name="session_locale_format",
            ),
            models.CheckConstraint(
                condition=Q(consumed_at__isnull=True)
                | Q(consumed_at__lte=F("expires_at")),
                name="session_consumed_before_expiry",
            ),
        ]

    def __str__(self) -> str:
        return f"Sesja formularza: {self.queue_entry} ({self.created_at.strftime('%d.%m.%Y')})"

    @classmethod
    def create_session(
        cls,
        queue_entry: QueueEntry,
        created_by_user_id: uuid.UUID,
        minutes: int = 120,
        tablet_device_id: uuid.UUID | None = None,
        form_locale: str = "de-DE",
    ) -> PatientFormSession:
        """Create a form session (no token). Latest-wins: caller must set queue_entry.active_session."""
        session = cls.objects.create(
            queue_entry=queue_entry,
            tablet_device_id=tablet_device_id,
            form_locale=form_locale,
            expires_at=timezone.now() + timedelta(minutes=minutes),
            created_by_user_id=created_by_user_id,
        )
        return session


class PatientImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_file_name = models.CharField(
        max_length=255,
        verbose_name=db_gettext_lazy(
            "administration.field_source_file_name", "Source file name"
        ),
    )
    source_file_sha256 = models.CharField(
        max_length=64,
        verbose_name=db_gettext_lazy(
            "administration.field_source_file_sha256", "Source file sha256"
        ),
    )
    import_type = models.CharField(
        max_length=40,
        choices=ImportType.choices,
        default=ImportType.DAILY_FILE_IMPORT,
        verbose_name=db_gettext_lazy("administration.field_import_type", "Import type"),
    )
    source_system = models.CharField(
        max_length=40,
        choices=ImportSourceSystem.choices,
        default=ImportSourceSystem.DOCTOLIB_EXPORT,
        verbose_name=db_gettext_lazy(
            "administration.field_source_system", "Source system"
        ),
    )
    status = models.CharField(
        max_length=30,
        choices=ImportStatus.choices,
        default=ImportStatus.PROCESSING,
        verbose_name=db_gettext_lazy("administration.field_status", "Status"),
    )
    total_rows = models.IntegerField(
        default=0,
        verbose_name=db_gettext_lazy("administration.field_total_rows", "Total rows"),
    )
    inserted_rows = models.IntegerField(
        default=0,
        verbose_name=db_gettext_lazy(
            "administration.field_inserted_rows", "Inserted rows"
        ),
    )
    matched_rows = models.IntegerField(
        default=0,
        verbose_name=db_gettext_lazy(
            "administration.field_matched_rows", "Matched rows"
        ),
    )
    skipped_already_present_count = models.IntegerField(
        default=0,
        verbose_name=db_gettext_lazy(
            "administration.field_skipped_already_present_count",
            "Skipped already present rows",
        ),
    )
    error_rows = models.IntegerField(
        default=0,
        verbose_name=db_gettext_lazy("administration.field_error_rows", "Error rows"),
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="import_batches",
        verbose_name=db_gettext_lazy(
            "administration.field_created_by_user", "Created by"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )
    finished_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy("administration.field_finished_at", "Finished at"),
    )

    class Meta:
        db_table = "patient_import_batch"
        verbose_name = db_gettext_lazy(
            "administration.model_patientimportbatch",
            "Patient import batch",
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_patientimportbatch_plural",
            "Patient import batches",
        )
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["source_system", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_rows__gte=0)
                & Q(inserted_rows__gte=0)
                & Q(matched_rows__gte=0)
                & Q(skipped_already_present_count__gte=0)
                & Q(error_rows__gte=0),
                name="import_batch_non_negative_counts",
            )
        ]

    def __str__(self) -> str:
        return f"Import: {self.source_file_name} ({self.created_at.strftime('%d.%m.%Y')}, {self.get_status_display()})"


class PatientImportError(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        PatientImportBatch,
        on_delete=models.CASCADE,
        related_name="errors",
        verbose_name=db_gettext_lazy(
            "administration.field_import_batch", "Import batch"
        ),
    )
    row_number = models.IntegerField(
        verbose_name=db_gettext_lazy("administration.field_row_number", "Row number")
    )
    error_code = models.CharField(
        max_length=50,
        verbose_name=db_gettext_lazy("administration.field_error_code", "Error code"),
    )
    error_message = models.TextField(
        verbose_name=db_gettext_lazy(
            "administration.field_error_message", "Error message"
        )
    )
    raw_row = models.JSONField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy("administration.field_raw_row", "Raw row"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )

    class Meta:
        db_table = "patient_import_error"
        verbose_name = db_gettext_lazy(
            "administration.model_patientimporterror",
            "Patient import error",
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_patientimporterror_plural",
            "Patient import errors",
        )
        constraints = [
            models.CheckConstraint(
                condition=Q(row_number__gt=0), name="import_error_row_positive"
            )
        ]

    def __str__(self) -> str:
        msg = (self.error_message or "")[:50]
        if len(self.error_message or "") > 50:
            msg += "…"
        return f"Wiersz {self.row_number}: {self.error_code}" + (
            f" – {msg}" if msg else ""
        )
