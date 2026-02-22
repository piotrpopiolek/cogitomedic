from __future__ import annotations

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Q


class IntakeStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    SUBMITTED = "SUBMITTED", "Submitted"


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
