# Generated manually – seed doctor UI and Fitzpatrick translations.

from django.db import migrations

DOCTOR_UI = {
    "area_name": {"de": "Arztbereich", "en": "Doctor area", "pl": "Panel lekarza"},
    "logout": {"de": "Abmelden", "en": "Log out", "pl": "Wyloguj"},
    "login_title": {"de": "Arztbereich – Anmelden", "en": "Doctor area – Sign in", "pl": "Panel lekarza – Logowanie"},
    "username": {"de": "Benutzername", "en": "Username", "pl": "Nazwa użytkownika"},
    "password": {"de": "Passwort", "en": "Password", "pl": "Hasło"},
    "login_submit": {"de": "Anmelden", "en": "Sign in", "pl": "Zaloguj"},
    "login_footer": {"de": "Nur für Berechtigte (Arzt/Admin).", "en": "For authorised users (doctor/admin) only.", "pl": "Tylko dla uprawnionych (lekarz/administrator)."},
    "list_title": {"de": "Medizinische Dokumente (Work Queue)", "en": "Medical documents (work queue)", "pl": "Dokumenty medyczne (kolejka)"},
    "filter_status": {"de": "Status", "en": "Status", "pl": "Status"},
    "filter_all": {"de": "– alle –", "en": "– all –", "pl": "– wszystkie –"},
    "filter_draft": {"de": "Entwurf", "en": "Draft", "pl": "Szkic"},
    "filter_published": {"de": "Veröffentlicht", "en": "Published", "pl": "Opublikowany"},
    "filter_date": {"de": "Datum", "en": "Date", "pl": "Data"},
    "filter_patient": {"de": "Patient (Name)", "en": "Patient (name)", "pl": "Pacjent (nazwisko)"},
    "filter_search_placeholder": {"de": "Suche…", "en": "Search…", "pl": "Szukaj…"},
    "filter_submit": {"de": "Filtern", "en": "Filter", "pl": "Filtruj"},
    "table_patient": {"de": "Patient", "en": "Patient", "pl": "Pacjent"},
    "table_date": {"de": "Datum", "en": "Date", "pl": "Data"},
    "table_status": {"de": "Status", "en": "Status", "pl": "Status"},
    "table_pdf": {"de": "PDF", "en": "PDF", "pl": "PDF"},
    "table_hidrive": {"de": "HiDrive", "en": "HiDrive", "pl": "HiDrive"},
    "table_sms": {"de": "SMS", "en": "SMS", "pl": "SMS"},
    "open": {"de": "Öffnen", "en": "Open", "pl": "Otwórz"},
    "no_documents": {"de": "Keine Dokumente.", "en": "No documents.", "pl": "Brak dokumentów."},
    "pagination_page": {"de": "Seite", "en": "Page", "pl": "Strona"},
    "pagination_total": {"de": "Einträge gesamt.", "en": "entries total.", "pl": "łącznie."},
    "back_to_list": {"de": "← Zurück zur Liste", "en": "← Back to list", "pl": "← Wróć do listy"},
    "intake_header": {"de": "Anamnese / Intake", "en": "Anamnesis / Intake", "pl": "Wywiad / Ankieta"},
    "patient_label": {"de": "Patient", "en": "Patient", "pl": "Pacjent"},
    "consents_label": {"de": "Zgody", "en": "Consents", "pl": "Zgody"},
    "body_map_title": {"de": "Körperschema (vom Patient markiert)", "en": "Body map (marked by patient)", "pl": "Schemat ciała (zaznaczony przez pacjenta)"},
    "body_map_hint": {"de": "Vorder- und Rückansicht mit den vom Patient gesetzten Markierungen.", "en": "Front and back view with markings set by the patient.", "pl": "Widok z przodu i z tyłu z oznaczeniami ustawionymi przez pacjenta."},
    "section_1": {"de": "1. Untersuchungsumfang (Mehrfachauswahl)", "en": "1. Scope of examination (multiple choice)", "pl": "1. Zakres badania (wielokrotny wybór)"},
    "section_2": {"de": "2. Hauttyp nach Fitzpatrick", "en": "2. Skin type (Fitzpatrick)", "pl": "2. Typ skóry wg Fitzpatricka"},
    "section_3": {"de": "3. Gesamtbeurteilung der Bildanalyse", "en": "3. Overall image assessment", "pl": "3. Ocena ogólna analizy obrazu"},
    "section_4": {"de": "4. Auswahl der Läsion(en)", "en": "4. Lesion selection", "pl": "4. Wybór zmian (läsion)"},
    "section_5": {"de": "5. Dermatoskopische Merkmale (Mehrfachauswahl)", "en": "5. Dermatoscopic features (multiple choice)", "pl": "5. Cechy dermatoskopowe (wielokrotny wybór)"},
    "section_6": {"de": "6. Klinisch-dermatoskopische Einschätzung", "en": "6. Clinical-dermatoscopic assessment", "pl": "6. Ocena kliniczno-dermatoskopowa"},
    "section_7": {"de": "7. Einschätzung des Malignitätsrisikos", "en": "7. Malignancy risk assessment", "pl": "7. Ocena ryzyka złośliwości"},
    "section_8": {"de": "8. Text (generiert / bearbeitet)", "en": "8. Text (generated / edited)", "pl": "8. Tekst (wygenerowany / edytowany)"},
    "section_9": {"de": "9. Zusammenfassung Gesamtbefund (editierbar)", "en": "9. Summary Befund (editable)", "pl": "9. Podsumowanie Befund (do edycji)"},
    "section_10": {"de": "10. Ärztliche Empfehlung (Mehrfachauswahl)", "en": "10. Medical recommendations (multiple choice)", "pl": "10. Zalecenia lekarskie (wielokrotny wybór)"},
    "section_11": {"de": "11. Ärztliche Gesamteinschätzung", "en": "11. Final medical assessment", "pl": "11. Końcowa ocena lekarska"},
    "examination_intimate": {"de": "Intimbereich nicht untersucht", "en": "Intimate area not examined", "pl": "Okolica intymna niebadana"},
    "examination_oral": {"de": "Mundschleimhaut nicht untersucht", "en": "Oral mucosa not examined", "pl": "Błona śluzowa jamy ustnej niebadana"},
    "overall_no_control": {"de": "Keine kontrollbedürftigen Hautveränderungen erkennbar", "en": "No skin changes requiring control", "pl": "Brak zmian skórnych wymagających kontroli"},
    "overall_control": {"de": "Kontrollbedürftige Hautveränderungen erkennbar", "en": "Skin changes requiring control present", "pl": "Występują zmiany wymagające kontroli"},
    "lesion_no": {"de": "Läsion Nr.", "en": "Lesion no.", "pl": "Zmiana nr"},
    "lesion_header": {"de": "Merkmale und Einschätzung", "en": "Features and assessment", "pl": "Cechy i ocena"},
    "add_group": {"de": "+ Gruppe hinzufügen", "en": "+ Add group", "pl": "+ Dodaj grupę"},
    "remove_group": {"de": "Gruppe entfernen", "en": "Remove group", "pl": "Usuń grupę"},
    "feature_asymmetry": {"de": "Asymmetrie", "en": "Asymmetry", "pl": "Asymetria"},
    "feature_irregular_border": {"de": "Unregelmäßige Begrenzung", "en": "Irregular border", "pl": "Nieregularna granica"},
    "feature_inhomogeneous": {"de": "Inhomogene Pigmentierung", "en": "Inhomogeneous pigmentation", "pl": "Niejednorodna pigmentacja"},
    "feature_multicolor": {"de": "Mehrfarbigkeit", "en": "Multicolor", "pl": "Wielobarwność"},
    "feature_atypical_network": {"de": "Atypisches Pigmentnetz", "en": "Atypical pigment network", "pl": "Nietypowa sieć pigmentowa"},
    "feature_irregular_globules": {"de": "Unregelmäßige Globuli", "en": "Irregular globules", "pl": "Nieregularne globule"},
    "feature_irregular_dots": {"de": "Unregelmäßige Punkte", "en": "Irregular dots", "pl": "Nieregularne punkty"},
    "feature_structureless": {"de": "Strukturlose Areale", "en": "Structureless areas", "pl": "Obszary bez struktury"},
    "feature_vascular": {"de": "Atypische Gefäßstrukturen", "en": "Atypical vascular structures", "pl": "Nietypowe struktury naczyniowe"},
    "feature_regression": {"de": "Regressionsareale", "en": "Regression areas", "pl": "Obszary regresji"},
    "clinical_unremarkable": {"de": "Unauffällige Läsion", "en": "Unremarkable lesion", "pl": "Zmiana niebudząca obaw"},
    "clinical_slight": {"de": "Leicht atypische Läsion", "en": "Slightly atypical lesion", "pl": "Lekko atypowa zmiana"},
    "clinical_control": {"de": "Kontrollbedürftige Läsion", "en": "Lesion requiring control", "pl": "Zmiana wymagająca kontroli"},
    "clinical_suspicious": {"de": "Suspekte Läsion", "en": "Suspicious lesion", "pl": "Zmiana podejrzana"},
    "malignancy_none": {"de": "Kein Malignitätsverdacht", "en": "No malignancy suspicion", "pl": "Brak podejrzenia złośliwości"},
    "malignancy_low": {"de": "Niedriger Malignitätsverdacht", "en": "Low malignancy suspicion", "pl": "Niskie podejrzenie złośliwości"},
    "malignancy_cannot_exclude": {"de": "Malignitätsverdacht kann nicht ausgeschlossen werden", "en": "Malignancy cannot be excluded", "pl": "Nie można wykluczyć podejrzenia złośliwości"},
    "text_placeholder": {"de": "Text hier anzeigen und bearbeiten", "en": "Display and edit content here.", "pl": "Treść tutaj (można edytować)."},
    "rec_followup_3": {"de": "Dermatologische Verlaufskontrolle in 3 Monaten empfohlen", "en": "Dermatological follow-up in 3 months recommended", "pl": "Kontrola dermatologiczna za 3 miesiące"},
    "rec_followup_6": {"de": "Dermatologische Verlaufskontrolle in 6 Monaten empfohlen", "en": "Dermatological follow-up in 6 months recommended", "pl": "Kontrola dermatologiczna za 6 miesięcy"},
    "rec_prompt_visit": {"de": "Bei klinischer Veränderung zeitnahe persönliche dermatologische Vorstellung empfohlen", "en": "Prompt dermatology visit if clinical change", "pl": "W razie zmiany – pilna wizyta dermatologiczna"},
    "rec_no_short": {"de": "Aktuell keine kurzfristige Kontrolle erforderlich", "en": "No short-term follow-up required at present", "pl": "Obecnie brak potrzeby krótkoterminowej kontroli"},
    "final_no_suspicion": {"de": "Aktuell kein höhergradiger Malignitätsverdacht", "en": "No high-grade malignancy suspicion at present", "pl": "Obecnie brak wysokiego podejrzenia złośliwości"},
    "final_high_grade": {"de": "Ein höhergradiger Malignitätsverdacht kann nicht sicher ausgeschlossen werden", "en": "High-grade malignancy cannot be excluded", "pl": "Nie można wykluczyć wysokiego podejrzenia złośliwości"},
    "btn_generate": {"de": "—", "en": "—", "pl": "—"},
    "btn_save_draft": {"de": "Entwurf speichern", "en": "Save draft", "pl": "Zapisz szkic"},
    "btn_preview_pdf": {"de": "PDF-Vorschau", "en": "Preview PDF", "pl": "Podgląd PDF"},
    "btn_publish": {"de": "Bestätigen und senden", "en": "Approve and send", "pl": "Zatwierdź i wyślij"},
    "template_select_label": {"de": "Textvorlage", "en": "Text template", "pl": "Szablon tekstu"},
    "template_select_placeholder": {"de": "Vorlage wählen…", "en": "Select template…", "pl": "Wybierz szablon…"},
    "template_select_hint": {"de": "Vorlage wählen – danach erscheinen die Favoriten in Abschnitt 8 und 9.", "en": "Choose a template – favorites for sections 8 and 9 will then appear.", "pl": "Wybierz szablon – wówczas pojawią się ulubione w sekcjach 8 i 9."},
    "favorite_lesion_label": {"de": "Favorit für Läsionsgruppe", "en": "Favorite for lesion group", "pl": "Ulubiony preset grupy"},
    "favorite_summary_label": {"de": "Favorit für Abschnitt 9", "en": "Favorite for section 9", "pl": "Ulubiony tekst sekcji 9"},
    "btn_apply_favorite": {"de": "Anwenden", "en": "Apply", "pl": "Zastosuj"},
    "resend_sms": {"de": "SMS erneut senden", "en": "Resend SMS", "pl": "Wyślij SMS ponownie"},
    "msg_lesion_required": {"de": "Bitte mindestens eine Läsion mit Nummern angeben.", "en": "Please add at least one lesion with numbers.", "pl": "Podaj co najmniej jedną zmianę z numerami."},
    "msg_generate_success": {"de": "Text generiert.", "en": "Text generated.", "pl": "Tekst wygenerowany."},
    "msg_save_success": {"de": "Entwurf gespeichert.", "en": "Draft saved.", "pl": "Szkic zapisany."},
    "msg_network_error": {"de": "Netzwerkfehler.", "en": "Network error.", "pl": "Błąd sieci."},
    "msg_error": {"de": "Fehler", "en": "Error", "pl": "Błąd"},
    "msg_publish_success": {"de": "Veröffentlicht. PDF wird erstellt.", "en": "Published. PDF will be generated.", "pl": "Opublikowano. PDF zostanie wygenerowany."},
    "msg_retry_success": {"de": "Erneuter Versuch wurde eingeplant.", "en": "Retry has been queued.", "pl": "Ponowienie zostało dodane do kolejki."},
    "msg_template_load_error": {"de": "Vorlagen konnten nicht geladen werden.", "en": "Could not load templates.", "pl": "Nie udało się pobrać szablonów."},
    "msg_favorite_applied": {"de": "Favorit angewendet.", "en": "Favorite applied.", "pl": "Zastosowano ulubiony preset."},
    "msg_validation_examination_scope_required": {"de": "Vor der Veröffentlichung muss die Sektion „1. Untersuchungsumfang (Mehrfachauswahl)“ ausgefüllt werden: mindestens eine Option ankreuzen (Intimbereich nicht untersucht oder Mundschleimhaut nicht untersucht).", "en": "Before publishing, please fill in section \"1. Scope of examination (multiple choice)\": select at least one option (Intimate area not examined or Oral mucosa not examined).", "pl": "Przed publikacją należy wypełnić sekcję „1. Untersuchungsumfang (Mehrfachauswahl)”: zaznacz co najmniej jedną opcję (Intimbereich nicht untersucht lub Mundschleimhaut nicht untersucht)."},
    "msg_validation_fitzpatrick_required": {"de": "Vor der Veröffentlichung muss der Hauttyp nach Fitzpatrick (Sektion 2) gewählt werden.", "en": "Before publishing, please select Fitzpatrick skin type (section 2).", "pl": "Przed publikacją należy wybrać Hauttyp nach Fitzpatrick (sekcja 2)."},
    "msg_validation_overall_assessment_required": {"de": "Vor der Veröffentlichung muss die Gesamtbeurteilung der Bildanalyse (Sektion 3) gewählt werden.", "en": "Before publishing, please select overall image assessment (section 3).", "pl": "Przed publikacją należy wybrać ocenę ogólną analizy obrazu (sekcja 3)."},
    "msg_validation_recommendations_required": {"de": "Vor der Veröffentlichung muss mindestens eine ärztliche Empfehlung (Sektion 10) ausgewählt werden.", "en": "Before publishing, please select at least one medical recommendation (section 10).", "pl": "Przed publikacją należy wybrać co najmniej jedną zalecenie lekarskie (sekcja 10)."},
    "msg_validation_final_assessment_required": {"de": "Vor der Veröffentlichung muss die ärztliche Gesamteinschätzung (Sektion 11) gewählt werden.", "en": "Before publishing, please select final medical assessment (section 11).", "pl": "Przed publikacją należy wybrać końcową ocenę lekarską (sekcja 11)."},
    "btn_retry_processing": {"de": "Erneut versuchen", "en": "Retry", "pl": "Ponów"},
    "btn_refresh_status": {"de": "Aktualisieren", "en": "Refresh", "pl": "Odśwież"},
    "lang_de": {"de": "DE", "en": "DE", "pl": "DE"},
    "lang_en": {"de": "EN", "en": "EN", "pl": "EN"},
    "lang_pl": {"de": "PL", "en": "PL", "pl": "PL"},
}

