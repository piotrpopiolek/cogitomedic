from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PatientResultsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.patient_results"
    verbose_name = _("Patient results (portal wyniki)")
