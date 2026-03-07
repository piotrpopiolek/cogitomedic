# Generated manually – seed waiting_room form and staff UI.

from django.db import migrations

FORM_UI = {
    "back_to_waiting": {"de": "← Wartezimmer", "en": "← Waiting room", "pl": "← Poczekalnia"},
    "patient_data_title": {"de": "Patientendaten (zur Überprüfung)", "en": "Patient data (for verification)", "pl": "Dane pacjenta (do weryfikacji)"},
    "date_of_birth": {"de": "Geburtsdatum:", "en": "Date of birth:", "pl": "Data urodzenia:"},
    "phone": {"de": "Telefon:", "en": "Phone:", "pl": "Telefon:"},
    "email": {"de": "E-Mail:", "en": "E-mail:", "pl": "E-mail:"},
    "consents_title": {"de": "Einwilligungen", "en": "Consents", "pl": "Zgody"},
    "consent_confirm": {"de": "Ich bestätige", "en": "I agree", "pl": "Akceptuję"},
    "save_consents": {"de": "Einwilligungen speichern", "en": "Save consents", "pl": "Zapisz zgody"},
    "body_map_title": {"de": "Körperschema", "en": "Body map", "pl": "Schemat ciała"},
    "body_map_hint": {"de": "Tippen Sie auf die Abbildung, um die Lage von Hautveränderungen (z. B. Muttermale) zu markieren. Links: Vorderansicht, rechts: Rückansicht.", "en": "Tap on the figure to mark the location of skin changes (e.g. moles). Left: front, right: back.", "pl": "Dotknij rysunku, aby zaznaczyć lokalizację zmian skórnych (np. znamion). Lewy: przód, prawy: tył."},
    "body_map_alt": {"de": "Körperschema – Vorder- und Rückansicht", "en": "Body map – front and back", "pl": "Schemat ciała – przód i tył"},
    "save_body_map": {"de": "Schema speichern", "en": "Save map", "pl": "Zapisz schemat"},
    "body_map_undo_last": {"de": "Letzten Punkt rückgängig", "en": "Undo last point", "pl": "Cofnij ostatni punkt"},
    "anamnesis_title": {"de": "Anamnese", "en": "Anamnesis", "pl": "Wywiad"},
    "notes": {"de": "Anmerkungen:", "en": "Notes:", "pl": "Uwagi:"},
    "notes_placeholder": {"de": "Optional", "en": "Optional", "pl": "Opcjonalnie"},
    "save_anamnesis": {"de": "Anamnese speichern", "en": "Save anamnesis", "pl": "Zapisz wywiad"},
    "signature_title": {"de": "Unterschrift", "en": "Signature", "pl": "Podpis"},
    "clear": {"de": "Löschen", "en": "Clear", "pl": "Wyczyść"},
    "save_signature": {"de": "Unterschrift speichern", "en": "Save signature", "pl": "Zapisz podpis"},
    "signature_saved": {"de": "Unterschrift gespeichert.", "en": "Signature saved.", "pl": "Podpis zapisany."},
    "submit_form": {"de": "Formular absenden", "en": "Submit form", "pl": "Wyślij formularz"},
    "msg_consents_saved": {"de": "Einwilligungen gespeichert.", "en": "Consents saved.", "pl": "Zgody zapisane."},
    "msg_save_error": {"de": "Fehler beim Speichern.", "en": "Error saving.", "pl": "Błąd zapisu."},
    "msg_connection_error": {"de": "Verbindungsfehler.", "en": "Connection error.", "pl": "Błąd połączenia."},
    "msg_body_map_saved": {"de": "Schema gespeichert.", "en": "Map saved.", "pl": "Schemat zapisany."},
    "msg_anamnesis_saved": {"de": "Anamnese gespeichert.", "en": "Anamnesis saved.", "pl": "Wywiad zapisany."},
    "msg_signature_error": {"de": "Fehler beim Speichern der Unterschrift.", "en": "Error saving signature.", "pl": "Błąd zapisu podpisu."},
    "msg_signature_draw_first": {"de": "Bitte zuerst unterschreiben.", "en": "Please draw your signature first.", "pl": "Najpierw narysuj podpis w polu."},
    "msg_submit_error": {"de": "Fehler beim Absenden.", "en": "Error submitting.", "pl": "Błąd wysyłania."},
    "msg_signature_required_before_submit": {"de": "Unterschrift ist vor dem Absenden erforderlich.", "en": "Signature is required before submitting.", "pl": "Podpis jest wymagany przed wysłaniem formularza."},
    "lang_de": {"de": "Deutsch", "en": "Deutsch", "pl": "Deutsch"},
    "lang_en": {"de": "English", "en": "English", "pl": "English"},
    "lang_pl": {"de": "Polski", "en": "Polski", "pl": "Polski"},
    "form_submitted_title": {"de": "Formular wurde abgesendet.", "en": "Form has been submitted.", "pl": "Formularz został wysłany."},
    "back_to_queues": {"de": "Zurück zur Warteliste", "en": "Back to queue list", "pl": "Wróć do listy kolejek"},
    "step_1_title": {"de": "Teil 1: Einwilligungen", "en": "Part 1: Consents", "pl": "Część 1: Zgody"},
    "step_2_title": {"de": "Teil 2: Anamnese", "en": "Part 2: Anamnesis", "pl": "Część 2: Wywiad"},
    "step_3_title": {"de": "Teil 3: Unterschrift", "en": "Part 3: Signature", "pl": "Część 3: Podpis"},
    "step_next": {"de": "Weiter", "en": "Next", "pl": "Dalej"},
    "step_back": {"de": "Zurück", "en": "Back", "pl": "Wstecz"},
    "step_save_and_next": {"de": "Speichern und weiter", "en": "Save and continue", "pl": "Zapisz i kontynuuj"},
    "validation_consents_required": {"de": "Bitte akzeptieren Sie alle erforderlichen Einwilligungen (mit * markiert).", "en": "Please accept all required consents (marked with *).", "pl": "Proszę zaakceptować wszystkie wymagane zgody (oznaczone *)."},
    "validation_anamnesis_required": {"de": "Bitte beantworten Sie alle Pflichtfragen (mit * markiert).", "en": "Please answer all required questions (marked with *).", "pl": "Proszę odpowiedzieć na wszystkie pytania obowiązkowe (oznaczone *)."},
    "msg_try_again": {"de": "Erneut versuchen", "en": "Try again", "pl": "Spróbuj ponownie"},
    "contact_method_phone": {"de": "Telefon", "en": "Phone", "pl": "Telefon"},
    "consent_contact_agree": {"de": "Ja, ich bin mit einer Kontaktaufnahme einverstanden.", "en": "Yes, I agree to be contacted.", "pl": "Tak, wyrażam zgodę na kontakt."},
}

