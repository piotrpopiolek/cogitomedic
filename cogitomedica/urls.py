"""
URL configuration for cogitomedica project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from django.urls import include, path
from drf_spectacular.views import SpectacularRedocView, SpectacularSwaggerView

from cogitomedica.openapi_extension import cogito_openapi_schema_view
from apps.reception.paper_intake_admin_views import (
    paper_intake_admin_entry_view,
    paper_intake_admin_hub_view,
)
from apps.reception.views import reception_dashboard_view
from apps.intake.views import (
    intake_documents_list_view,
    intake_document_detail_view,
)

urlpatterns = [
    path("", include("apps.patient_results.urls", namespace="ergebnisse")),
    path("ergebnisse/", lambda request: redirect("/", permanent=True)),
    path("ergebnisse/otp/", lambda request: redirect("/otp/", permanent=True)),
    path(
        "ergebnisse/documents/", lambda request: redirect("/documents/", permanent=True)
    ),
    path(
        "admin/reception-dashboard/",
        reception_dashboard_view,
        name="admin_reception_dashboard",
    ),
    path(
        "admin/paper-intake/",
        paper_intake_admin_hub_view,
        name="admin_paper_intake_hub",
    ),
    path(
        "admin/paper-intake/<uuid:queue_entry_id>/",
        paper_intake_admin_entry_view,
        name="admin_paper_intake_entry",
    ),
    path(
        "admin/intake-documents/",
        intake_documents_list_view,
        name="admin_intake_documents",
    ),
    path(
        "admin/intake-documents/<uuid:version_id>/",
        intake_document_detail_view,
        name="admin_intake_document_detail",
    ),
    path("admin/", admin.site.urls),
    path("tablet/", include("cogitomedica.tablet_urls", namespace="tablet")),
    path("doctor/", include("cogitomedica.doctor_urls")),
    path(
        "api/schema/",
        staff_member_required(cogito_openapi_schema_view),
        name="api-schema",
    ),
    path("api/docs/", lambda request: redirect("api-swagger", permanent=False)),
    path(
        "api/docs/swagger/",
        staff_member_required(SpectacularSwaggerView.as_view(url_name="api-schema")),
        name="api-swagger",
    ),
    path(
        "api/docs/redoc/",
        staff_member_required(SpectacularRedocView.as_view(url_name="api-schema")),
        name="api-redoc",
    ),
    path("api/v1/", include("cogitomedica.api_urls")),
]
