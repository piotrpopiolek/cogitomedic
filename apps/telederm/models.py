"""Teledermatology adaptive questionnaire catalog (CCE paths)."""

from __future__ import annotations

import uuid

from django.db import models

from apps.core.translation_service import db_gettext_lazy


class TeledermAnswerType(models.TextChoices):
    SINGLE = "SINGLE", db_gettext_lazy(
        "administration.choice_telederm_answer_type_single", "Single choice"
    )
    MULTIPLE = "MULTIPLE", db_gettext_lazy(
        "administration.choice_telederm_answer_type_multiple", "Multiple choice"
    )
    FREE_TEXT = "FREE_TEXT", db_gettext_lazy(
        "administration.choice_telederm_answer_type_free_text", "Free text"
    )


class TeledermSection(models.TextChoices):
    TRIAGE = "TRIAGE", "Triage"
    CHIEF_COMPLAINT = "CHIEF_COMPLAINT", "Chief complaint"
    QUESTIONNAIRE = "QUESTIONNAIRE", "Questionnaire"


class TeledermQuestionDefinition(models.Model):
    """Catalog row for telederm intake (triage, chief complaint, path questions)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question_id = models.CharField(
        max_length=32,
        unique=True,
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_question_id", "Question id"
        ),
    )
    path_code = models.CharField(
        max_length=32,
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_path_code", "Path code"
        ),
        help_text="TRIAGE, CHIEF, CCE-001, GLOBAL, …",
    )
    section = models.CharField(
        max_length=32,
        choices=TeledermSection.choices,
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_section", "Section"
        ),
    )
    answer_type = models.CharField(
        max_length=20,
        choices=TeledermAnswerType.choices,
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_answer_type", "Answer type"
        ),
    )
    question_text_de = models.TextField(
        verbose_name=db_gettext_lazy(
            "administration.field_question_text_de", "Question text (DE)"
        ),
    )
    question_text_en = models.TextField(
        blank=True,
        default="",
        verbose_name=db_gettext_lazy(
            "administration.field_question_text_en", "Question text (EN)"
        ),
    )
    question_text_pl = models.TextField(
        blank=True,
        default="",
        verbose_name=db_gettext_lazy(
            "administration.field_question_text_pl", "Question text (PL)"
        ),
    )
    show_if = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_show_if", "Show if"
        ),
    )
    include_in_summary = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy(
            "administration.field_include_in_summary", "Include in summary"
        ),
    )
    is_required = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_required", "Required"),
    )
    display_order = models.PositiveIntegerField(
        default=0,
        verbose_name=db_gettext_lazy(
            "administration.field_display_order", "Display order"
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_active", "Active"),
    )

    class Meta:
        db_table = "telederm_question_definition"
        verbose_name = db_gettext_lazy(
            "administration.model_telederm_question", "Telederm question"
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_telederm_question_plural", "Telederm questions"
        )
        ordering = ["display_order", "question_id"]

    def __str__(self) -> str:
        return self.question_id


class TeledermQuestionOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        TeledermQuestionDefinition,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_question", "Question"
        ),
    )
    code = models.CharField(
        max_length=64,
        verbose_name=db_gettext_lazy("administration.field_option_code", "Option code"),
    )
    label_de = models.CharField(max_length=500)
    label_en = models.CharField(max_length=500, blank=True, default="")
    label_pl = models.CharField(max_length=500, blank=True, default="")
    is_urgent = models.BooleanField(
        default=False,
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_is_urgent", "Urgent triage flag"
        ),
    )
    activates_path_code = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=db_gettext_lazy(
            "administration.field_telederm_activates_path", "Activates path code"
        ),
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "telederm_question_option"
        verbose_name = db_gettext_lazy(
            "administration.model_telederm_option", "Telederm option"
        )
        verbose_name_plural = db_gettext_lazy(
            "administration.model_telederm_option_plural", "Telederm options"
        )
        constraints = [
            models.UniqueConstraint(
                fields=["question", "code"],
                name="telederm_question_option_unique",
            ),
        ]
        ordering = ["display_order", "code"]

    def __str__(self) -> str:
        return f"{self.question.question_id}/{self.code}"
