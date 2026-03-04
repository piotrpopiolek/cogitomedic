# Generated manually – seed translations for all fields and login/logout screens.

import os
from django.db import migrations

def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    # The collected fields from patch_models.py
    fields = ['accepted', 'content_pl', 'title_de', 'is_html_allowed', 'summary_favorites', 'password', 'raw_row', 'is_staff', 'city', 'sms_sent', 'source_file_sha256', 'shift_code', 'first_name', 'hidrive_sent', 'key', 'signature_sha256', 'is_global', 'country_code', 'error_message', 'is_active', 'notes', 'processed_at', 'version_no', 'last_published_at', 'payload', 'published_at', 'username', 'inserted_rows', 'value', 'error_code', 'procedure_code', 'template_locale', 'expires_at', 'version', 'option_text_en', 'form_locale', 'status', 'event_type', 'last_seen_at', 'source', 'question_text_en', 'content_en', 'medical_payload_schema_version', 'pdf_local_path', 'source_file_name', 'sms_sent_at', 'title_pl', 'event_time', 'description', 'reason', 'external_source_id', 'row_number', 'identity_alert_created_at', 'phone', 'phone_number', 'question_text_de', 'daily_queue', 'max_retries', 'body_map_data', 'selected_option_codes', 'body_map_schema_version', 'appointment_time', 'street', 'metadata', 'display_order', 'date_joined', 'publish_locale', 'hidrive_path', 'snapshot_payload', 'diagnosis_code', 'current_version_no', 'payload_schema_version', 'name', 'visit_external_id', 'email', 'language_code', 'title_en', 'anamnesis_schema_version', 'is_required', 'locked_at', 'date_of_birth', 'submitted_at', 'retry_count', 'option_text_de', 'pdf_checksum_sha256', 'identity_resolution_due_at', 'accepted_at', 'clinic_site', 'lesion_group_favorites', 'consumed_at', 'effective_to', 'allowed_placeholders', 'changed_at', 'local_pdf_deleted_at', 'anamnesis_payload', 'queue_date', 'android_id', 'preferred_locale', 'signature_file_path', 'last_name', 'available_at', 'template_body', 'aggregate_type', 'postal_code', 'medical_payload', 'effective_from', 'patient', 'selected_option_code', 'total_rows', 'code', 'finished_at', 'doctolib_patient_id', 'error_rows', 'content_de', 'position_no', 'question_text_pl', 'option_text_pl', 'hidrive_sent_at']

    login_keys = {
        "login_welcome": {"de": "Willkommen zurück bei", "en": "Welcome back to", "pl": "Witaj z powrotem w"},
        "login_btn": {"de": "Anmelden", "en": "Log in", "pl": "Zaloguj się"},
        "login_forgot_password": {"de": "Passwort oder Benutzername vergessen?", "en": "Forgotten your password or username?", "pl": "Nie pamiętasz hasła lub nazwy użytkownika?"},
        "logout_title": {"de": "Sie wurden erfolgreich von der Administration abgemeldet", "en": "You have been successfully logged out from the administration", "pl": "Zostałeś pomyślnie wylogowany z panelu administracyjnego"},
        "logout_subtitle": {"de": "Vielen Dank, dass Sie heute Zeit mit der Website verbracht haben.", "en": "Thanks for spending some quality time with the web site today.", "pl": "Dzięki za spędzenie cennego czasu na stronie."},
        "logout_btn": {"de": "Erneut anmelden", "en": "Log in again", "pl": "Zaloguj się ponownie"},
        "return_to_site": {"de": "Zurück zur Website", "en": "Return to site", "pl": "Wróć do strony głównej"},
    }

    # Add login keys
    for short_key, mapping in login_keys.items():
        full_key = f"administration.{short_key}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "administration",
                "description": "Login/logout UI labels",
                "is_html_allowed": False,
                "allowed_placeholders": [],
                "status": "ACTIVE",
            },
        )
        for lang, text in mapping.items():
            TranslationValue.objects.get_or_create(
                translation_key=key,
                language_code=lang,
                defaults={"value": text},
            )

    # Add field keys
    for field_name in fields:
        full_key = f"administration.field_{field_name}"
        human_readable = field_name.replace('_', ' ').capitalize()
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "administration",
                "description": "Model field label",
                "is_html_allowed": False,
                "allowed_placeholders": [],
                "status": "ACTIVE",
            },
        )
        # Default English to human readable, Polish and German to the same for now
        # User will update them via Admin panel if needed.
        for lang in ["de", "en", "pl"]:
            TranslationValue.objects.get_or_create(
                translation_key=key,
                language_code=lang,
                defaults={"value": human_readable},
            )

def backward(apps, schema_editor):
    pass # No need to delete them individually for safety

class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_seed_admin_fields_translations"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
