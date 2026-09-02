from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.db.models import F, Q

from apps.core.translation_service import db_gettext_lazy, format_administration_message
from apps.intake.constants import (
    TELEDERM_PAYLOAD_SCHEMA_VERSION,
    default_telederm_payload,
)
from apps.outbox.constants import outbox_max_retries_default
from apps.reception.process_types import (
    ANAMNESIS_QUESTION_PROCESS_TYPE_ALLOWED,
    CONSENT_DEFINITION_PROCESS_TYPE_ALLOWED,
    PROCESS_TYPE_STANDARD,
    ProcessType,
    process_type_allowed_constraint,
)


class IntakeStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", db_gettext_lazy(
        "administration.choice_intake_status_in_progress", "In progress"
    )
    REOPENED = "REOPENED", db_gettext_lazy(
        "administration.choice_intake_status_reopened", "Reopened for patient"
    )
    SUBMITTED = "SUBMITTED", db_gettext_lazy(
        "administration.choice_intake_status_submitted", "Submitted"
    )


class IntakePdfStatus(models.TextChoices):
    PENDING = "PENDING", db_gettext_lazy(
        "administration.choice_intake_pdf_status_pending", "Pending"
    )
    PROCESSING = "PROCESSING", db_gettext_lazy(
        "administration.choice_intake_pdf_status_processing", "Processing"
    )
    COMPLETED = "COMPLETED", db_gettext_lazy(
        "administration.choice_intake_pdf_status_completed", "Completed"
    )
    FAILED = "FAILED", db_gettext_lazy(
        "administration.choice_intake_pdf_status_failed", "Failed"
    )


class IntakeOutboxEventType(models.TextChoices):
    GENERATE_INTAKE_PDF = "GENERATE_INTAKE_PDF", db_gettext_lazy(
        "administration.choice_intake_outbox_event_generate_intake_pdf",
        "Generate intake PDF",
    )
    HIDRIVE_UPLOAD_INTAKE_PDF = "HIDRIVE_UPLOAD_INTAKE_PDF", db_gettext_lazy(
        "administration.choice_intake_outbox_event_hidrive_upload_intake_pdf",
        "HiDrive upload intake PDF",
    )


class IntakeOutboxStatus(models.TextChoices):
    PENDING = "PENDING", db_gettext_lazy(
        "administration.choice_intake_outbox_status_pending", "Pending"
    )
    PROCESSING = "PROCESSING", db_gettext_lazy(
        "administration.choice_intake_outbox_status_processing", "Processing"
    )
    PROCESSED = "PROCESSED", db_gettext_lazy(
        "administration.choice_intake_outbox_status_processed", "Processed"
    )
    FAILED = "FAILED", db_gettext_lazy(
        "administration.choice_intake_outbox_status_failed", "Failed"
    )
    DEAD_LETTER = "DEAD_LETTER", db_gettext_lazy(
        "administration.choice_intake_outbox_status_dead_letter", "Dead letter"
    )


def _attach_process_types(
    *,
    through_model: type[models.Model],
    fk_name: str,
    definition: models.Model,
    process_types: list[str] | None,
) -> None:
    """Link catalog row to processes. None → STANDARD (test/legacy create)."""
    values = [PROCESS_TYPE_STANDARD] if process_types is None else list(process_types)
    for process_type in values:
        through_model.objects.get_or_create(
            **{fk_name: definition, "process_type": process_type}
        )


def _clean_active_definition_requires_process(definition: models.Model) -> None:
    """Active catalog rows must have ≥1 process; skip on ADD.

    UUID ``pk`` is assigned in memory before INSERT. Admin validates the parent
    before inlines exist, so ``process_links.exists()`` is always false on ADD.

    Error is non-field: ``process_links`` is a reverse relation, not a parent
    form field — a keyed ``ValidationError`` would 500 in admin ``add_error``.
    """
    if definition._state.adding or not definition.is_active:
        return
    if not definition.process_links.exists():  # type: ignore[attr-defined]
        raise ValidationError(
            {
                NON_FIELD_ERRORS: [
                    db_gettext_lazy(
                        "administration.error_definition_requires_process",
                        "At least one process type is required.",
                    )
                ]
            }
        )


def _pop_process_types(kwargs: dict, defaults: dict | None = None) -> tuple:
    """Pull non-field ``process_types`` off manager create/get_or_create kwargs."""
    merged = dict(defaults or {})
    process_types = merged.pop("process_types", None)
    process_types = kwargs.pop("process_types", process_types)
    return process_types, merged


