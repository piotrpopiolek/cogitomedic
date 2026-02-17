# Plan REST API

## 0. Założenia
- Bazowa ścieżka API to `/api/v1`.
- Bazowy runtime backendu to **Django 6.0.x**.
- Zadania tła są definiowane przez **Django Tasks** (`django.tasks`) i orkiestrację przez Transactional Outbox.
- **Języki portalu:** interfejs użytkownika (panel personelu i tablet pacjenta) jest dostępny w języku **angielskim** i **niemieckim**. Użytkownik personelu ma pole `preferred_locale` (np. `en-GB`, `de-DE`); dla tabletu pacjenta język może wynikać z parametru w linku, nagłówka Accept-Language lub domyślnego ustawienia placówki.
- Komunikacja tylko przez HTTPS.
- Domyślny format payloadu to JSON (`application/json`), z wyjątkiem endpointów uploadu plików (`multipart/form-data`).
- Uwierzytelnianie: sesja dla panelu personelu (cookie Django + CSRF) oraz token bearer dla linków pacjenta/tabletu.
- Format czasu: ISO 8601 UTC.
- Wszystkie endpointy listujące wspierają paginację/filtrowanie/sortowanie przez wspólne parametry:
  - `page` (domyślnie `1`)
  - `page_size` (domyślnie `20`, maks. `100`)
  - `ordering` (lista pól po przecinku, prefiks `-` dla malejąco)
  - parametry filtrowania specyficzne dla zasobu

## 1. Zasoby
- `auth` -> `staff_user` (logowanie, wylogowanie, bieżąca sesja, dostęp wg roli)
- `staff-users` -> `staff_user`
- `patients` -> `patient`
- `patient-contact-history` -> `patient_contact_history`
- `clinic-sites` -> `clinic_site`
- `consulting-rooms` -> `consulting_room`
- `daily-queues` -> `daily_queue`
- `queue-entries` -> `queue_entry`
- `tablet-devices` -> `tablet_device`
- `patient-sessions` -> `patient_form_session` (cykl życia tokenu jednorazowego, latest-wins)
- `consent-definitions` -> `consent_definition`
- `anamnesis-definitions` -> `anamnesis_question_definition`, `anamnesis_option_definition`
- `intake-forms` -> `patient_intake_form`
- `intake-consents` -> `patient_intake_consent`
- `medical-documents` -> `medical_document`
- `medical-document-versions` -> `medical_document_version`
- `doctor-text-templates` -> `doctor_text_template` (MVP: tylko prywatne)
- `imports` -> `patient_import_batch`, `patient_import_error`
- `outbox-events` -> `outbox_event`
- `audit-events` -> `audit_event`
- `operations` -> akcje domenowe niebędące czystym CRUD (publikacja, merge, retry, retencja)
- `observability` -> ekspozycja metryk i health-checków

## 2. Endpointy

### 2.1 Auth