FITZPATRICK = {
    "TYPE_I": {"de": "Hauttyp I nach Fitzpatrick", "en": "Fitzpatrick skin type I", "pl": "Typ I wg Fitzpatricka"},
    "TYPE_II": {"de": "Hauttyp II nach Fitzpatrick", "en": "Fitzpatrick skin type II", "pl": "Typ II wg Fitzpatricka"},
    "TYPE_III": {"de": "Hauttyp III nach Fitzpatrick", "en": "Fitzpatrick skin type III", "pl": "Typ III wg Fitzpatricka"},
    "TYPE_IV": {"de": "Hauttyp IV nach Fitzpatrick", "en": "Fitzpatrick skin type IV", "pl": "Typ IV wg Fitzpatricka"},
    "TYPE_V": {"de": "Hauttyp V nach Fitzpatrick", "en": "Fitzpatrick skin type V", "pl": "Typ V wg Fitzpatricka"},
    "TYPE_VI": {"de": "Hauttyp VI nach Fitzpatrick", "en": "Fitzpatrick skin type VI", "pl": "Typ VI wg Fitzpatricka"},
    "TYPE_II_III": {"de": "Hauttyp II–III nach Fitzpatrick", "en": "Fitzpatrick skin type II–III", "pl": "Typ II–III wg Fitzpatricka"},
    "UNDETERMINED": {"de": "Hauttyp nicht eindeutig bestimmbar", "en": "Skin type not clearly determinable", "pl": "Typ skóry nie do jednoznacznego określenia"},
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    for short_key, mapping in DOCTOR_UI.items():
        full_key = f"doctor.{short_key}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "doctor",
                "description": "Doctor UI translation",
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

    for code, mapping in FITZPATRICK.items():
        full_key = f"doctor.fitzpatrick.{code}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "doctor",
                "description": "Fitzpatrick label",
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
    doctor_keys = [f"doctor.{k}" for k in DOCTOR_UI]
    fitz_keys = [f"doctor.fitzpatrick.{k}" for k in FITZPATRICK]
    TranslationKey.objects.filter(key__in=doctor_keys + fitz_keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_seed_doctor_validation_messages"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
