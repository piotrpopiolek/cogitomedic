from __future__ import annotations

import uuid

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode

try:
    from unfold.widgets import UnfoldAdminSelectWidget
except ImportError:
    UnfoldAdminSelectWidget = forms.Select

from apps.core.admin_list_page_size import CogitomedicaModelAdmin

from apps.core.exceptions import DomainError
from apps.core.translation_service import (
    db_gettext_lazy,
    format_administration_message,
    resolve_other_message,
)
from apps.outbox.result_available_sms import enqueue_result_available_sms_for_patient
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientFormSession,
    PatientImportBatch,
    PatientImportError,
    QueueEntry,
    TabletDevice,
)
from apps.reception.process_types import QUEUE_ENTRY_PROCESS_TYPE_UNIQUE
from apps.reception.services import (
    create_queue_entry,
    queue_entry_process_type_exists_error,
    staff_user_may_set_ausfallhonorar,
    update_queue_entry,
)
from apps.reception.xlsx_import import enqueue_patient_xlsx_import
from apps.users.models import StaffUser, StaffUserPreferredLocale


def _user_may_send_result_available_sms(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            getattr(user, "is_superuser", False)
            or getattr(user, "is_admin_role", False)
            or getattr(user, "is_manager", False)
            or getattr(user, "is_reception", False)
        )
    )


class PatientXlsxImportAdminForm(forms.Form):
    file = forms.FileField(
        label="Plik XLSX",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "class": "hidden",
            }
        ),
    )
    next = forms.CharField(widget=forms.HiddenInput(), required=False)


@admin.register(Patient)
class PatientAdmin(CogitomedicaModelAdmin):
    change_form_template = "admin/reception/patient/change_form.html"
    actions = ("send_result_available_sms",)
    list_display = (
        "last_name",
        "first_name",
        "date_of_birth",
        "phone",
        "postal_code",
        "created_at",
        "is_active",
    )
    list_display_links = ("last_name",)
    list_filter = ("is_active",)
    ordering = ["-created_at"]
    search_fields = ("first_name", "last_name", "email", "phone")
    exclude = ("doctolib_patient_id",)
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

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/send-result-available-sms/",
                self.admin_site.admin_view(self.send_result_available_sms_view),
                name="reception_patient_send_result_available_sms",
            ),
        ]
        return custom + urls

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if _user_may_send_result_available_sms(request.user):
            extra_context["send_result_available_sms_url"] = reverse(
                "admin:reception_patient_send_result_available_sms",
                args=[object_id],
            )
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    def send_result_available_sms_view(
        self, request: HttpRequest, object_id: str
    ) -> HttpResponse:
        if request.method != "POST":
            return redirect(reverse("admin:reception_patient_change", args=[object_id]))
        if not _user_may_send_result_available_sms(request.user):
            raise PermissionDenied
        patient = self.get_object(request, object_id)
        if patient is None:
            raise PermissionDenied
        try:
            enqueue_result_available_sms_for_patient(
                patient_id=patient.id,
                actor_user_id=request.user.id,
            )
            self.message_user(
                request,
                format_administration_message(
                    "administration.admin_send_result_sms_detail_ok",
                    "“Result available” SMS was queued.",
                    request=request,
                ),
                level=messages.SUCCESS,
            )
        except DomainError as exc:
            self.message_user(
                request,
                resolve_other_message(
                    request,
                    exc.api_message_key or "",
                    str(exc),
                    **(exc.api_message_params or {}),
                ),
                level=messages.ERROR,
            )
        return redirect(reverse("admin:reception_patient_change", args=[object_id]))

    @admin.action(
        description=db_gettext_lazy(
            "administration.admin_action_send_result_available_sms",
            "SMS: Ergebnis verfügbar",
        )
    )
    def send_result_available_sms(self, request, queryset):
        if not _user_may_send_result_available_sms(request.user):
            self.message_user(
                request,
                format_administration_message(
                    "administration.admin_send_result_sms_permission_denied",
                    "You do not have permission to send “result available” SMS "
                    "(Reception/Manager/Admin).",
                    request=request,
                ),
                level=messages.ERROR,
            )
            return
        ok = 0
        failed = 0
        last_error = ""
        for patient in queryset:
            try:
                enqueue_result_available_sms_for_patient(
                    patient_id=patient.id,
                    actor_user_id=request.user.id,
                )
                ok += 1
            except DomainError as exc:
                failed += 1
                last_error = resolve_other_message(
                    request,
                    exc.api_message_key or "",
                    str(exc),
                    **(exc.api_message_params or {}),
                )
        summary = format_administration_message(
            "administration.admin_send_result_sms_result",
            "“Result available” SMS: {ok} queued; {failed} failed.",
            request=request,
            ok=ok,
            failed=failed,
        )
        if failed and last_error:
            summary = f"{summary} {last_error}"
        self.message_user(
            request,
            summary,
            level=messages.WARNING if failed else messages.SUCCESS,
        )


