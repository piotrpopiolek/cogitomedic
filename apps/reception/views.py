from django.contrib.admin.views.decorators import staff_member_required
from django.template.response import TemplateResponse
from django.contrib import admin
from apps.core.api_utils import get_scoped_clinic_site_ids
from apps.reception.models import PatientImportBatch
from apps.outbox.models import OutboxEvent, OutboxStatus

@staff_member_required
def reception_dashboard_view(request):
    recent_imports = PatientImportBatch.objects.order_by("-created_at")[:10]
    failed_outbox_qs = OutboxEvent.objects.select_related(
        "medical_document_version__medical_document__queue_entry__daily_queue"
    ).filter(
        status__in=[OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER]
    )
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    if scoped_clinic_site_ids is not None:
        failed_outbox_qs = failed_outbox_qs.filter(
            medical_document_version__medical_document__queue_entry__daily_queue__clinic_site_id__in=scoped_clinic_site_ids
        )
    failed_outbox = failed_outbox_qs.order_by("-created_at")[:20]
    
    context = {
        **admin.site.each_context(request),
        "title": "Dashboard operacyjny recepcji",
        "recent_imports": recent_imports,
        "failed_outbox": failed_outbox,
    }
    return TemplateResponse(request, "admin/reception/dashboard.html", context)
