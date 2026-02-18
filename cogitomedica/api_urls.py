from __future__ import annotations

from django.urls import path

from apps.intake.api_views import intake_form_anamnesis_view, intake_form_submit_view
from apps.medical.api_views import (
    doctor_text_template_detail_view,
    doctor_text_templates_view,
    medical_document_draft_view,
    medical_document_publish_view,
    medical_documents_view,
)
from apps.outbox.api_views import (
    operations_outbox_process_view,
    operations_retention_run_view,
    outbox_event_retry_view,
    outbox_events_view,
)
from apps.operations.api_views import observability_health_view, observability_metrics_view
from apps.reception.api_views import queue_entry_sessions_view
from apps.users.api_views import auth_login_view, auth_logout_view, auth_me_view


urlpatterns = [
    path(
        "observability/health",
        observability_health_view,
        name="observability-health",
    ),
    path(
        "observability/metrics",
        observability_metrics_view,
        name="observability-metrics",
    ),
    path(
        "auth/login",
        auth_login_view,
        name="auth-login",
    ),
    path(
        "auth/logout",
        auth_logout_view,
        name="auth-logout",
    ),
    path(
        "auth/me",
        auth_me_view,
        name="auth-me",
    ),
    path(
        "doctor-text-templates",
        doctor_text_templates_view,
        name="doctor-text-templates",
    ),
    path(
        "doctor-text-templates/<uuid:template_id>",
        doctor_text_template_detail_view,
        name="doctor-text-template-detail",
    ),
    path(
        "outbox-events",
        outbox_events_view,
        name="outbox-events",
    ),
    path(
        "outbox-events/<uuid:outbox_event_id>/retry",
        outbox_event_retry_view,
        name="outbox-event-retry",
    ),
    path(
        "operations/outbox/process",
        operations_outbox_process_view,
        name="operations-outbox-process",
    ),
    path(
        "operations/retention/run",
        operations_retention_run_view,
        name="operations-retention-run",
    ),
    path(
        "medical-documents",
        medical_documents_view,
        name="medical-documents",
    ),
    path(
        "medical-documents/<uuid:medical_document_id>/draft",
        medical_document_draft_view,
        name="medical-document-draft",
    ),
    path(
        "medical-documents/<uuid:medical_document_id>/publish",
        medical_document_publish_view,
        name="medical-document-publish",
    ),
    path(
        "queue-entries/<uuid:queue_entry_id>/sessions",
        queue_entry_sessions_view,
        name="queue-entry-sessions",
    ),
    path(
        "intake-forms/<uuid:intake_form_id>/anamnesis",
        intake_form_anamnesis_view,
        name="intake-form-anamnesis",
    ),
    path(
        "intake-forms/<uuid:intake_form_id>/submit",
        intake_form_submit_view,
        name="intake-form-submit",
    ),
]
