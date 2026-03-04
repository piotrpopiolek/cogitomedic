# Generated manually – seed REAL translations for all fields

import os
from django.db import migrations

def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    field_translations = {
        "accepted": {"de": "Akzeptiert", "en": "Accepted", "pl": "Zaakceptowano"},
        "content_pl": {"de": "Inhalt (PL)", "en": "Content (PL)", "pl": "Treść (PL)"},
        "title_de": {"de": "Titel (DE)", "en": "Title (DE)", "pl": "Tytuł (DE)"},
        "is_html_allowed": {"de": "HTML erlaubt", "en": "Is HTML allowed", "pl": "HTML dozwolony"},
        "summary_favorites": {"de": "Zusammenfassung-Favoriten", "en": "Summary favorites", "pl": "Ulubione podsumowania"},
        "password": {"de": "Passwort", "en": "Password", "pl": "Hasło"},
        "raw_row": {"de": "Rohdaten-Zeile", "en": "Raw row", "pl": "Surowy wiersz"},
        "is_staff": {"de": "Ist Mitarbeiter", "en": "Is staff", "pl": "Jest personelem"},
        "city": {"de": "Stadt", "en": "City", "pl": "Miasto"},
        "sms_sent": {"de": "SMS gesendet", "en": "SMS sent", "pl": "SMS wysłany"},
        "source_file_sha256": {"de": "Quelldatei SHA256", "en": "Source file SHA256", "pl": "SHA256 pliku źródłowego"},
        "shift_code": {"de": "Schichtcode", "en": "Shift code", "pl": "Kod zmiany"},
        "first_name": {"de": "Vorname", "en": "First name", "pl": "Imię"},
        "hidrive_sent": {"de": "An HiDrive gesendet", "en": "Sent to HiDrive", "pl": "Wysłano do HiDrive"},
        "key": {"de": "Schlüssel", "en": "Key", "pl": "Klucz"},
        "signature_sha256": {"de": "Unterschrift SHA256", "en": "Signature SHA256", "pl": "SHA256 podpisu"},
        "is_global": {"de": "Ist global", "en": "Is global", "pl": "Jest globalne"},
        "country_code": {"de": "Ländercode", "en": "Country code", "pl": "Kod kraju"},
        "error_message": {"de": "Fehlermeldung", "en": "Error message", "pl": "Komunikat błędu"},
        "is_active": {"de": "Ist aktiv", "en": "Is active", "pl": "Czy aktywny"},
        "notes": {"de": "Notizen", "en": "Notes", "pl": "Notatki"},
        "processed_at": {"de": "Verarbeitet am", "en": "Processed at", "pl": "Przetworzono"},
        "version_no": {"de": "Versionsnummer", "en": "Version no", "pl": "Numer wersji"},
        "last_published_at": {"de": "Zuletzt veröffentlicht am", "en": "Last published at", "pl": "Ostatnio opublikowano"},
        "payload": {"de": "Nutzdaten", "en": "Payload", "pl": "Dane (payload)"},
        "published_at": {"de": "Veröffentlicht am", "en": "Published at", "pl": "Opublikowano"},
        "username": {"de": "Benutzername", "en": "Username", "pl": "Nazwa użytkownika"},
        "inserted_rows": {"de": "Eingefügte Zeilen", "en": "Inserted rows", "pl": "Wstawione wiersze"},
        "value": {"de": "Wert", "en": "Value", "pl": "Wartość"},
        "error_code": {"de": "Fehlercode", "en": "Error code", "pl": "Kod błędu"},
        "procedure_code": {"de": "Verfahrenscode", "en": "Procedure code", "pl": "Kod procedury"},
        "template_locale": {"de": "Vorlagensprache", "en": "Template locale", "pl": "Język szablonu"},
        "expires_at": {"de": "Läuft ab am", "en": "Expires at", "pl": "Wygasa"},
        "version": {"de": "Version", "en": "Version", "pl": "Wersja"},
        "option_text_en": {"de": "Optionstext (EN)", "en": "Option text (EN)", "pl": "Tekst opcji (EN)"},
        "form_locale": {"de": "Formularsprache", "en": "Form locale", "pl": "Język formularza"},
        "status": {"de": "Status", "en": "Status", "pl": "Status"},
        "event_type": {"de": "Ereignistyp", "en": "Event type", "pl": "Typ zdarzenia"},
        "last_seen_at": {"de": "Zuletzt gesehen am", "en": "Last seen at", "pl": "Ostatnio widziany"},
        "source": {"de": "Quelle", "en": "Source", "pl": "Źródło"},
        "question_text_en": {"de": "Fragentext (EN)", "en": "Question text (EN)", "pl": "Treść pytania (EN)"},
        "content_en": {"de": "Inhalt (EN)", "en": "Content (EN)", "pl": "Treść (EN)"},
        "medical_payload_schema_version": {"de": "Schemaversion der med. Nutzdaten", "en": "Medical payload schema version", "pl": "Wersja schematu danych medycznych"},
        "pdf_local_path": {"de": "Lokaler PDF-Pfad", "en": "PDF local path", "pl": "Lokalna ścieżka PDF"},
        "source_file_name": {"de": "Dateiname der Quelle", "en": "Source file name", "pl": "Nazwa pliku źródłowego"},
        "sms_sent_at": {"de": "SMS gesendet am", "en": "SMS sent at", "pl": "Czas wysłania SMS"},
        "title_pl": {"de": "Titel (PL)", "en": "Title (PL)", "pl": "Tytuł (PL)"},
        "event_time": {"de": "Ereigniszeit", "en": "Event time", "pl": "Czas zdarzenia"},
        "description": {"de": "Beschreibung", "en": "Description", "pl": "Opis"},
        "reason": {"de": "Grund", "en": "Reason", "pl": "Powód"},
        "external_source_id": {"de": "Externe Quellen-ID", "en": "External source ID", "pl": "ID z zewnętrznego źródła"},
        "row_number": {"de": "Zeilennummer", "en": "Row number", "pl": "Numer wiersza"},
        "identity_alert_created_at": {"de": "Identitätswarnung erstellt am", "en": "Identity alert created at", "pl": "Alert tożsamości utworzony"},
        "phone": {"de": "Telefon", "en": "Phone", "pl": "Telefon"},
        "phone_number": {"de": "Telefonnummer", "en": "Phone number", "pl": "Numer telefonu"},
        "question_text_de": {"de": "Fragentext (DE)", "en": "Question text (DE)", "pl": "Treść pytania (DE)"},
        "daily_queue": {"de": "Tageswarteschlange", "en": "Daily queue", "pl": "Kolejka dzienna"},
        "max_retries": {"de": "Max. Wiederholungen", "en": "Max retries", "pl": "Maksymalna liczba ponowień"},
        "body_map_data": {"de": "Körperschema-Daten", "en": "Body map data", "pl": "Dane schematu ciała"},
        "selected_option_codes": {"de": "Ausgewählte Optionscodes", "en": "Selected option codes", "pl": "Wybrane kody opcji"},
        "body_map_schema_version": {"de": "Körperschema-Version", "en": "Body map schema version", "pl": "Wersja schematu ciała"},
        "appointment_time": {"de": "Terminzeit", "en": "Appointment time", "pl": "Godzina wizyty"},
        "street": {"de": "Straße", "en": "Street", "pl": "Ulica"},
        "metadata": {"de": "Metadaten", "en": "Metadata", "pl": "Metadane"},
        "display_order": {"de": "Anzeigereihenfolge", "en": "Display order", "pl": "Kolejność wyświetlania"},
        "date_joined": {"de": "Beigetreten am", "en": "Date joined", "pl": "Data dołączenia"},
        "publish_locale": {"de": "Veröffentlichungssprache", "en": "Publish locale", "pl": "Język publikacji"},
        "hidrive_path": {"de": "HiDrive-Pfad", "en": "HiDrive path", "pl": "Ścieżka HiDrive"},
        "snapshot_payload": {"de": "Snapshot-Nutzdaten", "en": "Snapshot payload", "pl": "Dane migawki"},
        "diagnosis_code": {"de": "Diagnosecode", "en": "Diagnosis code", "pl": "Kod diagnozy"},
        "current_version_no": {"de": "Aktuelle Versionsnummer", "en": "Current version no", "pl": "Aktualny numer wersji"},
        "payload_schema_version": {"de": "Nutzdaten-Schemaversion", "en": "Payload schema version", "pl": "Wersja schematu danych"},
        "name": {"de": "Name", "en": "Name", "pl": "Nazwa"},
        "visit_external_id": {"de": "Externe Besuchs-ID", "en": "Visit external ID", "pl": "Zewnętrzne ID wizyty"},
        "email": {"de": "E-Mail", "en": "Email", "pl": "E-mail"},
        "language_code": {"de": "Sprachcode", "en": "Language code", "pl": "Kod języka"},
        "title_en": {"de": "Titel (EN)", "en": "Title (EN)", "pl": "Tytuł (EN)"},
        "anamnesis_schema_version": {"de": "Anamnese-Schemaversion", "en": "Anamnesis schema version", "pl": "Wersja schematu wywiadu"},
        "is_required": {"de": "Ist erforderlich", "en": "Is required", "pl": "Jest wymagane"},
        "locked_at": {"de": "Gesperrt am", "en": "Locked at", "pl": "Zablokowano"},
        "date_of_birth": {"de": "Geburtsdatum", "en": "Date of birth", "pl": "Data urodzenia"},
        "submitted_at": {"de": "Eingereicht am", "en": "Submitted at", "pl": "Wysłano"},
        "retry_count": {"de": "Anzahl Wiederholungen", "en": "Retry count", "pl": "Liczba ponowień"},
        "option_text_de": {"de": "Optionstext (DE)", "en": "Option text (DE)", "pl": "Tekst opcji (DE)"},
        "pdf_checksum_sha256": {"de": "PDF Checksumme SHA256", "en": "PDF checksum SHA256", "pl": "Suma kontrolna PDF"},
        "identity_resolution_due_at": {"de": "Identitätsklärung fällig am", "en": "Identity resolution due at", "pl": "Termin weryfikacji tożsamości"},
        "accepted_at": {"de": "Akzeptiert am", "en": "Accepted at", "pl": "Zaakceptowano"},
        "clinic_site": {"de": "Standort", "en": "Clinic site", "pl": "Placówka"},
        "lesion_group_favorites": {"de": "Favoriten Läsionsgruppe", "en": "Lesion group favorites", "pl": "Ulubione grup zmian"},
        "consumed_at": {"de": "Verwendet am", "en": "Consumed at", "pl": "Wykorzystano"},
        "effective_to": {"de": "Gültig bis", "en": "Effective to", "pl": "Ważne do"},
        "allowed_placeholders": {"de": "Erlaubte Platzhalter", "en": "Allowed placeholders", "pl": "Dozwolone zmienne"},
        "changed_at": {"de": "Geändert am", "en": "Changed at", "pl": "Zmieniono"},
        "local_pdf_deleted_at": {"de": "Lokales PDF gelöscht am", "en": "Local PDF deleted at", "pl": "Lokalny PDF usunięto"},
        "anamnesis_payload": {"de": "Anamnese-Nutzdaten", "en": "Anamnesis payload", "pl": "Dane wywiadu"},
        "queue_date": {"de": "Warteschlangen-Datum", "en": "Queue date", "pl": "Data kolejki"},
        "android_id": {"de": "Android-ID", "en": "Android ID", "pl": "ID Androida"},
        "preferred_locale": {"de": "Bevorzugte Sprache", "en": "Preferred locale", "pl": "Preferowany język"},
        "signature_file_path": {"de": "Unterschrifts-Dateipfad", "en": "Signature file path", "pl": "Ścieżka pliku podpisu"},
        "last_name": {"de": "Nachname", "en": "Last name", "pl": "Nazwisko"},
        "available_at": {"de": "Verfügbar ab", "en": "Available at", "pl": "Dostępne od"},
        "template_body": {"de": "Vorlageninhalt", "en": "Template body", "pl": "Treść szablonu"},
        "aggregate_type": {"de": "Aggregat-Typ", "en": "Aggregate type", "pl": "Typ agregatu"},
        "postal_code": {"de": "Postleitzahl", "en": "Postal code", "pl": "Kod pocztowy"},
        "medical_payload": {"de": "Medizinische Nutzdaten", "en": "Medical payload", "pl": "Dane medyczne"},
        "effective_from": {"de": "Gültig ab", "en": "Effective from", "pl": "Ważne od"},
        "patient": {"de": "Patient", "en": "Patient", "pl": "Pacjent"},
        "selected_option_code": {"de": "Ausgewählter Optionscode", "en": "Selected option code", "pl": "Kod wybranej opcji"},
        "total_rows": {"de": "Zeilen gesamt", "en": "Total rows", "pl": "Suma wierszy"},
        "code": {"de": "Code", "en": "Code", "pl": "Kod"},
        "finished_at": {"de": "Abgeschlossen am", "en": "Finished at", "pl": "Zakończono"},
        "doctolib_patient_id": {"de": "Doctolib Patienten-ID", "en": "Doctolib patient ID", "pl": "ID pacjenta Doctolib"},
        "error_rows": {"de": "Fehlerhafte Zeilen", "en": "Error rows", "pl": "Błędne wiersze"},
        "content_de": {"de": "Inhalt (DE)", "en": "Content (DE)", "pl": "Treść (DE)"},
        "position_no": {"de": "Positionsnummer", "en": "Position no", "pl": "Pozycja (nr)"},
        "question_text_pl": {"de": "Fragentext (PL)", "en": "Question text (PL)", "pl": "Treść pytania (PL)"},
        "option_text_pl": {"de": "Optionstext (PL)", "en": "Option text (PL)", "pl": "Tekst opcji (PL)"},
        "hidrive_sent_at": {"de": "An HiDrive gesendet am", "en": "HiDrive sent at", "pl": "Wysłano do HiDrive (czas)"},
    }

    for short_key, mapping in field_translations.items():
        full_key = f"administration.field_{short_key}"
        try:
            key = TranslationKey.objects.get(key=full_key)
            for lang, text in mapping.items():
                val, _ = TranslationValue.objects.get_or_create(
                    translation_key=key,
                    language_code=lang,
                    defaults={"value": text},
                )
                if val.value != text:
                    val.value = text
                    val.save()
        except TranslationKey.DoesNotExist:
            continue

def backward(apps, schema_editor):
    pass # No need to delete them individually for safety

class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_seed_all_fields_and_login_translations"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
