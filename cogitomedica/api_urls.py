from __future__ import annotations

from django.urls import path

from apps.intake.api_views import intake_form_anamnesis_view, intake_form_submit_view
from apps.reception.api_views import queue_entry_sessions_view


urlpatterns = [
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