class ConsentDefinitionManager(models.Manager):
    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        process_types, _ = _pop_process_types(kwargs)
        obj = super().create(**kwargs)
        _attach_process_types(
            through_model=ConsentDefinitionProcess,
            fk_name="consent_definition",
            definition=obj,
            process_types=process_types,
        )
        return obj

    def get_or_create(self, defaults=None, **kwargs):  # type: ignore[no-untyped-def]
        process_types, defaults = _pop_process_types(kwargs, defaults)
        obj, created = super().get_or_create(defaults=defaults or None, **kwargs)
        if created:
            _attach_process_types(
                through_model=ConsentDefinitionProcess,
                fk_name="consent_definition",
                definition=obj,
                process_types=process_types,
            )
        return obj, created


class AnamnesisQuestionDefinitionManager(models.Manager):
    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        process_types, _ = _pop_process_types(kwargs)
        obj = super().create(**kwargs)
        _attach_process_types(
            through_model=AnamnesisQuestionDefinitionProcess,
            fk_name="question_definition",
            definition=obj,
            process_types=process_types,
        )
        return obj

    def get_or_create(self, defaults=None, **kwargs):  # type: ignore[no-untyped-def]
        process_types, defaults = _pop_process_types(kwargs, defaults)
        obj, created = super().get_or_create(defaults=defaults or None, **kwargs)
        if created:
            _attach_process_types(
                through_model=AnamnesisQuestionDefinitionProcess,
                fk_name="question_definition",
                definition=obj,
                process_types=process_types,
            )
        return obj, created


class ConsentDefinition(models.Model):
    objects = ConsentDefinitionManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=60, verbose_name=db_gettext_lazy("administration.field_code", "Code")
    )
    version = models.IntegerField(
        verbose_name=db_gettext_lazy("administration.field_version", "Version")
    )
    title_de = models.CharField(
        max_length=200,
        verbose_name=db_gettext_lazy("administration.field_title_de", "Title de"),
    )
    title_en = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=db_gettext_lazy("administration.field_title_en", "Title en"),
    )
    title_pl = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=db_gettext_lazy("administration.field_title_pl", "Title pl"),
    )
    content_de = models.TextField(
        verbose_name=db_gettext_lazy("administration.field_content_de", "Content de")
    )
    content_en = models.TextField(
        blank=True,
        default="",
        verbose_name=db_gettext_lazy("administration.field_content_en", "Content en"),
    )
    content_pl = models.TextField(
        blank=True,
        default="",
        verbose_name=db_gettext_lazy("administration.field_content_pl", "Content pl"),
    )
    is_required = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_required", "Is required"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_active", "Is active"),
    )
    display_order = models.SmallIntegerField(
        default=0,
        verbose_name=db_gettext_lazy(
            "administration.field_display_order", "Display order"
        ),
    )
    effective_from = models.DateField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy(
            "administration.field_effective_from", "Effective from"
        ),
    )
    effective_to = models.DateField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_effective_to", "Effective to"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )

    class Meta:
        db_table = "consent_definition"
        verbose_name = db_gettext_lazy(
            "administration.model_consentdefinition", "Consent definition"
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_consentdefinition_plural", "Consent definitions"
        )
        constraints = [
            models.UniqueConstraint(
                fields=["code", "version"], name="consent_definition_unique"
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=F("effective_from")),
                name="consent_effective_to_after_from",
            ),
        ]
        indexes = [
            models.Index(fields=["code", "is_active", "-effective_from"]),
        ]

    def clean(self) -> None:
        super().clean()
        _clean_active_definition_requires_process(self)

    def __str__(self) -> str:
        return self.title_de or f"{self.code} (v{self.version})"


