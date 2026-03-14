# Seed ergebnisse portal UI translations (DE/EN/PL).

from django.db import migrations

ERGEBNISSE_UI = {
    "page_title": {"de": "Ergebnisse – CogitoMed", "en": "Results – CogitoMed", "pl": "Wyniki – CogitoMed"},
    "login_title": {"de": "Ergebnisse – Anmeldung", "en": "Results – Sign in", "pl": "Wyniki – Logowanie"},
    "login_intro": {"de": "Bitte geben Sie Ihre Telefonnummer und Ihr Geburtsdatum ein.", "en": "Please enter your phone number and date of birth.", "pl": "Podaj numer telefonu i datę urodzenia."},
    "phone_label": {"de": "Telefonnummer", "en": "Phone number", "pl": "Numer telefonu"},
    "phone_placeholder": {"de": "z.B. +49 123 456789", "en": "e.g. +49 123 456789", "pl": "np. +48 123 456789"},
    "dob_label": {"de": "Geburtsdatum (TT.MM.JJJJ)", "en": "Date of birth (DD.MM.YYYY)", "pl": "Data urodzenia (DD.MM.RRRR)"},
    "dob_placeholder": {"de": "TT.MM.JJJJ", "en": "DD.MM.YYYY", "pl": "DD.MM.RRRR"},
    "request_code_btn": {"de": "Code per SMS anfordern", "en": "Request code via SMS", "pl": "Poproś o kod SMS"},
    "otp_title": {"de": "Ergebnisse – Code eingeben", "en": "Results – Enter code", "pl": "Wyniki – Wprowadź kod"},
    "otp_intro": {"de": "Bitte geben Sie den 6-stelligen Code ein, den Sie per SMS erhalten haben.", "en": "Please enter the 6-digit code you received via SMS.", "pl": "Wprowadź 6-cyfrowy kod otrzymany SMS-em."},
    "otp_label": {"de": "SMS-Code", "en": "SMS code", "pl": "Kod SMS"},
    "otp_placeholder": {"de": "123456", "en": "123456", "pl": "123456"},
    "submit_btn": {"de": "Bestätigen", "en": "Confirm", "pl": "Potwierdź"},
    "back_to_login": {"de": "Zurück zur Anmeldung", "en": "Back to sign in", "pl": "Powrót do logowania"},
    "documents_title": {"de": "Ihre Dokumente", "en": "Your documents", "pl": "Twoje dokumenty"},
    "document_date_prefix": {"de": "Befund vom", "en": "Report from", "pl": "Wynik z"},
    "download_btn": {"de": "PDF herunterladen", "en": "Download PDF", "pl": "Pobierz PDF"},
    "no_documents": {"de": "Es sind keine Dokumente verfügbar.", "en": "No documents available.", "pl": "Brak dostępnych dokumentów."},
    "error_required": {"de": "Telefonnummer und Geburtsdatum sind erforderlich.", "en": "Phone number and date of birth are required.", "pl": "Numer telefonu i data urodzenia są wymagane."},
    "error_captcha": {"de": "CAPTCHA konnte nicht bestätigt werden. Bitte versuchen Sie es erneut.", "en": "CAPTCHA could not be verified. Please try again.", "pl": "Nie można zweryfikować CAPTCHA. Spróbuj ponownie."},
    "error_otp_required": {"de": "Bitte geben Sie den Code ein.", "en": "Please enter the code.", "pl": "Wprowadź kod."},
    "error_invalid_otp": {"de": "Ungültiger oder abgelaufener Code. Bitte versuchen Sie es erneut.", "en": "Invalid or expired code. Please try again.", "pl": "Nieprawidłowy lub wygasły kod. Spróbuj ponownie."},
}

PREFIX = "other.ergebnisse."


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    for short_key, lang_values in ERGEBNISSE_UI.items():
        full_key = f"{PREFIX}{short_key}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "other",
                "description": f"Ergebnisse portal: {short_key}",
                "is_html_allowed": False,
                "allowed_placeholders": [],
                "status": "ACTIVE",
            },
        )
        for lang, value in lang_values.items():
            TranslationValue.objects.get_or_create(
                translation_key=key,
                language_code=lang,
                defaults={"value": value},
            )


def reverse(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationKey.objects.filter(key__startswith=PREFIX).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_seed_sms_patient_results_translations"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