STAFF_UI = {
    "page_title": {"de": "Tablet – Wartezimmer", "en": "Tablet – Waiting room", "pl": "Tablet – Poczekalnia"},
    "logged_in_as": {"de": "Angemeldet:", "en": "Logged in:", "pl": "Zalogowany:"},
    "logout": {"de": "Abmelden", "en": "Log out", "pl": "Wyloguj"},
    "lang_de": {"de": "Deutsch", "en": "Deutsch", "pl": "Deutsch"},
    "lang_en": {"de": "English", "en": "English", "pl": "English"},
    "lang_pl": {"de": "Polski", "en": "Polski", "pl": "Polski"},
    "home_title": {"de": "Wartezimmer – Warteschlange wählen", "en": "Waiting room – Choose queue", "pl": "Poczekalnia – wybór kolejki"},
    "date": {"de": "Datum:", "en": "Date:", "pl": "Data:"},
    "no_queues_today": {"de": "Keine Warteschlangen für heute. Erstellen Sie eine in der Rezeption.", "en": "No queues for today. Create one in reception.", "pl": "Brak kolejek na dziś. Utwórz kolejkę w panelu recepcji."},
    "queue_not_today": {"de": "Diese Warteschlange ist nicht von heute. Bitte wählen Sie eine Warteschlange von der heutigen Liste.", "en": "This queue is not from today. Please choose a queue from today's list.", "pl": "Ta kolejka nie jest z dzisiaj. Wybierz kolejkę z listy na dziś."},
    "back_to_queues": {"de": "← Zurück zur Warteschlangenliste", "en": "← Back to queue list", "pl": "← Wróć do listy kolejek"},
    "queue_entries_title": {"de": "Patienten in der Warteschlange", "en": "Patients in queue", "pl": "Pacjenci w kolejce"},
    "no_patients": {"de": "Keine Patienten in dieser Warteschlange.", "en": "No patients in this queue.", "pl": "Brak pacjentów w tej kolejce."},
    "appointment_time": {"de": "Terminzeit", "en": "Appointment time", "pl": "Godzina wizyty"},
    "back_to_patients": {"de": "← Zurück zur Patientenliste", "en": "← Back to patient list", "pl": "← Wróć do listy pacjentów"},
    "entry_start_title": {"de": "Formular starten", "en": "Start form", "pl": "Start formularza"},
    "patient_label": {"de": "Patient:", "en": "Patient:", "pl": "Pacjent:"},
    "position_label": {"de": "Position", "en": "Position", "pl": "Pozycja"},
    "status_label": {"de": "Status:", "en": "Status:", "pl": "Status:"},
    "open_form_btn": {"de": "Intake-Formular öffnen", "en": "Open intake form", "pl": "Otwórz formularz intake"},
    "entry_started_title": {"de": "Formular vorbereitet", "en": "Form ready", "pl": "Formularz przygotowany"},
    "hand_tablet_msg": {"de": "Tablet dem Patienten zum Ausfüllen der Anamnese (Einwilligungen, Anamnese, Unterschrift) übergeben.", "en": "Hand the tablet to the patient to fill in the questionnaire (consents, anamnesis, signature).", "pl": "Przekaż tablet pacjentowi do wypełnienia ankiety (zgody, anamneza, podpis)."},
    "cta_fill_form": {"de": "Tablet dem Patienten übergeben – Formular ausfüllen", "en": "Hand tablet to patient – Fill form", "pl": "Przekaż tablet pacjentowi – wypełnij formularz"},
    "error_title": {"de": "Fehler", "en": "Error", "pl": "Błąd"},
    "error_home_link": {"de": "Tablet-Startseite", "en": "Tablet home", "pl": "Strona główna tabletu"},
    "login_title": {"de": "Wartezimmer – Anmeldung", "en": "Waiting room – Log in", "pl": "Poczekalnia – logowanie"},
    "login_btn": {"de": "Anmelden", "en": "Log in", "pl": "Zaloguj"},
    "login_error": {"de": "Ungültige Anmeldung oder keine Tablet-Berechtigung.", "en": "Invalid login or no tablet permission.", "pl": "Nieprawidłowy login lub brak uprawnień tabletu."},
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    for short_key, mapping in FORM_UI.items():
        full_key = f"waiting_room.form.{short_key}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "waiting_room",
                "description": "Waiting room tablet form UI",
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

    for short_key, mapping in STAFF_UI.items():
        full_key = f"waiting_room.staff.{short_key}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "waiting_room",
                "description": "Waiting room staff UI",
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
    form_keys = [f"waiting_room.form.{k}" for k in FORM_UI]
    staff_keys = [f"waiting_room.staff.{k}" for k in STAFF_UI]
    TranslationKey.objects.filter(key__in=form_keys + staff_keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_seed_doctor_pdf_labels"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
