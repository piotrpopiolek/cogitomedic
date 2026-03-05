from django.contrib.admin.views.decorators import staff_member_required
from django.template.response import TemplateResponse
from django.contrib import admin
from apps.reception.models import PatientImportBatch
from apps.outbox.models import OutboxEvent, OutboxStatus

@staff_member_required
def reception_dashboard_view(request):
    recent_imports = PatientImportBatch.objects.order_by("-created_at")[:10]
    failed_outbox = OutboxEvent.objects.filter(
        status__in=[OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER]
    ).order_by("-created_at")[:20]
    
    context = {
        **admin.site.each_context(request),
        "title": "Dashboard operacyjny recepcji",
        "recent_imports": recent_imports,
        "failed_outbox": failed_outbox,
    }
    return TemplateResponse(request, "admin/reception/dashboard.html", context)