def _set_created_by_user(request, obj, change: bool) -> None:
    """Set created_by_user to session user when adding and field is not set."""
    if change or not request.user.is_authenticated:
        return
    if getattr(obj, "created_by_user_id", None) is None and hasattr(
        obj, "created_by_user"
    ):
        obj.created_by_user = request.user


def _initial_created_by_user(request, form, change: bool) -> None:
    """Pre-fill created_by_user with session user on add so the field is not required to be filled."""
    if (
        change
        or not request.user.is_authenticated
        or "created_by_user" not in form.base_fields
    ):
        return
    if form.base_fields["created_by_user"].initial is None:
        form.base_fields["created_by_user"].initial = request.user.pk


def _admin_resolve_dailyqueue_clinic_site_id(
    request: HttpRequest, obj: DailyQueue | None
) -> uuid.UUID | None:
    """Prefer POSTed clinic_site (user may switch site on change); else persisted obj."""
    if request.method == "POST":
        raw = (request.POST.get("clinic_site") or "").strip()
        if raw:
            try:
                return uuid.UUID(raw)
            except (ValueError, TypeError):
                return None
    if obj is not None and getattr(obj, "clinic_site_id", None):
        return obj.clinic_site_id
    return None


def _consulting_rooms_for_clinic_site_queryset(
    clinic_site_id: uuid.UUID,
    *,
    current_room_id: uuid.UUID | None,
) -> QuerySet[ConsultingRoom]:
    qs = ConsultingRoom.objects.filter(clinic_site_id=clinic_site_id)
    active = qs.filter(is_active=True)
    if current_room_id and not active.filter(pk=current_room_id).exists():
        return qs.filter(Q(is_active=True) | Q(pk=current_room_id)).order_by(
            "code", "name"
        )
    return active.order_by("code", "name")


@admin.register(ClinicSite)
class ClinicSiteAdmin(CogitomedicaModelAdmin):
    list_display = (
        "code",
        "name",
        "pdf_import_default_consulting_room",
        "pdf_import_shift_code",
        "created_at",
        "is_active",
    )
    list_display_links = ("code",)
    list_filter = ("is_active",)
    ordering = ["-created_at"]
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
class ConsultingRoomAdmin(CogitomedicaModelAdmin):
    list_display = ("code", "name", "clinic_site", "created_at", "is_active")
    list_filter = ("is_active", "clinic_site")
    ordering = ["-created_at"]
    search_fields = ("code", "name")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # DOCTOR: see rooms from assigned clinics OR rooms from queues assigned to this doctor
        if request.user.is_doctor and not request.user.is_superuser:
            qs = qs.filter(
                Q(
                    clinic_site_id__in=request.user.clinic_sites.values_list(
                        "pk", flat=True
                    )
                )
                | Q(daily_queues__assigned_doctor=request.user)
            ).distinct()
        return qs


