from __future__ import annotations

from datetime import timedelta

from django import forms
from django.contrib import admin
from django.utils import timezone

from apps.operations.services import create_audit_event
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientContactHistory,
    PatientFormSession,
    PatientImportBatch,
    PatientImportError,
    QueueEntry,
    TabletDevice,
)


def _ensure_patient_temp_identity_alert(patient: Patient) -> None:
    """Set identity alert window when doctolib_patient_id is empty (constraint patient_temp_identity_requires_alert)."""
    if patient.doctolib_patient_id:
        return
    if patient.identity_alert_created_at is None and patient.identity_resolution_due_at is None:
        now = timezone.now()
        patient.identity_alert_created_at = now
        patient.identity_resolution_due_at = now + timedelta(hours=24)
    elif patient.identity_alert_created_at is None:
        patient.identity_alert_created_at = (
            patient.identity_resolution_due_at - timedelta(hours=24)
            if patient.identity_resolution_due_at
            else timezone.now()
        )
    elif patient.identity_resolution_due_at is None:
        patient.identity_resolution_due_at = patient.identity_alert_created_at + timedelta(hours=24)


class PatientAdminForm(forms.ModelForm):
    """Ensure temp-identity alert fields are set before save (constraint patient_temp_identity_requires_alert)."""

    class Meta:
        model = Patient
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("doctolib_patient_id"):
            return cleaned
        now = timezone.now()
        if not cleaned.get("identity_alert_created_at"):
            cleaned["identity_alert_created_at"] = now
        if not cleaned.get("identity_resolution_due_at"):
            cleaned["identity_resolution_due_at"] = cleaned.get("identity_alert_created_at") or now + timedelta(
                hours=24
            )
        return cleaned


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    form = PatientAdminForm
    list_display = ("last_name", "first_name", "date_of_birth", "identity_status", "is_active", "created_at")
    list_filter = ("identity_status", "is_active", "external_source")
    search_fields = ("first_name", "last_name", "email", "phone", "doctolib_patient_id")
    readonly_fields = ("id", "created_at", "updated_at")
    date_hierarchy = "created_at"

    def save_model(self, request, obj, form, change):
        _ensure_patient_temp_identity_alert(obj)
        super().save_model(request, obj, form, change)
        # Audit: when a new patient is created with temporary identity (alert set), log for audit list.
        if (
            not change
            and not obj.doctolib_patient_id
            and obj.identity_alert_created_at
            and obj.identity_resolution_due_at
        ):
            actor_id = getattr(request.user, "id", None) if request.user.is_authenticated else None
            create_audit_event(
                event_type="PATIENT_IDENTITY_ALERT_SET",
                actor_user_id=actor_id,
                patient_id=obj.pk,
                metadata={
                    "identity_alert_created_at": obj.identity_alert_created_at.isoformat(),
                    "identity_resolution_due_at": obj.identity_resolution_due_at.isoformat(),
                    "source": "admin",
                },
            )


@admin.register(PatientContactHistory)
class PatientContactHistoryAdmin(admin.ModelAdmin):
    list_display = ("patient", "phone", "email", "reason", "changed_at", "changed_by_user")
    list_filter = ("reason",)
    search_fields = ("patient__last_name", "patient__first_name", "phone", "email")
    readonly_fields = ("id", "changed_at")
    date_hierarchy = "changed_at"
    raw_id_fields = ("patient", "changed_by_user")


@admin.register(ClinicSite)
class ClinicSiteAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(ConsultingRoom)
class ConsultingRoomAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "clinic_site", "is_active", "created_at")
    list_filter = ("is_active", "clinic_site")
    search_fields = ("code", "name")
    raw_id_fields = ("clinic_site",)


@admin.register(DailyQueue)
class DailyQueueAdmin(admin.ModelAdmin):
    list_display = ("queue_date", "clinic_site", "consulting_room", "shift_code", "status", "source", "created_at")
    list_filter = ("status", "source", "shift_code", "queue_date")
    search_fields = ("clinic_site__code", "consulting_room__code")
    raw_id_fields = ("clinic_site", "consulting_room", "created_by_user")
    date_hierarchy = "queue_date"


@admin.register(QueueEntry)
class QueueEntryAdmin(admin.ModelAdmin):
    list_display = (
        "position_no",
        "daily_queue",
        "patient",
        "entry_status",
        "visit_external_id",
        "appointment_time",
        "created_at",
    )
    list_filter = ("entry_status", "daily_queue__queue_date")
    search_fields = ("patient__last_name", "patient__first_name", "visit_external_id", "notes")
    raw_id_fields = ("daily_queue", "patient", "active_session", "created_by_user")
    date_hierarchy = "created_at"


@admin.register(TabletDevice)
class TabletDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "device_code", "is_active", "last_seen_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "device_code")


@admin.register(PatientFormSession)
class PatientFormSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "queue_entry", "tablet_device", "form_locale", "expires_at", "consumed_at", "created_at")
    list_filter = ("form_locale",)
    raw_id_fields = ("queue_entry", "tablet_device", "created_by_user")
    readonly_fields = ("id", "token_hash", "created_at")
    date_hierarchy = "created_at"


@admin.register(PatientImportBatch)
class PatientImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_file_name",
        "import_type",
        "status",
        "total_rows",
        "inserted_rows",
        "error_rows",
        "created_by_user",
        "created_at",
    )
    list_filter = ("status", "import_type", "source_system")
    raw_id_fields = ("created_by_user",)
    readonly_fields = ("id", "source_file_sha256", "created_at", "finished_at")
    date_hierarchy = "created_at"


@admin.register(PatientImportError)
class PatientImportErrorAdmin(admin.ModelAdmin):
    list_display = ("batch", "row_number", "error_code", "error_message", "created_at")
    list_filter = ("error_code",)
    search_fields = ("error_message", "error_code")
    raw_id_fields = ("batch",)
    readonly_fields = ("id", "created_at")