class ConsentDefinitionProcess(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consent_definition = models.ForeignKey(
        ConsentDefinition,
        on_delete=models.CASCADE,
        related_name="process_links",
        verbose_name=db_gettext_lazy(
            "administration.model_consentdefinition", "Consent definition"
        ),
    )
    process_type = models.CharField(
        max_length=20,
        choices=ProcessType.choices,
        verbose_name=db_gettext_lazy(
            "administration.field_process_type", "Process type"
        ),
    )

    class Meta:
        db_table = "consent_definition_process"
        verbose_name = db_gettext_lazy(
            "administration.model_consentdefinitionprocess",
            "Consent definition process",
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_consentdefinitionprocess_plural",
            "Consent definition processes",
        )
        constraints = [
            models.UniqueConstraint(
                fields=["consent_definition", "process_type"],
                name="consent_definition_process_unique",
            ),
            process_type_allowed_constraint(
                name=CONSENT_DEFINITION_PROCESS_TYPE_ALLOWED
            ),
        ]

    def __str__(self) -> str:
        return f"{self.consent_definition_id} / {self.get_process_type_display()}"


class AnamnesisQuestionDefinition(models.Model):
    objects = AnamnesisQuestionDefinitionManager()

    class AnswerType(models.TextChoices):
        SINGLE_CHOICE = "SINGLE_CHOICE", db_gettext_lazy(
            "administration.choice_anamnesis_answer_single_choice",
            "Single choice",
        )
        MULTI_CHOICE = "MULTI_CHOICE", db_gettext_lazy(
            "administration.choice_anamnesis_answer_multi_choice",
            "Multi choice",
        )
        BOOLEAN = "BOOLEAN", db_gettext_lazy(
            "administration.choice_anamnesis_answer_boolean", "Boolean"
        )
        TEXT_OPTIONAL = "TEXT_OPTIONAL", db_gettext_lazy(
            "administration.choice_anamnesis_answer_text_optional",
            "Text optional",
        )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=80, verbose_name=db_gettext_lazy("administration.field_code", "Code")
    )
    version = models.IntegerField(
        default=1,
        verbose_name=db_gettext_lazy("administration.field_version", "Version"),
    )
    question_text_de = models.TextField(
        verbose_name=db_gettext_lazy(
            "administration.field_question_text_de", "Question text de"
        )
    )
    question_text_en = models.TextField(
        verbose_name=db_gettext_lazy(
            "administration.field_question_text_en", "Question text en"
        )
    )
    question_text_pl = models.TextField(
        blank=True,
        default="",
        verbose_name=db_gettext_lazy(
            "administration.field_question_text_pl", "Question text pl"
        ),
    )
    answer_type = models.CharField(
        max_length=30,
        choices=AnswerType.choices,
        default=AnswerType.SINGLE_CHOICE,
        verbose_name=db_gettext_lazy("administration.field_answer_type", "Answer type"),
    )
    is_required = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_required", "Is required"),
    )
    display_order = models.SmallIntegerField(
        default=0,
        verbose_name=db_gettext_lazy(
            "administration.field_display_order", "Display order"
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_active", "Is active"),
    )
    effective_from = models.DateField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy(
            "administration.field_effective_from", "Effective from"
        ),
    )
    effective_to = models.DateField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_effective_to", "Effective to"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )

    class Meta:
        db_table = "anamnesis_question_definition"
        verbose_name = db_gettext_lazy(
            "administration.model_anamnesisquestiondefinition",
            "Anamnesis question definition",
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_anamnesisquestiondefinition_plural",
            "Anamnesis question definitions",
        )
        constraints = [
            models.UniqueConstraint(
                fields=["code", "version"],
                name="anamnesis_question_definition_unique",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=F("effective_from")),
                name="anamnesis_question_effective_to_after_from",
            ),
        ]
        indexes = [
            models.Index(fields=["code", "is_active", "-effective_from"]),
        ]

    def clean(self) -> None:
        super().clean()
        _clean_active_definition_requires_process(self)

    def __str__(self) -> str:
        return self.question_text_de or f"{self.code} (v{self.version})"


