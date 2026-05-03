from django.urls import path

from cogitomedica.doctor_views import (
    doctor_create_no_intake_view,
    doctor_document_detail_view,
    doctor_list_view,
    doctor_login_view,
    doctor_logout_view,
    doctor_open_by_queue_view,
)

urlpatterns = [
    path("login/", doctor_login_view, name="doctor-login"),
    path("logout/", doctor_logout_view, name="doctor-logout"),
    path("", doctor_list_view, name="doctor-list"),
    path(
        "open/<uuid:queue_entry_id>/",
        doctor_open_by_queue_view,
        name="doctor-open-by-queue",
    ),
    path(
        "open/<uuid:queue_entry_id>/create-no-intake/",
        doctor_create_no_intake_view,
        name="doctor-create-no-intake",
    ),
    path(
        "<uuid:medical_document_id>/",
        doctor_document_detail_view,
        name="doctor-document-detail",
    ),
]
