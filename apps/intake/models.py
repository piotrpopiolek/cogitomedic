from __future__ import annotations

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Q


class IntakeStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    SUBMITTED = "SUBMITTED", "Submitted"


class IntakePdfStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class IntakeOutboxEventType(models.TextChoices):
    GENERATE_INTAKE_PDF = "GENERATE_INTAKE_PDF", "Generate intake PDF"
    HIDRIVE_UPLOAD_INTAKE_PDF = "HIDRIVE_UPLOAD_INTAKE_PDF", "HiDrive upload intake PDF"


class IntakeOutboxStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    PROCESSED = "PROCESSED", "Processed"
    FAILED = "FAILED", "Failed"
    DEAD_LETTER = "DEAD_LETTER", "Dead letter"


class ConsentDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=60)
    version = models.IntegerField()
    title_de = models.CharField(max_length=200)
    title_en = models.CharField(max_length=200, blank=True, default="")
    title_pl = models.CharField(max_length=200, blank=True, default="")
    content_de = models.TextField()
    content_en = models.TextField(blank=True, default="")
    content_pl = models.TextField(blank=True, default="")
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    display_order = models.SmallIntegerField(default=0)
    effective_from = models.DateField(auto_now_add=True)
    effective_to = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "consent_definition"
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="consent_definition_unique"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=F("effective_from")),
                name="consent_effective_to_after_from",
            ),
        ]
        indexes = [
            models.Index(fields=["code", "is_active", "-effective_from"]),
        ]


class AnamnesisQuestionDefinition(models.Model):
    class AnswerType(models.TextChoices):
        SINGLE_CHOICE = "SINGLE_CHOICE", "Single choice"
        MULTI_CHOICE = "MULTI_CHOICE", "Multi choice"
        BOOLEAN = "BOOLEAN", "Boolean"
        TEXT_OPTIONAL = "TEXT_OPTIONAL", "Text optional"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=80)
    version = models.IntegerField(default=1)
    question_text_de = models.TextField()
    question_text_en = models.TextField()
    question_text_pl = models.TextField(blank=True, default="")
    answer_type = models.CharField(
        max_length=30,
        choices=AnswerType.choices,
        default=AnswerType.SINGLE_CHOICE,
    )
    is_required = models.BooleanField(default=True)
    display_order = models.SmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(auto_now_add=True)
    effective_to = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "anamnesis_question_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["code", "version"],
                name="anamnesis_question_definition_unique",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=F("effective_from")),
                name="anamnesis_question_effective_to_after_from",
            ),
        ]
        indexes = [
            models.Index(fields=["code", "is_active", "-effective_from"]),
        ]


class AnamnesisOptionDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        AnamnesisQuestionDefinition,
        on_delete=models.CASCADE,
        related_name="options",
    )
    code = models.CharField(max_length=80)
    option_text_de = models.TextField()
    option_text_en = models.TextField()
    option_text_pl = models.TextField(blank=True, default="")
    display_order = models.SmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "anamnesis_option_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["question", "code"],
                name="anamnesis_option_definition_unique",
            )
        ]
        indexes = [
            models.Index(fields=["question", "is_active", "display_order"]),
        ]