class AnamnesisQuestionDefinitionProcess(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question_definition = models.ForeignKey(
        AnamnesisQuestionDefinition,
        on_delete=models.CASCADE,
        related_name="process_links",
        verbose_name=db_gettext_lazy(
            "administration.model_anamnesisquestiondefinition",
            "Anamnesis question definition",
        ),
    )
    process_type = models.CharField(
        max_length=20,
        choices=ProcessType.choices,
        verbose_name=db_gettext_lazy(
            "administration.field_process_type", "Process type"
        ),
    )

    class Meta:
        db_table = "anamnesis_question_definition_process"
        verbose_name = db_gettext_lazy(
            "administration.model_anamnesisquestiondefinitionprocess",
            "Anamnesis question process",
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_anamnesisquestiondefinitionprocess_plural",
            "Anamnesis question processes",
        )
        constraints = [
            models.UniqueConstraint(
                fields=["question_definition", "process_type"],
                name="anamnesis_question_process_unique",
            ),
            process_type_allowed_constraint(
                name=ANAMNESIS_QUESTION_PROCESS_TYPE_ALLOWED
            ),
        ]

    def __str__(self) -> str:
        return f"{self.question_definition_id} / {self.get_process_type_display()}"


class AnamnesisOptionDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        AnamnesisQuestionDefinition,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=db_gettext_lazy(
            "administration.field_anamnesis_question", "Anamnesis question"
        ),
    )
    code = models.CharField(
        max_length=80, verbose_name=db_gettext_lazy("administration.field_code", "Code")
    )
    option_text_de = models.TextField(
        verbose_name=db_gettext_lazy(
            "administration.field_option_text_de", "Option text de"
        )
    )
    option_text_en = models.TextField(
        verbose_name=db_gettext_lazy(
            "administration.field_option_text_en", "Option text en"
        )
    )
    option_text_pl = models.TextField(
        blank=True,
        default="",
        verbose_name=db_gettext_lazy(
            "administration.field_option_text_pl", "Option text pl"
        ),
    )
    display_order = models.SmallIntegerField(
        default=0,
        verbose_name=db_gettext_lazy(
            "administration.field_display_order", "Display order"
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
        db_table = "anamnesis_option_definition"
        verbose_name = db_gettext_lazy(
            "administration.model_anamnesisoptiondefinition",
            "Anamnesis option definition",
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_anamnesisoptiondefinition_plural",
            "Anamnesis option definitions",
        )
        constraints = [
            models.UniqueConstraint(
                fields=["question", "code"],
                name="anamnesis_option_definition_unique",
            )
        ]
        indexes = [
            models.Index(fields=["question", "is_active", "display_order"]),
        ]

    def __str__(self) -> str:
        return self.option_text_de or f"{self.code}"


class PatientIntakeForm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    queue_entry = models.OneToOneField(
        "reception.QueueEntry",
        on_delete=models.CASCADE,
        related_name="intake_form",
        verbose_name=db_gettext_lazy("administration.field_queue_entry", "Queue entry"),
    )
    session = models.OneToOneField(
        "reception.PatientFormSession",
        on_delete=models.RESTRICT,
        related_name="intake_form",
        verbose_name=db_gettext_lazy(
            "administration.field_patient_form_session", "Patient form session"
        ),
    )
    form_status = models.CharField(
        max_length=20,
        choices=IntakeStatus.choices,
        default=IntakeStatus.IN_PROGRESS,
        verbose_name=db_gettext_lazy("administration.field_form_status", "Form status"),
    )
    body_map_schema_version = models.SmallIntegerField(
        default=1,
        verbose_name=db_gettext_lazy(
            "administration.field_body_map_schema_version", "Body map schema version"
        ),
    )
    body_map_data = models.JSONField(
        default=list,
        blank=True,
        verbose_name=db_gettext_lazy(
            "administration.field_body_map_data", "Body map data"
        ),
    )
    anamnesis_schema_version = models.SmallIntegerField(
        default=1,
        verbose_name=db_gettext_lazy(
            "administration.field_anamnesis_schema_version", "Anamnesis schema version"
        ),
    )
    anamnesis_payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=db_gettext_lazy(
            "administration.field_anamnesis_payload", "Anamnesis payload"
        ),
    )
    telederm_schema_version = models.SmallIntegerField(
        default=TELEDERM_PAYLOAD_SCHEMA_VERSION,
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_schema_version",
            "Telederm schema version",
        ),
    )
    telederm_payload = models.JSONField(
        default=default_telederm_payload,
        blank=True,
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_payload", "Telederm payload"
        ),
    )
    signature_file_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_signature_file_path", "Signature file path"
        ),
    )
    signature_sha256 = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_signature_sha256", "Signature sha256"
        ),
    )
    submitted_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_submitted_at", "Submitted at"
        ),
    )
    reception_note = models.TextField(
        blank=True,
        default="",
        verbose_name=db_gettext_lazy(
            "administration.field_reception_note", "Reception note"
        ),
    )
    reception_note_updated_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_reception_note_updated_at",
            "Reception note updated at",
        ),
    )
    reception_note_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="intake_reception_notes_updated",
        verbose_name=db_gettext_lazy(
            "administration.field_reception_note_updated_by",
            "Reception note updated by",
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
        db_table = "patient_intake_form"
        verbose_name = db_gettext_lazy(
            "administration.model_patientintakeform", "Patient intake form"
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_patientintakeform_plural", "Patient intake forms"
        )
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
                condition=Q(
                    form_status__in=[
                        IntakeStatus.IN_PROGRESS,
                        IntakeStatus.REOPENED,
                    ]
                )
                | (
                    Q(form_status=IntakeStatus.SUBMITTED)
                    & Q(submitted_at__isnull=False)
                    & (
                        Q(signature_file_path__isnull=False)
                        | (Q(signature_sha256__isnull=False) & ~Q(signature_sha256=""))
                    )
                ),
                name="intake_submitted_requires_signature",
            ),
        ]

    def __str__(self) -> str:
        return format_administration_message(
            "administration.str_intake_form",
            "Fragebogen: {patient} ({status})",
            patient=self.queue_entry.patient,
            status=self.get_form_status_display(),
        )


