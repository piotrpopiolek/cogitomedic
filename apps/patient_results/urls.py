"""URL configuration for ergebnisse portal."""

from django.urls import path

from apps.patient_results.views import (
    ergebnisse_documents_view,
    ergebnisse_login_view,
    ergebnisse_otp_view,
)

app_name = "ergebnisse"

urlpatterns = [
    path("", ergebnisse_login_view, name="login"),
    path("otp/", ergebnisse_otp_view, name="otp"),
    path("documents/", ergebnisse_documents_view, name="documents"),
]