@admin.register(DailyQueue)
class DailyQueueAdmin(CogitomedicaModelAdmin):
    change_list_template = "admin/reception/dailyqueue/change_list.html"
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
    list_display_links = ("queue_date",)
    list_filter = ("status", "source", "shift_code", "queue_date")
    ordering = ["-created_at"]
    search_fields = (
        "clinic_site__code",
        "consulting_room__code",
        "assigned_doctor__username",
    )
    raw_id_fields = ("created_by_user",)
    # consulting_room: nie autocomplete — queryset z formfield_for_foreignkey jest wtedy respektowany (placówka → gabinety).
    autocomplete_fields = ("clinic_site", "assigned_doctor")
    date_hierarchy = "queue_date"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "master-detail/",
                self.admin_site.admin_view(self.master_detail_view),
                name="reception_dailyqueue_master_detail",
            ),
            path(
                "import-xlsx/",
                self.admin_site.admin_view(self.import_xlsx_view),
                name="reception_dailyqueue_import_xlsx",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_xlsx_url"] = "{}?{}".format(
            reverse("admin:reception_dailyqueue_import_xlsx"),
            urlencode({"next": request.get_full_path()}),
        )
        return super().changelist_view(request, extra_context=extra_context)

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
        queues = queues_qs.order_by(
            "-queue_date", "clinic_site__name", "consulting_room__name"
        )

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

    def import_xlsx_view(self, request: HttpRequest):
        if not (
            request.user.is_authenticated
            and (
                request.user.is_admin_role
                or getattr(request.user, "is_manager", False)
                or request.user.is_reception
                or request.user.is_superuser
            )
        ):
            raise PermissionDenied

        next_url = (
            request.GET.get("next")
            or request.POST.get("next")
            or reverse("admin:reception_dailyqueue_changelist")
        )
        if request.method == "POST":
            form = PatientXlsxImportAdminForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    batch = enqueue_patient_xlsx_import(
                        uploaded_file=form.cleaned_data["file"],
                        created_by_user=request.user,
                    )
                    batch_url = reverse(
                        "admin:reception_patientimportbatch_change", args=[batch.id]
                    )
                    self.message_user(
                        request,
                        format_html(
                            'Import XLSX został zakolejkowany. <a href="{}">Zobacz batch</a>.',
                            batch_url,
                        ),
                        level=messages.SUCCESS,
                    )
                    return redirect(
                        form.cleaned_data["next"]
                        or reverse("admin:reception_dailyqueue_changelist")
                    )
                except Exception as e:
                    self.message_user(
                        request,
                        f"Błąd importu: {e}",
                        level=messages.ERROR,
                    )
        else:
            form = PatientXlsxImportAdminForm(initial={"next": next_url})

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Import pacjentów z pliku XLSX",
            "form": form,
            "next_url": next_url,
        }
        return TemplateResponse(
            request,
            "admin/reception/dailyqueue/import_xlsx.html",
            context,
        )

    @admin.display(
        description=db_gettext_lazy("administration.admin_col_wpisy", "Einträge"),
        ordering="entries_count_annotated",
    )
    def entries_count(self, obj):
        return getattr(obj, "entries_count_annotated", 0)

    @admin.display(
        description=db_gettext_lazy("administration.admin_col_pacjenci", "Patienten"),
        ordering="patients_count_annotated",
    )
    def patients_count(self, obj):
        return getattr(obj, "patients_count_annotated", 0)

    @admin.display(
        description=db_gettext_lazy(
            "administration.admin_col_widok_wpisow", "Einträge anzeigen"
        )
    )
    def view_queue_entries(self, obj):
        url = f"{reverse('admin:reception_queueentry_changelist')}?{urlencode({'daily_queue__id__exact': str(obj.id)})}"
        label = str(
            db_gettext_lazy(
                "administration.admin_col_widok_wpisow", "Einträge anzeigen"
            )
        )
        return format_html('<a href="{}">{}</a>', url, label)

    @admin.display(
        description=db_gettext_lazy(
            "administration.admin_col_pacjenci_dnia", "Patienten des Tages"
        )
    )
    def view_day_patients(self, obj):
        params = {
            "daily_queue__queue_date__exact": obj.queue_date.isoformat(),
        }
        url = f"{reverse('admin:reception_queueentry_changelist')}?{urlencode(params)}"
        label = str(
            db_gettext_lazy(
                "administration.admin_col_pacjenci_dnia", "Patienten des Tages"
            )
        )
        return format_html('<a href="{}">{}</a>', url, label)

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        _initial_created_by_user(request, form, bool(change))
        return form

    def save_model(self, request, obj, form, change):
        _set_created_by_user(request, obj, change)
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "consulting_room":
            clinic_site_id = _admin_resolve_dailyqueue_clinic_site_id(
                request, kwargs.get("obj")
            )
            if clinic_site_id is not None:
                kwargs["queryset"] = _consulting_rooms_for_clinic_site_queryset(
                    clinic_site_id,
                    current_room_id=getattr(
                        kwargs.get("obj"), "consulting_room_id", None
                    ),
                )
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "assigned_doctor":
            formfield.queryset = StaffUser.objects.filter(
                groups__name="Doctor"
            ).distinct()
        return formfield


