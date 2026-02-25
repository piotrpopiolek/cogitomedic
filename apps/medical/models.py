from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q
from django.contrib.postgres.indexes import GinIndex


class MedicalDocStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PUBLISHED = "PUBLISHED", "Published"


class DocVersionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PUBLISHED = "PUBLISHED", "Published"


class PdfStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class MedicalDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    queue_entry = models.OneToOneField(
        "reception.QueueEntry",
        on_delete=models.RESTRICT,
        related_name="medical_document",
    )
    intake_form = models.OneToOneField(
        "intake.PatientIntakeForm",
        on_delete=models.RESTRICT,
        related_name="medical_document",
    )
    status = models.CharField(max_length=20, choices=MedicalDocStatus.choices, default=MedicalDocStatus.DRAFT)
    current_version_no = models.IntegerField(default=0)
    last_published_at = models.DateTimeField(blank=True, null=True)
    created_by_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.RESTRICT,
        related_name="created_medical_documents",
    )
    updated_by_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="updated_medical_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "medical_document"
        constraints = [
            models.CheckConstraint(
                condition=Q(current_version_no__gte=0),
                name="medical_document_current_version_non_negative",
            )
        ]
        indexes = [
            models.Index(fields=["status", "-updated_at"]),
        ]


class MedicalDocumentVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_document = models.ForeignKey(
        MedicalDocument,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_no = models.IntegerField()
    version_status = models.CharField(
        max_length=20,
        choices=DocVersionStatus.choices,
        default=DocVersionStatus.DRAFT,
    )
    publish_request_id = models.UUIDField(blank=True, null=True)
    pdf_generation_status = models.CharField(
        max_length=20,
        choices=PdfStatus.choices,
        default=PdfStatus.PENDING,
    )
    medical_payload_schema_version = models.SmallIntegerField(default=1)
    medical_payload = models.JSONField(default=dict)
    diagnosis_code = models.CharField(max_length=50, blank=True, null=True)
    procedure_code = models.CharField(max_length=50, blank=True, null=True)
    pdf_local_path = models.CharField(max_length=500, blank=True, null=True)
    pdf_checksum_sha256 = models.CharField(max_length=64, blank=True, null=True)
    hidrive_path = models.CharField(max_length=500, blank=True, null=True)
    hidrive_sent = models.BooleanField(default=False)
    hidrive_sent_at = models.DateTimeField(blank=True, null=True)
    sms_sent = models.BooleanField(default=False)
    sms_sent_at = models.DateTimeField(blank=True, null=True)
    local_pdf_deleted_at = models.DateTimeField(blank=True, null=True)
    publish_requested_by_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="requested_medical_publications",
    )
    published_by_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="published_medical_documents",
    )
    published_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "medical_document_version"
        constraints = [
            models.UniqueConstraint(
                fields=["medical_document", "version_no"],
                name="medical_document_version_unique",
            ),
            models.UniqueConstraint(
                fields=["medical_document", "publish_request_id"],
                name="medical_document_publish_request_unique",
            ),
            models.CheckConstraint(condition=Q(version_no__gt=0), name="medical_document_version_positive"),
            models.CheckConstraint(
                condition=Q(version_status=DocVersionStatus.DRAFT) | Q(publish_request_id__isnull=False),
                name="medical_document_published_requires_request_id",
            ),
            models.CheckConstraint(
                condition=Q(version_status=DocVersionStatus.DRAFT) | Q(published_at__isnull=False),
                name="medical_document_published_requires_time",
            ),
            models.CheckConstraint(
                condition=Q(pdf_generation_status=PdfStatus.COMPLETED, pdf_local_path__isnull=False)
                | ~Q(pdf_generation_status=PdfStatus.COMPLETED),
                name="medical_document_pdf_completed_requires_path",
            ),
            models.CheckConstraint(
                condition=Q(hidrive_sent=False)
                | (Q(hidrive_sent=True) & Q(hidrive_sent_at__isnull=False)),
                name="medical_document_hidrive_sent_requires_time",
            ),
            models.CheckConstraint(
                condition=Q(sms_sent=False) | (Q(sms_sent=True) & Q(sms_sent_at__isnull=False)),
                name="medical_document_sms_sent_requires_time",
            ),
            models.CheckConstraint(
                condition=Q(local_pdf_deleted_at__isnull=True)
                | (Q(hidrive_sent=True) & Q(sms_sent=True)),
                name="medical_document_local_pdf_deletion_guard",
            ),
        ]
        indexes = [
            models.Index(fields=["medical_document", "-version_no"]),
            models.Index(fields=["version_status", "-published_at"]),
            models.Index(fields=["hidrive_sent", "sms_sent", "published_at"]),
            models.Index(
                fields=["published_at"],
                name="medical_document_retention_idx",
                condition=Q(
                    version_status=DocVersionStatus.PUBLISHED,
                    hidrive_sent=True,
                    sms_sent=True,
                    local_pdf_deleted_at__isnull=True,
                ),
            ),
            GinIndex(
                fields=["medical_payload"],
                name="medical_payload_gin_idx",
                opclasses=["jsonb_path_ops"],
            ),
        ]


class DoctorTextTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="doctor_templates",
    )
    name = models.CharField(max_length=120)
    template_locale = models.CharField(max_length=10, default="de-DE")
    template_body = models.TextField()
    lesion_group_favorites = models.JSONField(default=list, blank=True)
    summary_favorites = models.JSONField(default=list, blank=True)
    is_global = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "doctor_text_template"
        constraints = [
            models.CheckConstraint(
                condition=Q(template_locale__regex=r"^(de|en|pl)(-[A-Z]{2})?$"),
                name="doctor_template_locale_format",
            ),
            models.CheckConstraint(
                condition=(Q(is_global=True) & Q(owner_user__isnull=True))
                | (Q(is_global=False) & Q(owner_user__isnull=False)),
                name="doctor_template_global_owner_consistency",
            ),
            models.UniqueConstraint(
                fields=["owner_user", "name", "template_locale"],
                name="doctor_template_owner_name_locale_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["owner_user", "template_locale", "is_active"]),
            models.Index(fields=["is_global", "template_locale", "is_active"]),
        ]
