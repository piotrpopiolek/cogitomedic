from django.apps import AppConfig

from apps.core.translation_service import db_gettext_lazy


class PatientResultsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.patient_results"
    verbose_name = db_gettext_lazy(
        "administration.app_patient_results", "Patient results (portal)"
    )
