from __future__ import annotations

from datetime import timedelta

from django import forms
from django.contrib import admin
from django.db.models import Count, Q
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import urlencode

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin

from apps.core.translation_service import db_gettext_lazy
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
class PatientAdmin(UnfoldModelAdmin):
    form = PatientAdminForm
    list_display = ("last_name", "first_name", "date_of_birth", "identity_status", "is_active", "created_at")
    list_filter = ("identity_status", "is_active", "external_source")
    search_fields = ("first_name", "last_name", "email", "phone", "doctolib_patient_id")
    readonly_fields = ("id", "created_at", "updated_at")
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # DOCTOR: see patients from assigned clinics OR patients in any queue assigned to this doctor
        if request.user.is_doctor and not request.user.is_superuser:
            qs = qs.filter(
                Q(clinic_sites__in=request.user.clinic_sites.all())
                | Q(queue_entries__daily_queue__assigned_doctor=request.user)
            ).distinct()
        return qs

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


def _set_created_by_user(request, obj, change: bool) -> None:
    """Set created_by_user to session user when adding and field is not set."""
    if change or not request.user.is_authenticated:
        return
    if getattr(obj, "created_by_user_id", None) is None and hasattr(obj, "created_by_user"):
        obj.created_by_user = request.user


def _initial_created_by_user(request, form, change: bool) -> None:
    """Pre-fill created_by_user with session user on add so the field is not required to be filled."""
    if change or not request.user.is_authenticated or "created_by_user" not in form.base_fields:
        return
    if form.base_fields["created_by_user"].initial is None:
        form.base_fields["created_by_user"].initial = request.user.pk


def _set_changed_by_user(request, obj) -> None:
    """Set changed_by_user to session user when not set."""
    if not request.user.is_authenticated or not hasattr(obj, "changed_by_user"):
        return
    if getattr(obj, "changed_by_user_id", None) is None:
        obj.changed_by_user = request.user


@admin.register(PatientContactHistory)
class PatientContactHistoryAdmin(UnfoldModelAdmin):
    list_display = ("patient", "phone", "email", "reason", "changed_at", "changed_by_user")
    list_filter = ("reason",)
    search_fields = ("patient__last_name", "patient__first_name", "phone", "email")
    readonly_fields = ("id", "changed_at")
    date_hierarchy = "changed_at"
    raw_id_fields = ("patient", "changed_by_user")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # DOCTOR: only see history for patients from assigned clinics
        if request.user.is_doctor and not request.user.is_superuser:
            qs = qs.filter(patient__clinic_sites__in=request.user.clinic_sites.all()).distinct()
        return qs

    def save_model(self, request, obj, form, change):
        _set_changed_by_user(request, obj)
        super().save_model(request, obj, form, change)


