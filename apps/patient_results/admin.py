from django.contrib import admin

from apps.core.admin_list_page_size import CogitomedicaModelAdmin

from .models import PatientResultsOtpSession


@admin.register(PatientResultsOtpSession)
class PatientResultsOtpSessionAdmin(CogitomedicaModelAdmin):
    list_display = (
        "id",
        "patient",
        "phone",
        "expires_at",
        "verified_at",
        "verify_attempt_count",
        "created_at",
    )
    list_display_links = ("id",)
    list_filter = ("verified_at",)
    ordering = ["-created_at"]
    search_fields = ("phone", "patient__first_name", "patient__last_name")
    raw_id_fields = ("patient",)
    readonly_fields = ("id", "otp_code_hash", "created_at")