@admin.register(QueueEntry)
class QueueEntryAdmin(CogitomedicaModelAdmin):
    list_display = (
        "position_no",
        "daily_queue",
        "patient",
        "process_type",
        "entry_status",
        "ausfallhonorar",
        "visit_external_id",
        "appointment_time",
        "created_at",
    )
    list_display_links = ("position_no",)
    list_filter = (
        "ausfallhonorar",
        "process_type",
        "entry_status",
        "daily_queue__queue_date",
        "daily_queue__clinic_site",
        "daily_queue__consulting_room",
    )
    ordering = ["-created_at"]
    search_fields = (
        "patient__last_name",
        "patient__first_name",
        "visit_external_id",
        "notes",
    )
    raw_id_fields = ("active_session", "created_by_user")
    readonly_fields = ("ausfallhonorar_set_at", "ausfallhonorar_set_by")
    exclude = ("visit_external_id",)
    date_hierarchy = "created_at"
    actions = ("mark_ausfallhonorar", "clear_ausfallhonorar")

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        _initial_created_by_user(request, form, bool(change))
        return form

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if "visit_external_id" not in exclude:
            exclude.append("visit_external_id")
        if obj is None:
            exclude.append("position_no")
        return exclude

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not staff_user_may_set_ausfallhonorar(request.user):
            if "ausfallhonorar" not in readonly:
                readonly.append("ausfallhonorar")
        if obj is not None and "process_type" not in readonly:
            readonly.append("process_type")
        return readonly

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not staff_user_may_set_ausfallhonorar(request.user):
            actions.pop("mark_ausfallhonorar", None)
            actions.pop("clear_ausfallhonorar", None)
        return actions

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except DomainError:
            # Flag write failed after message_user ERROR; skip admin "saved successfully".
            return redirect(request.get_full_path())

    def _report_domain_error(self, request, exc: DomainError) -> None:
        self.message_user(
            request,
            resolve_other_message(
                request,
                exc.api_message_key or "",
                str(exc),
                **(exc.api_message_params or {}),
            ),
            level=messages.ERROR,
        )

    def save_model(self, request, obj, form, change):
        _set_created_by_user(request, obj, change)
        # Intent is the bound form vs its initial snapshot, not the live DB row.
        # A stale unchecked box must not clear a flag set after the form was opened.
        flag_changed = "ausfallhonorar" in getattr(form, "changed_data", [])
        desired_flag = (
            bool(form.cleaned_data.get("ausfallhonorar")) if flag_changed else None
        )
        with transaction.atomic():
            if not change:
                obj.ausfallhonorar = False
                obj.ausfallhonorar_set_at = None
                obj.ausfallhonorar_set_by = None
                try:
                    created = create_queue_entry(
                        daily_queue_id=obj.daily_queue_id,
                        patient_id=obj.patient_id,
                        created_by_user_id=obj.created_by_user_id,
                        appointment_time=obj.appointment_time,
                        notes=obj.notes,
                        process_type=obj.process_type,
                    )
                except DomainError as exc:
                    self._report_domain_error(request, exc)
                    raise
                obj.pk = created.pk
                obj.id = created.id
                obj.position_no = created.position_no
                obj.entry_status = created.entry_status
                obj.process_type = created.process_type
                obj.created_at = created.created_at
                obj.updated_at = created.updated_at
                if flag_changed and desired_flag:
                    self._apply_ausfallhonorar(request, obj.id, True)
                return
            stored = QueueEntry.objects.select_for_update().get(pk=obj.pk)
            obj.ausfallhonorar = stored.ausfallhonorar
            obj.ausfallhonorar_set_at = stored.ausfallhonorar_set_at
            obj.ausfallhonorar_set_by_id = stored.ausfallhonorar_set_by_id
            status_changed = "entry_status" in getattr(form, "changed_data", [])
            try:
                if status_changed:
                    try:
                        updated = update_queue_entry(
                            obj.pk,
                            entry_status=obj.entry_status,
                            actor_user_id=request.user.id,
                        )
                    except DomainError as exc:
                        self._report_domain_error(request, exc)
                        raise
                    obj.entry_status = updated.entry_status
                    obj.doctor_list_sort_at = updated.doctor_list_sort_at
                super().save_model(request, obj, form, change)
            except IntegrityError as exc:
                if QUEUE_ENTRY_PROCESS_TYPE_UNIQUE in str(exc):
                    err = queue_entry_process_type_exists_error(obj.process_type)
                    self._report_domain_error(request, err)
                    raise err from exc
                raise
            if flag_changed:
                self._apply_ausfallhonorar(request, obj.id, bool(desired_flag))

    def _apply_ausfallhonorar(self, request, queue_entry_id, flagged: bool) -> None:
        try:
            update_queue_entry(
                queue_entry_id,
                ausfallhonorar=flagged,
                actor_user_id=request.user.id,
            )
        except DomainError as exc:
            self._report_domain_error(request, exc)
            raise

    def _bulk_set_ausfallhonorar(self, request, queryset, *, flagged: bool) -> None:
        if not staff_user_may_set_ausfallhonorar(request.user):
            self.message_user(
                request,
                format_administration_message(
                    "administration.admin_ausfallhonorar_permission_denied",
                    "You do not have permission to set Ausfallhonorar "
                    "(Reception, Manager, or Admin).",
                    request=request,
                ),
                level=messages.ERROR,
            )
            return
        ok = 0
        failed = 0
        last_error = ""
        for entry in queryset:
            try:
                update_queue_entry(
                    entry.id,
                    ausfallhonorar=flagged,
                    actor_user_id=request.user.id,
                )
                ok += 1
            except DomainError as exc:
                failed += 1
                last_error = resolve_other_message(
                    request,
                    exc.api_message_key or "",
                    str(exc),
                    **(exc.api_message_params or {}),
                )
        result_key = (
            "administration.admin_ausfallhonorar_marked"
            if flagged
            else "administration.admin_ausfallhonorar_cleared"
        )
        default = (
            "Ausfallhonorar marked: {ok}."
            if flagged
            else "Ausfallhonorar cleared: {ok}."
        )
        summary = format_administration_message(
            result_key,
            default,
            request=request,
            ok=ok,
        )
        if failed and last_error:
            summary = f"{summary} {last_error}"
        self.message_user(
            request,
            summary,
            level=messages.WARNING if failed else messages.SUCCESS,
        )

    @admin.action(
        description=db_gettext_lazy(
            "administration.admin_action_mark_ausfallhonorar",
            "Mark Ausfallhonorar",
        )
    )
    def mark_ausfallhonorar(self, request, queryset):
        self._bulk_set_ausfallhonorar(request, queryset, flagged=True)

    @admin.action(
        description=db_gettext_lazy(
            "administration.admin_action_clear_ausfallhonorar",
            "Clear Ausfallhonorar",
        )
    )
    def clear_ausfallhonorar(self, request, queryset):
        self._bulk_set_ausfallhonorar(request, queryset, flagged=False)


