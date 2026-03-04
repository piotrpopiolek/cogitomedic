from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.contrib.postgres.indexes import GinIndex

from apps.core.translation_service import db_gettext_lazy


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
    status = models.CharField(max_length=20, choices=MedicalDocStatus.choices, default=MedicalDocStatus.DRAFT, verbose_name=db_gettext_lazy("administration.field_status", "Status"))
    current_version_no = models.IntegerField(default=0, verbose_name=db_gettext_lazy("administration.field_current_version_no", "Current version no"))
    last_published_at = models.DateTimeField(blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_last_published_at", "Last published at"))
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
        verbose_name = db_gettext_lazy("administration.model_medicaldocument", "Medical document")
        verbose_name_plural = db_gettext_lazy("administration.model_medicaldocument_plural", "Medical documents")
        constraints = [
            models.CheckConstraint(
                condition=Q(current_version_no__gte=0),
                name="medical_document_current_version_non_negative",
            )
        ]
        indexes = [
            models.Index(fields=["status", "-updated_at"]),
            models.Index(fields=["created_by_user", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Dokument medyczny: {self.queue_entry.patient} ({self.get_status_display()})"


class MedicalDocumentVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_document = models.ForeignKey(
        MedicalDocument,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_no = models.IntegerField(verbose_name=db_gettext_lazy("administration.field_version_no", "Version no"))
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
    medical_payload_schema_version = models.SmallIntegerField(default=1, verbose_name=db_gettext_lazy("administration.field_medical_payload_schema_version", "Medical payload schema version"))
    medical_payload = models.JSONField(default=dict, verbose_name=db_gettext_lazy("administration.field_medical_payload", "Medical payload"))
    diagnosis_code = models.CharField(max_length=50, blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_diagnosis_code", "Diagnosis code"))
    procedure_code = models.CharField(max_length=50, blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_procedure_code", "Procedure code"))
    pdf_local_path = models.CharField(max_length=500, blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_pdf_local_path", "Pdf local path"))
    pdf_checksum_sha256 = models.CharField(max_length=64, blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_pdf_checksum_sha256", "Pdf checksum sha256"))
    hidrive_path = models.CharField(max_length=500, blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_hidrive_path", "Hidrive path"))
    hidrive_sent = models.BooleanField(default=False, verbose_name=db_gettext_lazy("administration.field_hidrive_sent", "Hidrive sent"))
    hidrive_sent_at = models.DateTimeField(blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_hidrive_sent_at", "Hidrive sent at"))
    sms_sent = models.BooleanField(default=False, verbose_name=db_gettext_lazy("administration.field_sms_sent", "Sms sent"))
    sms_sent_at = models.DateTimeField(blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_sms_sent_at", "Sms sent at"))
    local_pdf_deleted_at = models.DateTimeField(blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_local_pdf_deleted_at", "Local pdf deleted at"))
    publish_requested_by_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="requested_medical_publications",
    )
    publish_locale = models.CharField(max_length=10, blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_publish_locale", "Publish locale"))
    published_by_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="published_medical_documents",
    )
    published_at = models.DateTimeField(blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_published_at", "Published at"))
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
                condition=Q(version_status=DocVersionStatus.DRAFT) | Q(publish_locale__isnull=False),
                name="medical_document_published_requires_publish_locale",
            ),
            models.CheckConstraint(
                condition=Q(publish_locale__isnull=True)
                | Q(publish_locale__regex=r"^(de|en|pl)(-[A-Z]{2})?$"),
                name="medical_document_publish_locale_format",
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

    def __str__(self) -> str:
        return f"Wersja {self.version_no} – {self.medical_document} ({self.get_version_status_display()})"


class DoctorTextTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="doctor_templates",
    )
    clinic_site = models.ForeignKey(
        "reception.ClinicSite",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="doctor_templates",
    )
    name = models.CharField(max_length=120, verbose_name=db_gettext_lazy("administration.field_name", "Name"))
    template_locale = models.CharField(max_length=10, default="de-DE", verbose_name=db_gettext_lazy("administration.field_template_locale", "Template locale"))
    template_body = models.TextField(verbose_name=db_gettext_lazy("administration.field_template_body", "Template body"))
    lesion_group_favorites = models.JSONField(default=list, blank=True, verbose_name=db_gettext_lazy("administration.field_lesion_group_favorites", "Lesion group favorites"))
    summary_favorites = models.JSONField(default=list, blank=True, verbose_name=db_gettext_lazy("administration.field_summary_favorites", "Summary favorites"))
    is_global = models.BooleanField(default=False, verbose_name=db_gettext_lazy("administration.field_is_global", "Is global"))
    is_active = models.BooleanField(default=True, verbose_name=db_gettext_lazy("administration.field_is_active", "Is active"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        # Normalize global templates to satisfy constraint and avoid admin UX pitfalls.
        if self.is_global:
            self.owner_user = None
            return
        if self.owner_user_id is None and self.clinic_site_id is None:
            raise ValidationError("Private or clinic template requires owner_user or clinic_site.")
        if self.owner_user_id is not None and self.clinic_site_id is not None:
            raise ValidationError("Template cannot have both owner_user and clinic_site.")

    class Meta:
        db_table = "doctor_text_template"
        verbose_name = db_gettext_lazy("administration.model_doctortexttemplate", "Doctor template")
        verbose_name_plural = db_gettext_lazy("administration.model_doctortexttemplate_plural", "Doctor templates")
        constraints = [
            models.CheckConstraint(
                condition=Q(template_locale__regex=r"^(de|en|pl)(-[A-Z]{2})?$"),
                name="doctor_template_locale_format",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(is_global=True) & Q(owner_user__isnull=True)) |
                    (Q(is_global=False) & (
                        (Q(owner_user__isnull=False) & Q(clinic_site__isnull=True)) |
                        (Q(owner_user__isnull=True) & Q(clinic_site__isnull=False))
                    ))
                ),
                name="doctor_template_global_owner_consistency",
            ),
            models.UniqueConstraint(
                fields=["owner_user", "name", "template_locale"],
                name="doctor_template_owner_name_locale_unique",
            ),
            models.UniqueConstraint(
                fields=["clinic_site", "name", "template_locale"],
                name="doctor_template_clinic_name_locale_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["owner_user", "template_locale", "is_active"]),
            models.Index(fields=["clinic_site", "template_locale", "is_active"]),
            models.Index(fields=["is_global", "template_locale", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name
