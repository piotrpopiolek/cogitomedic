from django.contrib.admin.views.decorators import staff_member_required
from django.template.response import TemplateResponse
from django.contrib import admin

from apps.core.api_utils import get_scoped_clinic_site_ids
from apps.core.staff_custom_admin import ensure_reception_admin_manager_staff
from apps.core.translation_service import get_admin_translation
from apps.reception.hidrive_dashboard import (
    MISSING_HIDRIVE_RESULTS_DISPLAY_LIMIT,
    build_missing_hidrive_results_report,
)
from apps.reception.models import PatientImportBatch
from apps.outbox.models import OutboxEvent, OutboxStatus


@staff_member_required
def reception_dashboard_view(request):
    forbidden = ensure_reception_admin_manager_staff(request)
    if forbidden is not None:
        return forbidden

    recent_imports = PatientImportBatch.objects.order_by("-created_at")[:10]
    failed_outbox_qs = OutboxEvent.objects.select_related(
        "medical_document_version__medical_document__queue_entry__daily_queue"
    ).filter(status__in=[OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER])
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    if scoped_clinic_site_ids is not None:
        failed_outbox_qs = failed_outbox_qs.filter(
            medical_document_version__medical_document__queue_entry__daily_queue__clinic_site_id__in=scoped_clinic_site_ids
        )
    failed_outbox = failed_outbox_qs.order_by("-created_at")[:20]

    hidrive_report = build_missing_hidrive_results_report(request.user)
    missing_hidrive_results = hidrive_report.rows[
        :MISSING_HIDRIVE_RESULTS_DISPLAY_LIMIT
    ]

    context = {
        **admin.site.each_context(request),
        "title": get_admin_translation(
            request,
            "administration.reception_dashboard_title",
            "Reception operations dashboard",
        ),
        "recent_imports": recent_imports,
        "failed_outbox": failed_outbox,
        "missing_hidrive_results": missing_hidrive_results,
        "missing_hidrive_meta": hidrive_report,
        "missing_hidrive_total": hidrive_report.total_row_count,
    }
    return TemplateResponse(request, "admin/reception/dashboard.html", context)