@admin.register(TabletDevice)
class TabletDeviceAdmin(CogitomedicaModelAdmin):
    list_display = (
        "android_id",
        "clinic_site",
        "last_seen_at",
        "created_at",
        "is_active",
    )
    list_display_links = ("android_id",)
    list_filter = ("is_active", "clinic_site")
    ordering = ["-created_at"]
    search_fields = ("android_id",)


@admin.register(PatientFormSession)
class PatientFormSessionAdmin(CogitomedicaModelAdmin):
    list_display = (
        "id",
        "queue_entry",
        "tablet_device",
        "form_locale",
        "expires_at",
        "consumed_at",
        "created_at",
    )
    list_display_links = ("id",)
    list_filter = ("form_locale",)
    ordering = ["-created_at"]
    raw_id_fields = ("created_by_user",)
    readonly_fields = ("id", "created_at")
    date_hierarchy = "created_at"

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if "form_locale" in form.base_fields:
            base_field = form.base_fields["form_locale"]
            form.base_fields["form_locale"] = forms.ChoiceField(
                choices=StaffUserPreferredLocale.choices,
                required=base_field.required,
                label=base_field.label,
                help_text=base_field.help_text,
                initial=base_field.initial,
                widget=UnfoldAdminSelectWidget,
            )
        _initial_created_by_user(request, form, bool(change))
        return form

    def save_model(self, request, obj, form, change):
        _set_created_by_user(request, obj, change)
        super().save_model(request, obj, form, change)


@admin.register(PatientImportBatch)
class PatientImportBatchAdmin(CogitomedicaModelAdmin):
    list_display = (
        "source_file_name",
        "import_type",
        "status",
        "total_rows",
        "inserted_rows",
        "matched_rows",
        "skipped_already_present_count",
        "error_rows",
        "created_by_user",
        "created_at",
    )
    list_display_links = ("source_file_name",)
    list_filter = ("status", "import_type", "source_system")
    ordering = ["-created_at"]
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
class PatientImportErrorAdmin(CogitomedicaModelAdmin):
    list_display = ("batch", "row_number", "error_code", "error_message", "created_at")
    list_display_links = ("batch",)
    list_filter = ("error_code",)
    ordering = ["-created_at"]
    search_fields = ("error_message", "error_code")
    raw_id_fields = ("batch",)
    readonly_fields = ("id", "created_at")
