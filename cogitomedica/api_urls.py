from __future__ import annotations

from django.urls import path

from apps.intake.api_views import intake_form_anamnesis_view, intake_form_submit_view
from apps.medical.api_views import medical_document_draft_view, medical_document_publish_view, medical_documents_view
from apps.reception.api_views import queue_entry_sessions_view


urlpatterns = [
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
