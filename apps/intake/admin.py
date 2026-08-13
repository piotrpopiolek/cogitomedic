from __future__ import annotations

from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone

from apps.core.admin_list_page_size import CogitomedicaModelAdmin
from apps.core.exceptions import StateTransitionError
from apps.core.translation_service import (
    db_gettext_lazy,
    format_administration_message,
)
from apps.intake.models import (
    AnamnesisOptionDefinition,
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    IntakeDocumentVersion,
    IntakeOutboxEvent,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.intake.services import reopen_patient_intake_form

_MARKDOWN_HELP = (
    "Markdown-Formatierung wird unterstützt. "
    "Überschriften: Zeile mit ## beginnen (z.B. ## Verantwortliche Stelle). "
    "Fett: **Text**, Kursiv: *Text*. "
    "Zentriert: -> Text <- (z.B. -> Unterschrift <-)."
)


@admin.register(ConsentDefinition)
class ConsentDefinitionAdmin(CogitomedicaModelAdmin):
    show_add_link = True
    list_display = (
        "code",
        "version",
        "title_de",
        "title_en",
        "title_pl",
        "is_required",
        "display_order",
        "effective_from",
        "created_at",
        "is_active",
    )
    list_display_links = ("code",)
    list_filter = ("is_required", "is_active")
    search_fields = ("code", "title_de", "title_en", "title_pl")
    ordering = ["display_order", "code", "version"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "code",
                    "version",
                    "is_required",
                    "is_active",
                    "display_order",
                    "effective_to",
                )
            },
        ),
        ("Deutsch", {"fields": ("title_de", "content_de")}),
        ("English", {"fields": ("title_en", "content_en")}),
        ("Polski", {"fields": ("title_pl", "content_pl")}),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in ("content_de", "content_en", "content_pl"):
            kwargs["help_text"] = _MARKDOWN_HELP
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def has_add_permission(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            return True
        return super().has_add_permission(request)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_add_permission(request):
            info = self.model._meta.app_label, self.model._meta.model_name
            extra_context["add_url"] = reverse("admin:%s_%s_add" % info)
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(AnamnesisQuestionDefinition)
class AnamnesisQuestionDefinitionAdmin(CogitomedicaModelAdmin):
    list_display = (
        "code",
        "version",
        "answer_type",
        "question_text_de",
        "question_text_pl",
        "is_required",
        "display_order",
        "created_at",
        "is_active",
    )
    list_display_links = ("code",)
    list_filter = ("answer_type", "is_required", "is_active")
    search_fields = ("code", "question_text_de", "question_text_en", "question_text_pl")
    ordering = ["-created_at"]


@admin.register(AnamnesisOptionDefinition)
class AnamnesisOptionDefinitionAdmin(CogitomedicaModelAdmin):
    list_display = (
        "question",
        "code",
        "option_text_de",
        "option_text_pl",
        "display_order",
        "created_at",
        "is_active",
    )
    list_display_links = ("question",)
    list_filter = ("is_active",)
    search_fields = ("code", "option_text_de", "option_text_en", "option_text_pl")
    ordering = ["-created_at"]


@admin.register(PatientIntakeForm)
class PatientIntakeFormAdmin(CogitomedicaModelAdmin):
    actions = ("reopen_intake_for_patient_editing",)

    list_display = (
        "queue_entry",
        "form_status",
        "submitted_at",
        "reception_note_updated_at",
        "created_at",
        "updated_at",
    )
    list_display_links = ("queue_entry",)
    list_filter = ("form_status",)
    ordering = ["-created_at"]
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "reception_note_updated_at",
        "reception_note_updated_by",
        "body_map_schema_version",
        "body_map_data",
        "anamnesis_schema_version",
        "anamnesis_payload",
    )
    date_hierarchy = "created_at"
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "queue_entry",
                    "session",
                    "form_status",
                    "submitted_at",
                    "reception_note",
                    "reception_note_updated_at",
                    "reception_note_updated_by",
                )
            },
        ),
        (
            db_gettext_lazy(
                "administration.fieldset_body_map",
                "Körperschema",
            ),
            {"fields": ("body_map_schema_version", "body_map_data")},
        ),
        (
            db_gettext_lazy(
                "administration.fieldset_anamnesis",
                "Anamnese",
            ),
            {"fields": ("anamnesis_schema_version", "anamnesis_payload")},
        ),
        (
            db_gettext_lazy(
                "administration.fieldset_signature",
                "Unterschrift",
            ),
            {"fields": ("signature_file_path", "signature_sha256")},
        ),
        (
            db_gettext_lazy(
                "administration.fieldset_metadata",
                "Metadaten",
            ),
            {"fields": ("id", "created_at", "updated_at")},
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("queue_entry", "queue_entry__patient", "session")

    def save_model(self, request, obj, form, change):
        if "reception_note" in form.changed_data:
            obj.reception_note = (obj.reception_note or "").strip()
            obj.reception_note_updated_at = timezone.now()
            obj.reception_note_updated_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(
        description=db_gettext_lazy(
            "administration.admin_action_reopen_intake_short",
            "Reopen intake for patient editing (tablet)",
        )
    )
    def reopen_intake_for_patient_editing(self, request, queryset):
        if not (
            request.user.is_superuser
            or getattr(request.user, "is_admin_role", False)
            or getattr(request.user, "is_manager", False)
            or getattr(request.user, "is_reception", False)
        ):
            self.message_user(
                request,
                format_administration_message(
                    "administration.admin_intake_reopen_permission_denied",
                    "You do not have permission to reopen intake forms.",
                    request=request,
                ),
                level=messages.ERROR,
            )
            return
        reopened = 0
        skipped = 0
        for form in queryset.select_related("queue_entry"):
            try:
                reopen_patient_intake_form(
                    intake_form_id=form.id,
                    actor_user_id=request.user.id,
                    reception_note=(form.reception_note or "").strip(),
                )
                reopened += 1
            except StateTransitionError:
                skipped += 1
        self.message_user(
            request,
            format_administration_message(
                "administration.admin_intake_reopen_result",
                "Reopened {reopened} intake form(s); skipped {skipped}.",
                request=request,
                reopened=reopened,
                skipped=skipped,
            ),
            level=messages.WARNING if skipped else messages.INFO,
        )


@admin.register(PatientIntakeConsent)
class PatientIntakeConsentAdmin(CogitomedicaModelAdmin):
    list_display = ("intake_form", "consent_definition", "accepted", "accepted_at")
    list_display_links = ("intake_form",)
    list_filter = ("accepted",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("intake_form", "consent_definition")


@admin.register(IntakeDocumentVersion)
class IntakeDocumentVersionAdmin(CogitomedicaModelAdmin):
    list_display = (
        "id",
        "intake_form",
        "version_no",
        "form_locale",
        "pdf_generation_status",
        "hidrive_sent",
        "created_at",
    )
    list_display_links = ("id",)
    list_filter = ("pdf_generation_status", "hidrive_sent", "form_locale")
    ordering = ["-created_at"]
    raw_id_fields = ("intake_form",)
    readonly_fields = (
        "id",
        "snapshot_payload",
        "pdf_checksum_sha256",
        "hidrive_path",
        "hidrive_sent_at",
        "created_at",
    )
    date_hierarchy = "created_at"


@admin.register(IntakeOutboxEvent)
class IntakeOutboxEventAdmin(CogitomedicaModelAdmin):
    list_display = (
        "id",
        "event_type",
        "status",
        "retry_count",
        "max_retries",
        "intake_document_version",
        "available_at",
        "processed_at",
        "created_at",
    )
    list_display_links = ("id",)
    list_filter = ("event_type", "status")
    ordering = ["-created_at"]
    search_fields = ("error_message",)
    raw_id_fields = ("intake_document_version",)
    readonly_fields = (
        "id",
        "aggregate_type",
        "aggregate_id",
        "payload",
        "payload_schema_version",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