class PatientIntakeForm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    queue_entry = models.OneToOneField(
        "reception.QueueEntry",
        on_delete=models.CASCADE,
        related_name="intake_form",
    )
    session = models.OneToOneField(
        "reception.PatientFormSession",
        on_delete=models.RESTRICT,
        related_name="intake_form",
    )
    form_status = models.CharField(
        max_length=20,
        choices=IntakeStatus.choices,
        default=IntakeStatus.IN_PROGRESS,
    )
    body_map_schema_version = models.SmallIntegerField(default=1)
    body_map_data = models.JSONField(default=list)
    anamnesis_schema_version = models.SmallIntegerField(default=1)
    anamnesis_payload = models.JSONField(default=dict)
    signature_file_path = models.CharField(max_length=500, blank=True, null=True)
    signature_sha256 = models.CharField(max_length=64, blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "patient_intake_form"
        indexes = [
            models.Index(fields=["form_status", "submitted_at"]),
            GinIndex(
                fields=["body_map_data"],
                name="intake_body_map_gin_idx",
                opclasses=["jsonb_path_ops"],
            ),
            GinIndex(
                fields=["anamnesis_payload"],
                name="intake_anamnesis_gin_idx",
                opclasses=["jsonb_path_ops"],
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(form_status=IntakeStatus.IN_PROGRESS)
                | (
                    Q(submitted_at__isnull=False)
                    & Q(signature_file_path__isnull=False)
                ),
                name="intake_submitted_requires_signature",
            ),
        ]


class PatientIntakeConsent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intake_form = models.ForeignKey(
        PatientIntakeForm,
        on_delete=models.CASCADE,
        related_name="consents",
    )
    consent_definition = models.ForeignKey(
        ConsentDefinition,
        on_delete=models.RESTRICT,
        related_name="intake_consents",
    )
    accepted = models.BooleanField()
    accepted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "patient_intake_consent"
        constraints = [
            models.UniqueConstraint(
                fields=["intake_form", "consent_definition"],
                name="intake_consent_unique",
            ),
            models.CheckConstraint(
                condition=(Q(accepted=True) & Q(accepted_at__isnull=False))
                | (Q(accepted=False) & Q(accepted_at__isnull=True)),
                name="intake_consent_accepted_time",
            ),
        ]
        indexes = [
            models.Index(fields=["intake_form", "accepted"]),
        ]


class IntakeDocumentVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intake_form = models.ForeignKey(
        PatientIntakeForm,
        on_delete=models.CASCADE,
        related_name="document_versions",
    )
    version_no = models.IntegerField()
    form_locale = models.CharField(max_length=10)
    snapshot_payload = models.JSONField(default=dict)
    pdf_generation_status = models.CharField(
        max_length=20,
        choices=IntakePdfStatus.choices,
        default=IntakePdfStatus.PENDING,
    )
    pdf_local_path = models.CharField(max_length=500, blank=True, null=True)
    pdf_checksum_sha256 = models.CharField(max_length=64, blank=True, null=True)
    hidrive_path = models.CharField(max_length=500, blank=True, null=True)
    hidrive_sent = models.BooleanField(default=False)
    hidrive_sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "intake_document_version"
        constraints = [
            models.UniqueConstraint(
                fields=["intake_form", "version_no"],
                name="intake_document_version_unique",
            ),
            models.CheckConstraint(
                condition=Q(version_no__gt=0),
                name="intake_document_version_positive",
            ),
            models.CheckConstraint(
                condition=Q(form_locale__regex=r"^(de|en|pl)(-[A-Z]{2})?$"),
                name="intake_document_locale_format",
            ),
            models.CheckConstraint(
                condition=Q(pdf_generation_status=IntakePdfStatus.COMPLETED, pdf_local_path__isnull=False)
                | ~Q(pdf_generation_status=IntakePdfStatus.COMPLETED),
                name="intake_document_pdf_completed_requires_path",
            ),
            models.CheckConstraint(
                condition=Q(hidrive_sent=False)
                | (Q(hidrive_sent=True) & Q(hidrive_sent_at__isnull=False)),
                name="intake_document_hidrive_sent_requires_time",
            ),
        ]
        indexes = [
            models.Index(fields=["intake_form", "-version_no"]),
            models.Index(fields=["pdf_generation_status", "-created_at"]),
            models.Index(fields=["hidrive_sent", "-created_at"]),
            GinIndex(
                fields=["snapshot_payload"],
                name="intake_snap_gin_idx",
                opclasses=["jsonb_path_ops"],
            ),
        ]


class IntakeOutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intake_document_version = models.ForeignKey(
        IntakeDocumentVersion,
        on_delete=models.CASCADE,
        related_name="outbox_events",
    )
    aggregate_type = models.CharField(max_length=50, default="INTAKE_DOCUMENT_VERSION")
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=40, choices=IntakeOutboxEventType.choices)
    payload_schema_version = models.SmallIntegerField(default=1)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=IntakeOutboxStatus.choices,
        default=IntakeOutboxStatus.PENDING,
    )
    retry_count = models.SmallIntegerField(default=0)
    max_retries = models.SmallIntegerField(default=10)
    available_at = models.DateTimeField(auto_now_add=True)
    locked_at = models.DateTimeField(blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "intake_outbox_event"
        constraints = [
            models.UniqueConstraint(
                fields=["intake_document_version", "event_type"],
                name="intake_outbox_event_unique_per_type",
            ),
            models.CheckConstraint(
                condition=Q(retry_count__gte=0)
                & Q(max_retries__gt=0)
                & Q(retry_count__lte=F("max_retries")),
                name="intake_outbox_event_retry_bounds",
            ),
            models.CheckConstraint(
                condition=Q(aggregate_type="INTAKE_DOCUMENT_VERSION"),
                name="intake_outbox_event_aggregate_type_guard",
            ),
            models.CheckConstraint(
                condition=Q(aggregate_id=F("intake_document_version_id")),
                name="intake_outbox_event_aggregate_id_guard",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "available_at"]),
            models.Index(fields=["event_type", "status", "retry_count", "available_at", "payload_schema_version"]),
            models.Index(fields=["intake_document_version", "-created_at"]),
            models.Index(
                fields=["status", "available_at"],
                name="intake_outbox_pend_fail_idx",
                condition=Q(status__in=[IntakeOutboxStatus.PENDING, IntakeOutboxStatus.FAILED]),
            ),
            models.Index(
                fields=["available_at", "created_at"],
                name="intake_outbox_pf_order_idx",
                condition=Q(status__in=[IntakeOutboxStatus.PENDING, IntakeOutboxStatus.FAILED]),
            ),
            GinIndex(
                fields=["payload"],
                name="intake_outbox_payload_gin_idx",
                opclasses=["jsonb_path_ops"],
            ),
        ]
