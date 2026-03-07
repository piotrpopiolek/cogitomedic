# Generated manually – seed doctor PDF labels.

from django.db import migrations

PDF_LABELS = {
    "befund": {"de": "Befund", "en": "Befund", "pl": "Befund"},
    "document_id": {"de": "Dokument-ID", "en": "Document ID", "pl": "ID dokumentu"},
    "version": {"de": "Version", "en": "Version", "pl": "Wersja"},
    "generated_at": {"de": "Erstellt am", "en": "Generated at", "pl": "Wygenerowano"},
    "locale": {"de": "Sprache", "en": "Locale", "pl": "Język"},
    "patient": {"de": "Patient", "en": "Patient", "pl": "Pacjent"},
    "name": {"de": "Name", "en": "Name", "pl": "Imię i nazwisko"},
    "date_of_birth": {"de": "Geburtsdatum", "en": "Date of birth", "pl": "Data urodzenia"},
    "phone": {"de": "Telefon", "en": "Phone", "pl": "Telefon"},
    "email": {"de": "E-Mail", "en": "Email", "pl": "E-mail"},
    "global_assessment": {"de": "Gesamtbeurteilung", "en": "Global Assessment", "pl": "Ocena ogólna"},
    "fitzpatrick_type": {"de": "Hauttyp (Fitzpatrick)", "en": "Fitzpatrick type", "pl": "Typ skóry (Fitzpatrick)"},
    "overall_image_assessment": {"de": "Gesamtbeurteilung Bildanalyse", "en": "Overall image assessment", "pl": "Ocena obrazu"},
    "final_assessment": {"de": "Ärztliche Gesamteinschätzung", "en": "Final assessment", "pl": "Końcowa ocena lekarska"},
    "diagnosis_code": {"de": "Diagnosecode", "en": "Diagnosis code", "pl": "Kod rozpoznania"},
    "procedure_code": {"de": "Prozedurcode", "en": "Procedure code", "pl": "Kod procedury"},
    "examination_scope": {"de": "Untersuchungsumfang", "en": "Examination Scope", "pl": "Zakres badania"},
    "lesions": {"de": "Läsionen", "en": "Lesions", "pl": "Zmiany"},
    "group": {"de": "Gruppe", "en": "Group", "pl": "Grupa"},
    "numbers": {"de": "Nummern", "en": "Numbers", "pl": "Numery"},
    "clinical_assessment": {"de": "Klinisch-dermatoskopische Einschätzung", "en": "Clinical assessment", "pl": "Ocena kliniczno-dermatoskopowa"},
    "malignancy_risk": {"de": "Malignitätsrisiko", "en": "Malignancy risk", "pl": "Ryzyko złośliwości"},
    "dermatoscopic_features": {"de": "Dermatoskopische Merkmale", "en": "Dermatoscopic features", "pl": "Cechy dermatoskopowe"},
    "final_text": {"de": "Text", "en": "Final text", "pl": "Tekst"},
    "recommendations": {"de": "Empfehlungen", "en": "Recommendations", "pl": "Rekomendacje"},
    "summary": {"de": "Zusammenfassung", "en": "Summary", "pl": "Podsumowanie"},
    "no_lesions": {"de": "Keine Läsionen angegeben.", "en": "No lesions listed.", "pl": "Brak wpisanych zmian."},
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    for short_key, mapping in PDF_LABELS.items():
        full_key = f"doctor.pdf_label.{short_key}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "doctor",
                "description": "Doctor PDF label",
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


def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    keys_to_delete = [f"doctor.pdf_label.{k}" for k in PDF_LABELS]
    TranslationKey.objects.filter(key__in=keys_to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_seed_doctor_ui_and_fitzpatrick"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