@admin.register(ClinicSite)
class ClinicSiteAdmin(UnfoldModelAdmin):
    list_display = ("code", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # DOCTOR: see clinics from profile OR clinics from queues assigned to this doctor
        if request.user.is_doctor and not request.user.is_superuser:
            qs = qs.filter(
                Q(id__in=request.user.clinic_sites.values_list("pk", flat=True))
                | Q(daily_queues__assigned_doctor=request.user)
            ).distinct()
        return qs


@admin.register(ConsultingRoom)
class ConsultingRoomAdmin(UnfoldModelAdmin):
    list_display = ("code", "name", "clinic_site", "is_active", "created_at")
    list_filter = ("is_active", "clinic_site")
    search_fields = ("code", "name")
    raw_id_fields = ("clinic_site",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # DOCTOR: see rooms from assigned clinics OR rooms from queues assigned to this doctor
        if request.user.is_doctor and not request.user.is_superuser:
            qs = qs.filter(
                Q(clinic_site_id__in=request.user.clinic_sites.values_list("pk", flat=True))
                | Q(daily_queues__assigned_doctor=request.user)
            ).distinct()
        return qs


@admin.register(DailyQueue)
class DailyQueueAdmin(UnfoldModelAdmin):
    list_display = (
        "queue_date",
        "clinic_site",
        "consulting_room",
        "assigned_doctor",
        "shift_code",
        "status",
        "source",
        "entries_count",
        "patients_count",
        "view_queue_entries",
        "view_day_patients",
        "created_at",
    )
    list_filter = ("status", "source", "shift_code", "queue_date")
    search_fields = ("clinic_site__code", "consulting_room__code", "assigned_doctor__username")
    raw_id_fields = ("clinic_site", "consulting_room", "created_by_user", "assigned_doctor")
    date_hierarchy = "queue_date"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "master-detail/",
                self.admin_site.admin_view(self.master_detail_view),
                name="reception_dailyqueue_master_detail",
            ),
        ]
        return custom_urls + urls

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            entries_count_annotated=Count("entries", distinct=True),
            patients_count_annotated=Count("entries__patient", distinct=True),
        )

    def master_detail_view(self, request: HttpRequest):
        queue_date = (request.GET.get("queue_date") or "").strip()
        queues_qs = DailyQueue.objects.select_related(
            "clinic_site",
            "consulting_room",
        ).prefetch_related("entries__patient")
        if queue_date:
            queues_qs = queues_qs.filter(queue_date=queue_date)
        queues = queues_qs.order_by("-queue_date", "clinic_site__name", "consulting_room__name")

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Kolejki dzienne - master/detail",
            "queues": queues,
            "queue_date": queue_date,
        }
        return TemplateResponse(
            request,
            "admin/reception/dailyqueue/master_detail.html",
            context,
        )

    @admin.display(description=db_gettext_lazy("administration.admin_col_wpisy", "Wpisy"), ordering="entries_count_annotated")
    def entries_count(self, obj):
        return getattr(obj, "entries_count_annotated", 0)

    @admin.display(description=db_gettext_lazy("administration.admin_col_pacjenci", "Pacjenci"), ordering="patients_count_annotated")
    def patients_count(self, obj):
        return getattr(obj, "patients_count_annotated", 0)

    @admin.display(description=db_gettext_lazy("administration.admin_col_widok_wpisow", "Widok wpisów"))
    def view_queue_entries(self, obj):
        url = f"{reverse('admin:reception_queueentry_changelist')}?{urlencode({'daily_queue__id__exact': str(obj.id)})}"
        return format_html('<a href="{}">Wpisy tej kolejki</a>', url)

    @admin.display(description=db_gettext_lazy("administration.admin_col_pacjenci_dnia", "Pacjenci dnia"))
    def view_day_patients(self, obj):
        params = {
            "daily_queue__queue_date__exact": obj.queue_date.isoformat(),
        }
        url = f"{reverse('admin:reception_queueentry_changelist')}?{urlencode(params)}"
        return format_html('<a href="{}">Pacjenci na ten dzień</a>', url)

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        _initial_created_by_user(request, form, bool(change))
        return form

    def save_model(self, request, obj, form, change):
        _set_created_by_user(request, obj, change)
        super().save_model(request, obj, form, change)


@admin.register(QueueEntry)
class QueueEntryAdmin(UnfoldModelAdmin):
    list_display = (
        "position_no",
        "daily_queue",
        "patient",
        "entry_status",
        "visit_external_id",
        "appointment_time",
        "created_at",
    )
    list_filter = ("entry_status", "daily_queue__queue_date", "daily_queue__clinic_site", "daily_queue__consulting_room")
    search_fields = ("patient__last_name", "patient__first_name", "visit_external_id", "notes")
    raw_id_fields = ("daily_queue", "patient", "active_session", "created_by_user")
    date_hierarchy = "created_at"

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        _initial_created_by_user(request, form, bool(change))
        return form

    def save_model(self, request, obj, form, change):
        _set_created_by_user(request, obj, change)
        super().save_model(request, obj, form, change)


@admin.register(TabletDevice)
class TabletDeviceAdmin(UnfoldModelAdmin):
    list_display = ("android_id", "is_active", "last_seen_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("android_id",)


@admin.register(PatientFormSession)
class PatientFormSessionAdmin(UnfoldModelAdmin):
    list_display = ("id", "queue_entry", "tablet_device", "form_locale", "expires_at", "consumed_at", "created_at")
    list_filter = ("form_locale",)
    raw_id_fields = ("queue_entry", "tablet_device", "created_by_user")
    readonly_fields = ("id", "created_at")
    date_hierarchy = "created_at"

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        _initial_created_by_user(request, form, bool(change))
        return form

    def save_model(self, request, obj, form, change):
        _set_created_by_user(request, obj, change)
        super().save_model(request, obj, form, change)


@admin.register(PatientImportBatch)
class PatientImportBatchAdmin(UnfoldModelAdmin):
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

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        _initial_created_by_user(request, form, bool(change))
        return form

    def save_model(self, request, obj, form, change):
        _set_created_by_user(request, obj, change)
        super().save_model(request, obj, form, change)


@admin.register(PatientImportError)
class PatientImportErrorAdmin(UnfoldModelAdmin):
    list_display = ("batch", "row_number", "error_code", "error_message", "created_at")
    list_filter = ("error_code",)
    search_fields = ("error_message", "error_code")
    raw_id_fields = ("batch",)
    readonly_fields = ("id", "created_at")