class PatientIntakeConsent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intake_form = models.ForeignKey(
        PatientIntakeForm,
        on_delete=models.CASCADE,
        related_name="consents",
        verbose_name=db_gettext_lazy("administration.field_intake_form", "Intake form"),
    )
    consent_definition = models.ForeignKey(
        ConsentDefinition,
        on_delete=models.RESTRICT,
        related_name="intake_consents",
        verbose_name=db_gettext_lazy(
            "administration.field_consent_definition", "Consent definition"
        ),
    )
    accepted = models.BooleanField(
        verbose_name=db_gettext_lazy("administration.field_accepted", "Accepted")
    )
    accepted_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy("administration.field_accepted_at", "Accepted at"),
    )
    selected_option_code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name=db_gettext_lazy(
            "administration.field_selected_option_code", "Selected option code"
        ),
    )
    selected_option_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name=db_gettext_lazy(
            "administration.field_selected_option_codes", "Selected option codes"
        ),
    )

    class Meta:
        db_table = "patient_intake_consent"
        verbose_name = db_gettext_lazy(
            "administration.model_patientintakeconsent", "Patient intake consent"
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_patientintakeconsent_plural",
            "Patient intake consents",
        )
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

    def __str__(self) -> str:
        yes_no = format_administration_message(
            "administration.str_yes" if self.accepted else "administration.str_no",
            "Ja" if self.accepted else "Nein",
        )
        return format_administration_message(
            "administration.str_intake_consent",
            "{consent} – {yes_no}",
            consent=self.consent_definition,
            yes_no=yes_no,
        )


class IntakeDocumentVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intake_form = models.ForeignKey(
        PatientIntakeForm,
        on_delete=models.CASCADE,
        related_name="document_versions",
        verbose_name=db_gettext_lazy("administration.field_intake_form", "Intake form"),
    )
    version_no = models.IntegerField(
        verbose_name=db_gettext_lazy("administration.field_version_no", "Version no")
    )
    form_locale = models.CharField(
        max_length=10,
        verbose_name=db_gettext_lazy("administration.field_form_locale", "Form locale"),
    )
    snapshot_payload = models.JSONField(
        default=dict,
        verbose_name=db_gettext_lazy(
            "administration.field_snapshot_payload", "Snapshot payload"
        ),
    )
    pdf_generation_status = models.CharField(
        max_length=20,
        choices=IntakePdfStatus.choices,
        default=IntakePdfStatus.PENDING,
        verbose_name=db_gettext_lazy(
            "administration.field_pdf_generation_status", "PDF generation status"
        ),
    )
    pdf_local_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_pdf_local_path", "Pdf local path"
        ),
    )
    pdf_checksum_sha256 = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_pdf_checksum_sha256", "Pdf checksum sha256"
        ),
    )
    hidrive_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_hidrive_path", "Hidrive path"
        ),
    )
    hidrive_sent = models.BooleanField(
        default=False,
        verbose_name=db_gettext_lazy(
            "administration.field_hidrive_sent", "Hidrive sent"
        ),
    )
    hidrive_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_hidrive_sent_at", "Hidrive sent at"
        ),
    )
    local_pdf_deleted_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_local_pdf_deleted_at", "Local pdf deleted at"
        ),
    )
    anonymization_deleted_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_anonymization_deleted_at", "Anonymization deleted at"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )

    class Meta:
        db_table = "intake_document_version"
        verbose_name = db_gettext_lazy(
            "administration.model_intakedocumentversion",
            "Intake document version",
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_intakedocumentversion_plural",
            "Intake document versions",
        )
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
                condition=~Q(pdf_generation_status=IntakePdfStatus.COMPLETED)
                | Q(pdf_local_path__isnull=False)
                | Q(local_pdf_deleted_at__isnull=False)
                | Q(anonymization_deleted_at__isnull=False),
                name="intake_document_pdf_completed_requires_path",
            ),
            models.CheckConstraint(
                condition=Q(hidrive_sent=False)
                | (Q(hidrive_sent=True) & Q(hidrive_sent_at__isnull=False)),
                name="intake_document_hidrive_sent_requires_time",
            ),
            models.CheckConstraint(
                condition=Q(local_pdf_deleted_at__isnull=True) | Q(hidrive_sent=True),
                name="intake_document_local_pdf_deletion_guard",
            ),
        ]
        indexes = [
            models.Index(fields=["intake_form", "-version_no"]),
            models.Index(fields=["pdf_generation_status", "-created_at"]),
            models.Index(fields=["hidrive_sent", "-created_at"]),
            models.Index(
                fields=["created_at"],
                name="intake_document_retention_idx",
                condition=Q(hidrive_sent=True, local_pdf_deleted_at__isnull=True),
            ),
            GinIndex(
                fields=["snapshot_payload"],
                name="intake_snap_gin_idx",
                opclasses=["jsonb_path_ops"],
            ),
        ]

    def __str__(self) -> str:
        return format_administration_message(
            "administration.str_intake_document_version",
            "Version {version_no} des Fragebogens {form} ({status})",
            version_no=self.version_no,
            form=self.intake_form,
            status=self.get_pdf_generation_status_display(),
        )


class IntakeOutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intake_document_version = models.ForeignKey(
        IntakeDocumentVersion,
        on_delete=models.CASCADE,
        related_name="outbox_events",
        verbose_name=db_gettext_lazy(
            "administration.field_intake_document_version", "Intake document version"
        ),
    )
    aggregate_type = models.CharField(
        max_length=50,
        default="INTAKE_DOCUMENT_VERSION",
        verbose_name=db_gettext_lazy(
            "administration.field_aggregate_type", "Aggregate type"
        ),
    )
    aggregate_id = models.UUIDField(
        verbose_name=db_gettext_lazy(
            "administration.field_aggregate_id", "Aggregate ID"
        )
    )
    event_type = models.CharField(
        max_length=40,
        choices=IntakeOutboxEventType.choices,
        verbose_name=db_gettext_lazy("administration.field_event_type", "Event type"),
    )
    payload_schema_version = models.SmallIntegerField(
        default=1,
        verbose_name=db_gettext_lazy(
            "administration.field_payload_schema_version", "Payload schema version"
        ),
    )
    payload = models.JSONField(
        default=dict,
        verbose_name=db_gettext_lazy("administration.field_payload", "Payload"),
    )
    status = models.CharField(
        max_length=20,
        choices=IntakeOutboxStatus.choices,
        default=IntakeOutboxStatus.PENDING,
        verbose_name=db_gettext_lazy("administration.field_status", "Status"),
    )
    retry_count = models.SmallIntegerField(
        default=0,
        verbose_name=db_gettext_lazy("administration.field_retry_count", "Retry count"),
    )
    max_retries = models.SmallIntegerField(
        default=outbox_max_retries_default,
        verbose_name=db_gettext_lazy("administration.field_max_retries", "Max retries"),
    )
    available_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy(
            "administration.field_available_at", "Available at"
        ),
    )
    locked_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy("administration.field_locked_at", "Locked at"),
    )
    processed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_processed_at", "Processed at"
        ),
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_error_message", "Error message"
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
        db_table = "intake_outbox_event"
        verbose_name = db_gettext_lazy(
            "administration.model_intakeoutboxevent", "Intake outbox event"
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_intakeoutboxevent_plural", "Intake outbox events"
        )
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
            models.Index(
                fields=[
                    "event_type",
                    "status",
                    "retry_count",
                    "available_at",
                    "payload_schema_version",
                ]
            ),
            models.Index(fields=["intake_document_version", "-created_at"]),
            models.Index(
                fields=["status", "available_at"],
                name="intake_outbox_pend_fail_idx",
                condition=Q(
                    status__in=[IntakeOutboxStatus.PENDING, IntakeOutboxStatus.FAILED]
                ),
            ),
            models.Index(
                fields=["available_at", "created_at"],
                name="intake_outbox_pf_order_idx",
                condition=Q(
                    status__in=[IntakeOutboxStatus.PENDING, IntakeOutboxStatus.FAILED]
                ),
            ),
            GinIndex(
                fields=["payload"],
                name="intake_outbox_payload_gin_idx",
                opclasses=["jsonb_path_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_event_type_display()} – {self.intake_document_version} ({self.get_status_display()})"
