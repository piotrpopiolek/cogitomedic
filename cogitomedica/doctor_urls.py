from django.urls import path

from cogitomedica.doctor_views import (
    doctor_document_detail_view,
    doctor_list_view,
    doctor_login_view,
    doctor_logout_view,
)

urlpatterns = [
    path("login/", doctor_login_view, name="doctor-login"),
    path("logout/", doctor_logout_view, name="doctor-logout"),
    path("", doctor_list_view, name="doctor-list"),
    path("<uuid:medical_document_id>/", doctor_document_detail_view, name="doctor-document-detail"),
]
