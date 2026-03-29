from django.contrib import admin

from .models import PatientResultsOtpSession


@admin.register(PatientResultsOtpSession)
class PatientResultsOtpSessionAdmin(admin.ModelAdmin):
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