- **POST** `/auth/login`
  - Opis: Logowanie personelu (US-001).
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "username": "reception1",
      "password": "********"
    }
    ```
  - Response JSON:
    ```json
    {
      "user": {
        "id": "uuid",
        "username": "reception1",
        "first_name": "Anna",
        "last_name": "Nowak",
        "role": "RECEPTION",
        "preferred_locale": "de-DE"
      },
      "session_expires_at": "2026-02-16T12:00:00Z"
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `401 INVALID_CREDENTIALS`, `429 TOO_MANY_ATTEMPTS`.

- **POST** `/auth/logout`
  - Opis: Kończy aktywną sesję.
  - Parametry zapytania: brak.
  - Request JSON: `{}`.
  - Response JSON: `{"message": "Logged out"}`.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `401 UNAUTHENTICATED`.

- **GET** `/auth/me`
  - Opis: Zwraca aktualnie uwierzytelnionego użytkownika personelu i jego uprawnienia.
  - Parametry zapytania: brak.
  - Request JSON: brak.
  - Response JSON:
    ```json
    {
      "id": "uuid",
      "username": "doctor1",
      "role": "DOCTOR",
      "permissions": ["queue.read", "document.publish"]
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `401 UNAUTHENTICATED`.

### 2.2 Użytkownicy personelu (Admin)

- **GET** `/staff-users`
  - Opis: Lista użytkowników.
  - Parametry zapytania: `role`, `is_active`, `search`.
  - Request JSON: brak.
  - Response JSON:
    ```json
    {
      "items": [
        {
          "id": "uuid",
          "username": "admin1",
          "email": "admin@example.com",
          "role": "ADMIN",
          "is_active": true
        }
      ],
      "pagination": {"page": 1, "page_size": 20, "total": 1}
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **POST** `/staff-users`
  - Opis: Tworzy użytkownika.
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "username": "reception2",
      "email": "r2@example.com",
      "first_name": "Maria",
      "last_name": "Klein",
      "phone_number": "+49123456789",
      "role": "RECEPTION",
      "is_staff": true,
      "is_active": true,
      "password": "StrongPassword123!"
    }
    ```
  - Response JSON: obiekt utworzonego użytkownika.
  - Kody sukcesu: `201 CREATED`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 DUPLICATE_USERNAME_OR_EMAIL`, `403 FORBIDDEN`.

- **GET** `/staff-users/{id}`
- **PATCH** `/staff-users/{id}`
- **DELETE** `/staff-users/{id}`
  - Opis: Odczyt/aktualizacja/dezaktywacja użytkownika (`DELETE` jako soft-delete przez `is_active=false`).
  - Parametry zapytania: brak.
  - Request JSON (`PATCH`): częściowa aktualizacja pól (poza niezmiennymi identyfikatorami).
  - Response JSON: obiekt użytkownika / `{"message":"User deactivated"}`.
  - Kody sukcesu: `200 OK`, opcjonalnie `204 NO_CONTENT` dla delete.
  - Kody błędów: `400 VALIDATION_ERROR`, `403 FORBIDDEN`, `404 NOT_FOUND`.

### 2.3 Pacjenci

- **GET** `/patients`
  - Opis: Wyszukiwanie/listowanie pacjentów.
  - Parametry zapytania: `search`, `last_name`, `date_of_birth`, `phone`, `identity_status`, `doctolib_patient_id`, `is_active`.
  - Request JSON: brak.
  - Response JSON:
    ```json
    {
      "items": [
        {
          "id": "uuid",
          "first_name": "Jan",
          "last_name": "Kowalski",
          "date_of_birth": "1980-01-01",
          "phone": "+49111111111",
          "email": "jan@example.com",
          "doctolib_patient_id": null,
          "identity_status": "TEMPORARY",
          "identity_alert_created_at": "2026-02-16T09:00:00Z",
          "identity_resolution_due_at": "2026-02-17T09:00:00Z"
        }
      ],
      "pagination": {"page": 1, "page_size": 20, "total": 1}
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **POST** `/patients`
  - Opis: Tworzy pacjenta (ścieżka manualna wspiera tożsamość tymczasową).
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "first_name": "Jan",
      "last_name": "Kowalski",
      "date_of_birth": "1980-01-01",
      "phone": "+49111111111",
      "email": "jan@example.com",
      "doctolib_patient_id": null,
      "street": "Main 1",
      "city": "Berlin",
      "postal_code": "10115",
      "country_code": "DE",
      "external_source": "MANUAL",
      "external_source_id": "frontdesk-20260216-001"
    }
    ```
  - Response JSON:
    ```json
    {
      "patient": {"id": "uuid", "identity_status": "TEMPORARY"},
      "identity_alert": {"created": true, "due_at": "2026-02-17T09:00:00Z"}
    }
    ```
  - Kody sukcesu: `201 CREATED`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 DUPLICATE_EXTERNAL_SOURCE`, `422 INVALID_BUSINESS_STATE`.

- **GET** `/patients/{id}`
- **PATCH** `/patients/{id}`
  - Opis: Odczyt/aktualizacja pacjenta.
  - Parametry zapytania: brak.
  - Request JSON (`PATCH`): mutowalne pola demograficzne/kontaktowe.
  - Response JSON: obiekt pacjenta.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `409 UNIQUE_CONSTRAINT`.

- **POST** `/patients/{id}/merge`
  - Opis: Merge rekordu tymczasowego do potwierdzonego (US-018).
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "target_patient_id": "uuid-confirmed",
      "source_action": "ARCHIVE",
      "reason": "Matched by Doctolib ID after import"
    }
    ```
  - Response JSON:
    ```json
    {
      "merged": true,
      "source_patient_id": "uuid-temp",
      "target_patient_id": "uuid-confirmed",
      "moved_entities": {
        "queue_entries": 3,
        "intake_forms": 2,
        "medical_documents": 2
      },
      "identity_alert_closed": true
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `409 MERGE_CONFLICT`, `422 SOURCE_NOT_TEMPORARY`.

- **GET** `/patients/{id}/contact-history`
  - Opis: Oś czasu zmian danych kontaktowych.
  - Parametry zapytania: tylko paginacja.
  - Request JSON: brak.
  - Response JSON:
    ```json
    {
      "items": [
        {
          "id": "uuid",
          "phone": "+49111111111",
          "email": "old@example.com",
          "changed_at": "2026-02-15T10:00:00Z",
          "changed_by_user_id": "uuid",
          "reason": "manual correction"
        }
      ]
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`, `403 FORBIDDEN`.

### 2.4 Placówki i gabinety

- **GET** `/clinic-sites`, **POST** `/clinic-sites`, **GET/PATCH/DELETE** `/clinic-sites/{id}`
  - Opis: CRUD dla lokalizacji (słownik admina).
  - Parametry zapytania: `is_active`, `search`.
  - Request JSON (create/update):
    ```json
    {
      "code": "BERLIN-1",
      "name": "Berlin Central",
      "is_active": true
    }
    ```
  - Response JSON: obiekt placówki.
  - Kody sukcesu: `200 OK`, `201 CREATED`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 DUPLICATE_CODE`, `403 FORBIDDEN`.

- **GET** `/consulting-rooms`, **POST** `/consulting-rooms`, **GET/PATCH/DELETE** `/consulting-rooms/{id}`
  - Opis: CRUD dla gabinetów per placówka.
  - Parametry zapytania: `clinic_site_id`, `is_active`, `search`.
  - Request JSON (create/update):
    ```json
    {
      "clinic_site_id": "uuid",
      "code": "R01",
      "name": "Room 1",
      "is_active": true
    }
    ```
  - Response JSON: obiekt gabinetu.
  - Kody sukcesu: `200 OK`, `201 CREATED`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 DUPLICATE_ROOM_CODE_PER_SITE`, `404 CLINIC_SITE_NOT_FOUND`.

### 2.5 Listy dzienne i wpisy kolejki (Recepcja)

- **GET** `/daily-queues`
  - Opis: Lista kolejek wg daty/placówki/gabinetu/zmiany.
  - Parametry zapytania: `queue_date`, `clinic_site_id`, `consulting_room_id`, `shift_code`, `status`.
  - Request JSON: brak.
  - Response JSON:
    ```json
    {
      "items": [
        {
          "id": "uuid",
          "queue_date": "2026-02-16",
          "clinic_site_id": "uuid",
          "consulting_room_id": "uuid",
          "shift_code": "FULL_DAY",
          "status": "OPEN"
        }
      ]
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`.

- **POST** `/daily-queues`
  - Opis: Tworzy kolejkę dla daty/placówki/gabinetu/zmiany.
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "queue_date": "2026-02-16",
      "clinic_site_id": "uuid",
      "consulting_room_id": "uuid",
      "shift_code": "FULL_DAY",
      "source": "MANUAL"
    }
    ```
  - Response JSON: obiekt kolejki.
  - Kody sukcesu: `201 CREATED`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 DUPLICATE_QUEUE`.

- **PATCH** `/daily-queues/{id}`
  - Opis: Aktualizacja statusu kolejki (`OPEN`/`CLOSED`).
  - Request JSON:
    ```json
    {
      "status": "CLOSED"
    }
    ```
  - Response JSON: obiekt kolejki.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `409 INVALID_STATE_TRANSITION`, `404 NOT_FOUND`.

- **GET** `/daily-queues/{id}/entries`
  - Opis: Lista wpisów kolejki w poczekalni.
  - Parametry zapytania: `entry_status`, `patient_id`, `ordering` (domyślnie `position_no`).
  - Request JSON: brak.
  - Response JSON: lista wpisów.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`.

- **POST** `/daily-queues/{id}/entries`
  - Opis: Dodaje pacjenta do kolejki (manualny przepływ recepcji).
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "patient_id": "uuid",
      "visit_external_id": null,
      "appointment_time": "2026-02-16T10:30:00Z",
      "notes": "Follow-up visit"
    }
    ```
  - Response JSON: utworzony wpis z nadanym `position_no`.
  - Kody sukcesu: `201 CREATED`.
  - Kody błędów: `400 VALIDATION_ERROR`, `404 QUEUE_OR_PATIENT_NOT_FOUND`, `409 UNIQUE_VISIT_EXTERNAL_ID`.

- **GET/PATCH/DELETE** `/queue-entries/{id}`
  - Opis: Odczyt/aktualizacja/anulowanie wpisu kolejki.
  - Parametry zapytania: brak.
  - Request JSON (`PATCH`):
    ```json
    {
      "entry_status": "IN_PROGRESS",
      "notes": "Patient moved to room"
    }
    ```
  - Response JSON: obiekt wpisu.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `409 INVALID_STATE_TRANSITION`.

### 2.6 Urządzenia tabletowe

- **GET** `/tablet-devices`, **POST** `/tablet-devices`, **GET/PATCH/DELETE** `/tablet-devices/{id}`
  - Opis: Zarządzanie dedykowanymi tabletami.
  - Parametry zapytania: `is_active`, `search`.
  - Request JSON:
    ```json
    {
      "name": "Tablet-1",
      "device_code": "TAB001",
      "is_active": true
    }
    ```
  - Response JSON: obiekt tabletu.
  - Kody sukcesu: `200 OK`, `201 CREATED`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 DUPLICATE_DEVICE`.

- **POST** `/tablet-devices/{id}/heartbeat`
  - Opis: Aktualizuje `last_seen_at` urządzenia.
  - Request JSON: `{}`.
  - Response JSON: `{"last_seen_at":"2026-02-16T10:00:00Z"}`.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`.

### 2.7 Sesje pacjenta i przepływ tokenu (latest-wins)

- **POST** `/queue-entries/{id}/sessions`
  - Opis: Generuje jednorazowy link/token pacjenta i ustawia go jako aktywną sesję (US-004).
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "tablet_device_id": "uuid",
      "ttl_minutes": 30,
      "form_locale": "de-DE"
    }
    ```
  - Response JSON:
    ```json
    {
      "session_id": "uuid",
      "launch_url": "https://app.example.com/patient/form?token=opaque-token",
      "expires_at": "2026-02-16T10:30:00Z"
    }
    ```
  - Kody sukcesu: `201 CREATED`.
  - Kody błędów: `404 QUEUE_ENTRY_NOT_FOUND`, `409 ENTRY_NOT_ELIGIBLE`, `422 TOKEN_GENERATION_FAILED`.

- **POST** `/patient-sessions/validate`
  - Opis: Waliduje token przed wejściem do formularza na tablecie.
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "token": "opaque-token"
    }
    ```
  - Response JSON:
    ```json
    {
      "valid": true,
      "session_id": "uuid",
      "queue_entry_id": "uuid",
      "form_locale": "de-DE",
      "patient_snapshot": {
        "first_name": "Jan",
        "last_name": "Kowalski",
        "date_of_birth": "1980-01-01",
        "phone": "+49111111111",
        "email": "jan@example.com"
      }
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `401 TOKEN_INVALID_OR_EXPIRED`, `409 TOKEN_NOT_ACTIVE_SESSION`, `410 TOKEN_CONSUMED`.

### 2.8 Definicje zgód (słownik Admin)

- **GET** `/consent-definitions`
  - Opis: Lista zgód z filtrowaniem aktywności i okresu obowiązywania.
  - Parametry zapytania: `is_active`, `effective_on`, `code`.
  - Request JSON: brak.
  - Response JSON: lista definicji zgód.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **POST** `/consent-definitions`
- **GET/PATCH/DELETE** `/consent-definitions/{id}`
  - Opis: CRUD dla wersji zgód.
  - Request JSON (create):
    ```json
    {
      "code": "PRIVACY",
      "version": 3,
      "title_de": "Datenschutz",
      "content_de": "....",
      "is_required": true,
      "is_active": true,
      "display_order": 1,
      "effective_from": "2026-02-16",
      "effective_to": null
    }
    ```
  - Response JSON: obiekt zgody.
  - Kody sukcesu: `201 CREATED`, `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 DUPLICATE_CODE_VERSION`, `403 FORBIDDEN`.

### 2.8a Definicje pytań anamnestycznych (słownik Admin)

- **GET** `/anamnesis-definitions`
  - Opis: Lista pytań anamnestycznych i opcji odpowiedzi (DE/EN) aktywnych dla daty.
  - Parametry zapytania: `is_active`, `effective_on`, `locale` (`de-DE`|`en-GB`|`en-US`), `code`.
  - Request JSON: brak.
  - Response JSON:
    ```json
    {
      "schema_version": 1,
      "items": [
        {
          "question_code": "Q1_MALIGNANT_MELANOMA_HISTORY",
          "question_text": "Wurde bei Ihnen jemals ein malignes Melanom diagnostiziert?",
          "answer_type": "SINGLE_CHOICE",
          "is_required": true,
          "options": [
            {"option_code": "NO", "label": "Nein"},
            {"option_code": "YES", "label": "Ja"}
          ]
        }
      ]
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **POST** `/anamnesis-definitions`
- **GET/PATCH/DELETE** `/anamnesis-definitions/{id}`
  - Opis: CRUD definicji pytań i opcji anamnestycznych.
  - Kody sukcesu: `201 CREATED`, `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 DUPLICATE_CODE_VERSION`, `403 FORBIDDEN`.

### 2.9 Formularze intake i zgody (Tablet)

- **GET** `/intake-forms/by-session/{session_id}`
  - Opis: Pobiera lub inicjalizuje kontekst formularza intake dla tabletu pacjenta.
  - Parametry zapytania: brak.
  - Request JSON: brak.
  - Response JSON:
    ```json
    {
      "intake_form_id": "uuid",
      "queue_entry_id": "uuid",
      "form_status": "IN_PROGRESS",
      "form_locale": "de-DE",
      "anamnesis_schema_version": 1,
      "anamnesis_questions": [
        {
          "question_code": "Q1_MALIGNANT_MELANOMA_HISTORY",
          "question_text": "Wurde bei Ihnen jemals ein malignes Melanom diagnostiziert?",
          "answer_type": "SINGLE_CHOICE",
          "is_required": true,
          "options": [
            {"option_code": "NO", "label": "Nein"},
            {"option_code": "YES", "label": "Ja"}
          ],
          "answer": {"selected_option_codes": []}
        }
      ],
      "body_map_schema_version": 1,
      "body_map_data": [],
      "consents": [
        {
          "consent_definition_id": "uuid",
          "code": "PRIVACY",
          "title_de": "Datenschutz",
          "is_required": true,
          "accepted": false
        }
      ]
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `401 TOKEN_INVALID_OR_EXPIRED`, `404 SESSION_NOT_FOUND`.

- **PATCH** `/intake-forms/{id}`
  - Opis: Zapisuje robocze dane schematu ciała i opcjonalny szkic podpisu.
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "body_map_schema_version": 1,
      "body_map_data": [
        {"x": 0.42, "y": 0.31, "side": "front", "label": "pain"}
      ]
    }
    ```
  - Response JSON: zaktualizowany formularz.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 INVALID_JSON_SCHEMA`, `401 TOKEN_INVALID_OR_EXPIRED`, `409 FORM_ALREADY_SUBMITTED`.

- **PUT** `/intake-forms/{id}/consents`
  - Opis: Podmienia zestaw akceptacji zgód dla formularza intake.
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "consents": [
        {"consent_definition_id": "uuid1", "accepted": true},
        {"consent_definition_id": "uuid2", "accepted": false}
      ]
    }
    ```
  - Response JSON:
    ```json
    {
      "intake_form_id": "uuid",
      "consents": [
        {"consent_definition_id": "uuid1", "accepted": true, "accepted_at": "2026-02-16T10:01:00Z"}
      ]
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 CONSENT_NOT_ACTIVE_FOR_DATE`.

- **PUT** `/intake-forms/{id}/anamnesis`
  - Opis: Podmienia odpowiedzi ankiety anamnestycznej dla formularza intake.
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "anamnesis_schema_version": 1,
      "answers": [
        {"question_code": "Q1_MALIGNANT_MELANOMA_HISTORY", "selected_option_codes": ["NO"]},
        {"question_code": "Q3_FAMILY_MELANOMA", "selected_option_codes": ["UNKNOWN"]},
        {
          "question_code": "Q4_NEW_SKIN_CHANGES_LOCATION",
          "selected_option_codes": ["YES", "LOWER_BACK"],
          "free_text": "other location description",
          "body_map_points": [{"x": 0.42, "y": 0.31, "side": "front"}]
        }
      ]
    }
    ```
  - Response JSON:
    ```json
    {
      "intake_form_id": "uuid",
      "anamnesis_schema_version": 1,
      "answers_saved": true
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 INVALID_JSON_SCHEMA`, `400 UNKNOWN_QUESTION_OR_OPTION_CODE`, `409 FORM_ALREADY_SUBMITTED`.

- **POST** `/intake-forms/{id}/signature`
  - Opis: Upload podpisu pacjenta.
  - Parametry zapytania: brak.
  - Request JSON (wariant base64):
    ```json
    {
      "signature_base64": "data:image/png;base64,..."
    }
    ```
  - Response JSON:
    ```json
    {
      "signature_file_path": "signatures/2026/02/uuid.png",
      "signature_sha256": "64-hex"
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 INVALID_SIGNATURE`, `413 PAYLOAD_TOO_LARGE`, `409 FORM_ALREADY_SUBMITTED`.

- **POST** `/intake-forms/{id}/submit`
  - Opis: Finalizuje formularz i zużywa token w jednej transakcji (US-005/006/007).
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "session_token": "opaque-token"
    }
    ```
  - Response JSON:
    ```json
    {
      "submitted": true,
      "form_status": "SUBMITTED",
      "submitted_at": "2026-02-16T10:05:00Z",
      "queue_entry_status": "PATIENT_COMPLETED"
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 REQUIRED_CONSENTS_MISSING`, `400 REQUIRED_ANAMNESIS_MISSING`, `400 SIGNATURE_REQUIRED`, `401 TOKEN_INVALID_OR_EXPIRED`, `409 FORM_ALREADY_SUBMITTED`.

### 2.10 Dokumenty medyczne i workflow lekarza

- **GET** `/medical-documents`
  - Opis: Lista robocza lekarza.
  - Parametry zapytania: `status`, `queue_date`, `doctor_view` (`pending_review`, `published`, `failed`), `patient_search`.
  - Request JSON: brak.
  - Response JSON: stronicowana lista dokumentów z flagami statusu ostatniej wersji (`pdf_generation_status`, `hidrive_sent`, `sms_sent`).
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **GET** `/medical-documents/{id}`
  - Opis: Pełny kontekst dokumentu (intake pacjenta + medyczny draft/aktualna wersja).
  - Parametry zapytania: `include_versions=true|false`.
  - Response JSON:
    ```json
    {
      "id": "uuid",
      "queue_entry_id": "uuid",
      "status": "DRAFT",
      "current_version_no": 2,
      "intake_summary": {
        "consents": [{"code": "PRIVACY", "accepted": true}],
        "body_map_data": [],
        "anamnesis_answers": [
          {"question_code": "Q1_MALIGNANT_MELANOMA_HISTORY", "selected_option_codes": ["NO"]}
        ]
      },
      "current_version": {
        "version_no": 2,
        "version_status": "DRAFT",
        "medical_payload_schema_version": 1,
        "medical_payload": {
          "authoring_locale": "de-DE",
          "fitzpatrick_type": "TYPE_III",
          "lesions": []
        },
        "diagnosis_code": null,
        "procedure_code": null
      }
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`, `403 FORBIDDEN`.

- **POST** `/medical-documents`
  - Opis: Tworzy dokument dla wpisu kolejki, jeśli nie istnieje.
  - Request JSON:
    ```json
    {
      "queue_entry_id": "uuid"
    }
    ```
  - Response JSON: utworzony lub istniejący dokument.
  - Kody sukcesu: `201 CREATED` lub `200 OK` (idempotentnie).
  - Kody błędów: `404 QUEUE_ENTRY_NOT_FOUND`, `409 INTAKE_NOT_SUBMITTED`.

- **PATCH** `/medical-documents/{id}/draft`
  - Opis: Zapisuje szkic części medycznej (US-008/009).
  - Request JSON:
    ```json
    {
      "medical_payload_schema_version": 1,
      "medical_payload": {
        "authoring_locale": "de-DE",
        "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
        "fitzpatrick_type": "TYPE_III",
        "overall_image_assessment": "CONTROL_NEEDED",
        "lesions": [
          {
            "lesion_no": 8,
            "dermatoscopic_features": ["ASYMMETRY", "INHOMOGENEOUS_PIGMENTATION"],
            "clinical_assessment": "CONTROL_NEEDED",
            "malignancy_risk": "NO_SUSPICION",
            "generated_text": "Läsion Nr. 8 zeigt dermatoskopisch Asymmetrie ...",
            "edited_text": "Läsion Nr. 8 zeigt dermatoskopisch Asymmetrie ..."
          }
        ],
        "recommendations": ["FOLLOWUP_3_MONTHS"],
        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        "summary_generated_text": "Bei der Analyse ...",
        "summary_edited_text": "Bei der Analyse ...",
        "template_context": {
          "template_id": "uuid",
          "template_name": "Dr. Meyer Default",
          "template_locale": "de-DE"
        }
      },
      "diagnosis_code": "M54.5",
      "procedure_code": "PROC-001"
    }
    ```
  - Response JSON: najnowsza wersja szkicu.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 INVALID_JSON_SCHEMA`, `400 REQUIRED_MEDICAL_FIELDS_MISSING`, `400 INVALID_TEXT_CONTENT`, `409 DOCUMENT_NOT_EDITABLE`.
  - Uwagi:
    - `generated_text` i `edited_text` przyjmują wyłącznie plain text (bez znaczników HTML/JS).
    - Logika zapisu po stronie backendu nigdy automatycznie nie nadpisuje `edited_text`.

- **POST** `/medical-documents/{id}/generate-text`
  - Opis: Generuje teksty bazowe Befund na podstawie zaznaczonych opcji (per zmiana + podsumowanie globalne), bez publikacji; domyślnie zachowuje istniejące ręczne edycje.
  - Request JSON:
    ```json
    {
      "medical_payload_schema_version": 1,
      "authoring_locale": "de-DE",
      "template_id": "uuid-optional",
      "preserve_existing_edited_text": true,
      "medical_payload": {
        "fitzpatrick_type": "TYPE_III",
        "lesions": [
          {
            "lesion_no": 8,
            "dermatoscopic_features": ["ASYMMETRY", "INHOMOGENEOUS_PIGMENTATION"],
            "clinical_assessment": "CONTROL_NEEDED",
            "malignancy_risk": "NO_SUSPICION"
          }
        ],
        "recommendations": ["FOLLOWUP_3_MONTHS"],
        "final_assessment": "NO_HIGH_GRADE_SUSPICION"
      }
    }
    ```
  - Response JSON:
    ```json
    {
      "generated": true,
      "edited_text_preserved": true,
      "lesions": [
        {
          "lesion_no": 8,
          "generated_text": "Läsion Nr. 8 zeigt dermatoskopisch Asymmetrie ...",
          "edited_text_unchanged": true
        }
      ],
      "summary_generated_text": "Bei der Analyse der digitalen dermatoskopischen Aufnahmen ..."
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 INVALID_MEDICAL_SELECTIONS`, `400 TEMPLATE_PLACEHOLDER_NOT_ALLOWED`, `404 DOCUMENT_NOT_FOUND`.
  - Uwagi:
    - Domyślne zachowanie to `preserve_existing_edited_text=true`.
    - Tryb nadpisania wymaga jawnej zgody klienta (`preserve_existing_edited_text=false`) i jawnego potwierdzenia w UI.

- **POST** `/medical-documents/{id}/publish`
  - Opis: Publikuje wersję dokumentu i idempotentnie kolejkuje łańcuch outbox (US-009/010).
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "publish_request_id": "uuid-or-client-key",
      "doctor_final_sign_off": true,
      "resend_sms": true
    }
    ```
  - Response JSON:
    ```json
    {
      "published": true,
      "idempotent_replay": false,
      "doctor_final_sign_off": true,
      "doctor_final_sign_off_at": "2026-02-16T10:07:00Z",
      "medical_document_id": "uuid",
      "version_no": 3,
      "version_status": "PUBLISHED",
      "outbox": [
        {"event_type": "GENERATE_PDF", "status": "PENDING"}
      ]
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `400 FINAL_SIGN_OFF_REQUIRED`, `409 PUBLICATION_IN_PROGRESS`, `422 BUSINESS_RULE_VIOLATION`.

### 2.10a Szablony tekstów lekarskich

- **GET** `/doctor-text-templates`
  - Opis: Lista prywatnych szablonów tekstu dostępnych dla uwierzytelnionego lekarza (MVP: tylko prywatne).
  - Parametry zapytania: `template_locale`, `is_active`.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **POST** `/doctor-text-templates`
- **GET/PATCH/DELETE** `/doctor-text-templates/{id}`
  - Opis: CRUD prywatnych szablonów tekstowych lekarza (bez zakresu globalnego).
  - Request JSON (create):
    ```json
    {
      "name": "Dr. Meyer Default",
      "template_locale": "de-DE",
      "template_body": "Läsion {{lesion_no}} zeigt ...",
      "is_active": true
    }
    ```
  - Kody sukcesu: `201 CREATED`, `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `400 TEMPLATE_PLACEHOLDER_NOT_ALLOWED`, `400 INVALID_TEXT_CONTENT`, `403 FORBIDDEN`, `409 TEMPLATE_NAME_CONFLICT`.
  - Uwagi:
    - Treść szablonu to wyłącznie plain text (bez HTML/JS).
    - Placeholdery są obsługiwane wyłącznie z allowlisty (bez logiki warunkowej, pętli i DSL).

- **GET** `/medical-documents/{id}/versions`
  - Opis: Historia wersji.
  - Parametry zapytania: paginacja/sortowanie po `-version_no`.
  - Response JSON: lista wersji.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`.

- **GET** `/medical-document-versions/{id}`
  - Opis: Szczegóły wskazanej wersji i stan przetwarzania.
  - Response JSON: obiekt wersji z flagami PDF/HiDrive/SMS.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`.

### 2.11 Importy (manualny, harmonogram, awaryjny)

- **POST** `/imports/patients`
  - Opis: Upload `.csv/.xlsx` dla importu dziennego (US-003/011/015).
  - Parametry zapytania: `mode` (`daily` lub `scheduled`).
  - Request: `multipart/form-data` z plikiem.
  - Response JSON:
    ```json
    {
      "batch_id": "uuid",
      "status": "PROCESSING",
      "source_system": "DOCTOLIB_EXPORT"
    }
    ```
  - Kody sukcesu: `202 ACCEPTED`.
  - Kody błędów: `400 INVALID_FILE_FORMAT`, `422 TEMPLATE_MISMATCH`, `403 FORBIDDEN`.

- **POST** `/imports/patients/emergency`
  - Opis: Ścieżka awaryjnego importu ze sztywnego szablonu (US-017).
  - Parametry zapytania: brak.
  - Request: `multipart/form-data` z plikiem zgodnym ze szablonem.
  - Response JSON: obiekt batcha.
  - Kody sukcesu: `202 ACCEPTED`.
  - Kody błędów: `400 INVALID_TEMPLATE`, `422 MISSING_DOCTOLIB_ID`, `403 FORBIDDEN`.

- **GET** `/imports/batches`
  - Opis: Lista batchy importu.
  - Parametry zapytania: `status`, `source_system`, `import_type`, `created_from`, `created_to`.
  - Response JSON: lista batchy.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **GET** `/imports/batches/{id}`
  - Opis: Szczegóły batcha.
  - Response JSON:
    ```json
    {
      "id": "uuid",
      "source_file_name": "export_20260216.csv",
      "status": "COMPLETED_WITH_ERRORS",
      "total_rows": 120,
      "inserted_rows": 115,
      "error_rows": 5,
      "finished_at": "2026-02-16T08:15:00Z"
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`.

- **GET** `/imports/batches/{id}/errors`
  - Opis: Raport błędów na poziomie wiersza.
  - Parametry zapytania: paginacja.
  - Response JSON:
    ```json
    {
      "items": [
        {
          "row_number": 14,
          "error_code": "MISSING_DOCTOLIB_ID",
          "error_message": "doctolib_id is required"
        }
      ]
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`.

- **GET** `/imports/templates/emergency.xlsx`
  - Opis: Pobiera awaryjny szablon importu.
  - Parametry zapytania: brak.
  - Request JSON: brak.
  - Response: plik binarny.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 TEMPLATE_NOT_FOUND`.

### 2.12 Outbox i operacje (Admin/Ops)

- **GET** `/outbox-events`
  - Opis: Operacyjny widok kolejki outbox.
  - Parametry zapytania: `status`, `event_type`, `available_before`, `retry_count_gte`.
  - Request JSON: brak.
  - Response JSON: lista zdarzeń outbox.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **POST** `/outbox-events/{id}/retry`
  - Opis: Wymusza retry dla zdarzenia failed/dead-letter.
  - Request JSON:
    ```json
    {
      "reason": "manual retry after provider recovery"
    }
    ```
  - Response JSON: zaktualizowane zdarzenie.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `409 EVENT_NOT_RETRYABLE`, `404 NOT_FOUND`, `403 FORBIDDEN`.

- **POST** `/operations/outbox/process`
  - Opis: Ręczne uruchomienie cyklu workera outbox (bezpieczny endpoint admina).
  - Request JSON:
    ```json
    {
      "limit": 100
    }
    ```
  - Response JSON:
    ```json
    {
      "processed": 80,
      "failed": 2,
      "remaining_pending": 15
    }
    ```
  - Kody sukcesu: `202 ACCEPTED`.
  - Kody błędów: `403 FORBIDDEN`, `429 RATE_LIMITED`.

- **POST** `/operations/retention/run`
  - Opis: Ręczne uruchomienie retencji lokalnych PDF starszych niż 30 dni.
  - Request JSON:
    ```json
    {
      "dry_run": true,
      "older_than_days": 30
    }
    ```
  - Response JSON:
    ```json
    {
      "candidates": 42,
      "deleted": 0,
      "skipped_not_safe": 5
    }
    ```
  - Kody sukcesu: `202 ACCEPTED`.
  - Kody błędów: `403 FORBIDDEN`.

### 2.13 Audyt i obserwowalność

- **GET** `/audit-events`
  - Opis: Zapytania do śladu audytowego.
  - Parametry zapytania: `event_type`, `actor_user_id`, `patient_id`, `medical_document_id`, `from`, `to`.
  - Response JSON: lista zdarzeń audytowych.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **GET** `/observability/health`
  - Opis: Liveness/readiness aplikacji, DB, workera i integracji.
  - Response JSON:
    ```json
    {
      "status": "ok",
      "checks": {
        "db": "ok",
        "outbox_worker": "ok",
        "hidrive": "degraded",
        "sms": "ok"
      }
    }
    ```
  - Kody sukcesu: `200 OK` / `503 SERVICE_UNAVAILABLE`.
  - Kody błędów: brak.

- **GET** `/observability/metrics`
  - Opis: Endpoint metryk (Prometheus/OpenTelemetry exporter bridge) zawierający wymagane liczniki i opóźnienia z PRD.
  - Response: tekstowy payload metryk.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN` (jeśli poza siecią wewnętrzną).

## 3. Uwierzytelnianie i autoryzacja

- Uwierzytelnianie:
  - Staff API: sesja Django oparta na cookie, secure/httponly/samesite, CSRF dla żądań mutujących.
  - Przepływ pacjenta na tablecie: podpisany token jednorazowy walidowany względem `patient_form_session.token_hash`.
  - Token jest ważny tylko gdy spełnione są wszystkie warunki:
    - hash tokenu pasuje do aktywnej sesji;
    - `session.id == queue_entry.active_session_id`;
    - `consumed_at IS NULL`;
    - `expires_at > now()`.

- Autoryzacja (RBAC wg `staff_user.role`):
  - `RECEPTION`: kolejki, wpisy kolejki, tworzenie/aktualizacja pacjentów, generacja tokenów, importy read/write.
  - `DOCTOR`: odczyt/zapis dokumentów medycznych, publikacja/republikacja, podgląd wersji.
  - `ADMIN`: zarządzanie użytkownikami, słownik zgód, merge pacjentów, operacje techniczne, pełny podgląd audytu/outbox.
  - Ochrona endpointów przez klasy uprawnień Django + kontrole na poziomie obiektu.

- Kontrole sesji/bezpieczeństwa:
  - Timeout bezczynności egzekwowany po stronie serwera.
  - Ochrona brute-force na `/auth/login` i endpoint walidacji tokenu.
  - HSTS i przekierowanie do HTTPS.
  - Hasła przechowywane wyłącznie przez hashery Django.
  - Brak sekretów w kodzie; konfiguracja przez zmienne środowiskowe.

- Utwardzenie API:
  - Rate limiting (przykładowa polityka):
    - `/auth/login`: 5 req/min/IP + bucket per username.
    - `/patient-sessions/validate`: 30 req/min/IP.
    - endpointy mutujące (domyślnie): 60 req/min/user.
    - operacje administracyjne: 10 req/min/user.
  - Limity rozmiaru żądań dla podpisów/uploadów.
  - Sanityzacja plain-text dla narracji lekarza i treści szablonów przed zapisem/generowaniem PDF.
  - Sanityzacja wejścia i allowlisty dla pól sortowania/filtrowania.
  - Audyt wszystkich akcji bezpieczeństwa (błędy logowania, publikacje, retry, merge, retencja).

## 4. Walidacja i logika biznesowa

### 4.1 Reguły walidacji zasobów

- `staff_user`
  - `username` unikalny, `email` unikalny (case-insensitive), `role` w `RECEPTION|DOCTOR|ADMIN`.
  - `phone_number` regex: `^[0-9+() -]{7,20}$`.

- `patient`
  - Wymagane: `first_name`, `last_name`, `date_of_birth`, `phone`, `email`.
  - `phone` regex: `^[0-9+() -]{7,20}$`.
  - `date_of_birth <= current_date`.
  - `(external_source, external_source_id)` unikalne.
  - Gdy `doctolib_patient_id` jest puste, muszą być ustawione `identity_alert_created_at` i `identity_resolution_due_at`.
  - `identity_resolution_due_at >= identity_alert_created_at`, gdy oba pola istnieją.

- `consulting_room`
  - Unikalność per placówka: `(clinic_site_id, code)`.

- `daily_queue`
  - Klucz unikalny: `(queue_date, clinic_site_id, consulting_room_id, shift_code)`.
  - `(consulting_room_id, clinic_site_id)` musi wskazywać poprawną relację gabinet-placówka.

- `queue_entry`
  - `position_no` unikalne w ramach kolejki.
  - Opcjonalne `visit_external_id` unikalne per kolejka, jeśli ustawione.
  - Status musi przestrzegać dozwolonej maszyny stanów.

- `patient_form_session`
  - `token_hash` unikalny.
  - `expires_at > created_at`.
  - `consumed_at <= expires_at`, jeśli ustawione.

- `consent_definition`
  - Unikalność `(code, version)`.
  - `effective_to >= effective_from`, jeśli ustawione.

- `patient_intake_form`
  - Relacja 1:1 z `queue_entry`.
  - `body_map_data` musi być tablicą JSON.
  - `form_status='SUBMITTED'` wymaga `submitted_at` i `signature_file_path`.

- `patient_intake_consent`
  - Unikalność `(intake_form_id, consent_definition_id)`.
  - `accepted=true` wymaga `accepted_at`; `accepted=false` wymaga `accepted_at=null`.

- `medical_document`
  - Relacja 1:1 z `queue_entry` i `intake_form`.
  - `current_version_no >= 0`.

- `medical_document_version`
  - Unikalność `(medical_document_id, version_no)`.
  - `version_no > 0`.
  - `medical_payload` musi być obiektem JSON.
  - `PUBLISHED` wymaga `publish_request_id` i `published_at`.
  - `pdf_generation_status='COMPLETED'` wymaga `pdf_local_path`.
  - `hidrive_sent=true` wymaga ukończonego PDF, `pdf_local_path` i `hidrive_sent_at`.
  - `sms_sent=true` wymaga `sms_sent_at`.
  - `local_pdf_deleted_at` dozwolone tylko gdy `hidrive_sent=true` i `sms_sent=true`.
  - Publikacja wymaga jawnego `doctor_final_sign_off=true`.

- `outbox_event`
  - Unikalność `(medical_document_version_id, event_type)`.
  - Ograniczenie `retry_count` (`0 <= retry_count <= max_retries`, `max_retries > 0`).
  - `payload` musi być obiektem JSON.
  - `aggregate_type='MEDICAL_DOCUMENT_VERSION'`.
  - `aggregate_id=medical_document_version_id`.

- `patient_import_batch` i `patient_import_error`
  - Nieuemne liczniki w batchu.
  - `row_number > 0` dla rekordów błędów.

- `audit_event`
  - `metadata` musi być obiektem JSON.

### 4.2 Implementacja logiki biznesowej w API

- Manualne dodanie pacjenta wspiera tożsamość tymczasową:
  - Jeśli brak `doctolib_patient_id`, API ustawia znaczniki alertu tożsamości i zwraca metadane alertu.

- Ujednolicona ingestia:
  - Dodanie ręczne, import pliku i autoimport korzystają ze wspólnego serwisu ingestii z tymi samymi walidacjami i deduplikacją.

- Idempotentny import:
  - Wykorzystanie identyfikatorów zewnętrznych (`doctolib_patient_id`, klucze zewnętrzne wizyty) do unikania duplikatów pacjentów/wizyt.

- Model tokenu latest-wins:
  - Generacja sesji tworzy nowy `patient_form_session` i atomowo przełącza `queue_entry.active_session_id`.
  - Starsze tokeny tracą ważność automatycznie.

- Transakcyjny submit intake:
  - Weryfikuje akceptację wymaganych aktywnych zgód.
  - Weryfikuje obecność podpisu.
  - Ustawia formularz na `SUBMITTED`, zapisuje `submitted_at`, zużywa token (`consumed_at`) i aktualizuje status kolejki w jednej transakcji.

- Workflow lekarza:
  - Zapis szkicu aktualizuje/tworzy najnowszą wersję draft.
  - Endpoint `generate-text` tworzy teksty bazowe Befund (`generated_text`) na podstawie wybranych cech/ocen i opcjonalnego prywatnego szablonu lekarza.
  - Regeneracja domyślnie zachowuje istniejące `edited_text` (brak niejawnego nadpisania).
  - Lekarz zapisuje w `medical_payload` zarówno teksty wygenerowane, jak i finalne teksty edytowane (`edited_text`).
  - Każda modyfikacja `edited_text` emituje zdarzenie audytowe (`MEDICAL_TEXT_EDITED`) z aktorem i stemplem czasowym.
  - Publikacja używa locka wiersza na `medical_document` i kontroli idempotencji:
    - ten sam `publish_request_id` zwraca sukces-replay;
    - publikacja już w toku zwraca idempotentny sukces (bez duplikacji łańcucha outbox).
    - publikacja wymaga jawnego potwierdzenia lekarza dla finalnego tekstu narracyjnego.

- Łańcuch transactional outbox:
  - Transakcja publikacji enqueuje `GENERATE_PDF`.
  - Worker po sukcesie PDF enqueuje `HIDRIVE_UPLOAD`.
  - Worker po sukcesie uploadu enqueuje `SMS_SEND`.
  - Retry i dead-letter obsługiwane przez statusy/liczniki outbox.

- Republikacja:
  - Edycja opublikowanego dokumentu tworzy kolejną wersję i uruchamia łańcuch ponownie; ścieżka archiwum jest nadpisywana zgodnie z wymaganiem biznesowym.
  - API wspiera opcjonalny `resend_sms`.

- Polityka retencji:
  - Harmonogram/ręczny job retencji usuwa lokalny PDF tylko gdy `hidrive_sent=true` i `sms_sent=true`, a wiek dokumentu przekracza 30 dni.
  - Akcja usunięcia zapisuje zdarzenie audytowe.

- Widoczność operacyjna:
  - API udostępnia endpointy health/metrics oraz podgląd outbox/importów.
  - Eksportowane są wymagane metryki z PRD (`pending_count`, `failed_count`, `dead_letter_count`, `oldest_pending_age_seconds`, latencje p95/p99, success ratio providerów, error rate importu).

### 4.3 Kontrakt `anamnesis_payload` v1 (Q1–Q11)

- API zwraca i przyjmuje dane anamnezy wyłącznie jako kody (`question_code`, `option_code`), niezależnie od języka DE/EN.
- Lokalizacja (`question_text`, `option label`) jest wykonywana na podstawie `form_locale` i słownika `anamnesis-definitions`.

Minimalny request dla `PUT /intake-forms/{id}/anamnesis`:

```json
{
  "anamnesis_schema_version": 1,
  "answers": [
    {"question_code": "Q1_MALIGNANT_MELANOMA_HISTORY", "selected_option_codes": ["NO"]},
    {"question_code": "Q3_FAMILY_MELANOMA_FIRST_DEGREE", "selected_option_codes": ["UNKNOWN"]},
    {
      "question_code": "Q4B_NEW_SKIN_CHANGES_LOCATION",
      "selected_option_codes": ["LOWER_BACK", "OTHER_LOCATION"],
      "free_text": "right shoulder blade",
      "body_map_points": [{"x": 0.45, "y": 0.34, "side": "back"}]
    }
  ]
}
```

Mapowanie kodów opcji dla Q1–Q11:
- `NO`, `YES`, `UNKNOWN` (pytania binarne i trójwartościowe),
- `LOWER_BACK`, `THORACIC_SPINE`, `ABDOMEN`, `OTHER_LOCATION` (lokalizacja zmian).

### 4.4 Kontrakt `medical_payload` v1 (Befund)

- `medical_payload` przechowuje dane ustrukturyzowane i teksty:
  - dane globalne (`fitzpatrick_type`, `overall_image_assessment`, `recommendations`, `final_assessment`),
  - dane per zmiana (`lesions[]`),
  - teksty wygenerowane i końcowe (`generated_text`, `edited_text`, `summary_generated_text`, `summary_edited_text`).
- Zapis tekstów odbywa się niezależnie od języka UI; `authoring_locale` wskazuje język roboczy lekarza.
- Pola narracyjne są plain text i podlegają limitom długości oraz sanityzacji po stronie backendu.

Minimalny przykład:

```json
{
  "medical_payload_schema_version": 1,
  "medical_payload": {
    "authoring_locale": "de-DE",
    "fitzpatrick_type": "TYPE_III",
    "overall_image_assessment": "CONTROL_NEEDED",
    "lesions": [
      {
        "lesion_no": 8,
        "dermatoscopic_features": ["ASYMMETRY", "INHOMOGENEOUS_PIGMENTATION"],
        "clinical_assessment": "CONTROL_NEEDED",
        "malignancy_risk": "NO_SUSPICION",
        "generated_text": "Läsion Nr. 8 zeigt dermatoskopisch Asymmetrie ...",
        "edited_text": "Läsion Nr. 8 zeigt dermatoskopisch Asymmetrie ..."
      }
    ],
    "recommendations": ["FOLLOWUP_3_MONTHS"],
    "final_assessment": "NO_HIGH_GRADE_SUSPICION",
    "summary_generated_text": "Bei der Analyse ...",
    "summary_edited_text": "Bei der Analyse ..."
  }
}
```

Kody enum (Befund v1):
- `examination_scope[]`: `INTIMATE_AREA_NOT_EXAMINED`, `ORAL_MUCOSA_NOT_EXAMINED`
- `fitzpatrick_type`: `TYPE_I`, `TYPE_II`, `TYPE_III`, `TYPE_IV`, `TYPE_V`, `TYPE_VI`, `TYPE_II_III`, `UNDETERMINED`
- `overall_image_assessment`: `NO_CONTROL_NEEDED`, `CONTROL_NEEDED`
- `lesions[].dermatoscopic_features[]`: `ASYMMETRY`, `IRREGULAR_BORDER`, `INHOMOGENEOUS_PIGMENTATION`, `MULTICOLOR`, `ATYPICAL_PIGMENT_NETWORK`, `IRREGULAR_GLOBULES`, `IRREGULAR_DOTS`, `STRUCTURELESS_AREAS`, `ATYPICAL_VASCULAR_STRUCTURES`, `REGRESSION_AREAS`
- `lesions[].clinical_assessment`: `UNREMARKABLE`, `SLIGHTLY_ATYPICAL`, `CONTROL_NEEDED`, `SUSPICIOUS`
- `lesions[].malignancy_risk`: `NO_SUSPICION`, `LOW_SUSPICION`, `CANNOT_EXCLUDE`
- `recommendations[]`: `FOLLOWUP_3_MONTHS`, `FOLLOWUP_6_MONTHS`, `PROMPT_VISIT_ON_CHANGE`, `NO_SHORT_TERM_FOLLOWUP_REQUIRED`
- `final_assessment`: `NO_HIGH_GRADE_SUSPICION`, `HIGH_GRADE_CANNOT_BE_EXCLUDED`

