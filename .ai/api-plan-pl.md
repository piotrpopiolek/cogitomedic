# Plan REST API

**Dokumentacja OpenAPI na żywo:** Przy uruchomionej aplikacji interaktywna dokumentacja jest dostępna pod [http://127.0.0.1:8000/api/docs/swagger/](http://127.0.0.1:8000/api/docs/swagger/) (Swagger UI) oraz [http://127.0.0.1:8000/api/docs/redoc/](http://127.0.0.1:8000/api/docs/redoc/) (ReDoc). Schemat: `/api/schema/`.

## 0. Założenia
- Bazowa ścieżka API to `/api/v1`.
- Bazowy runtime backendu to **Django 6.0.x**.
- Zadania tła są definiowane przez **Django Tasks** (`django.tasks`) i orkiestrację przez Transactional Outbox.
- W projekcie obowiązuje jedno rozwiązanie dla pracy asynchronicznej: **Django Tasks + Transactional Outbox**.
- **Języki portalu:** interfejs użytkownika (panel personelu i tablet pacjenta) jest dostępny w języku **angielskim** i **niemieckim**. Użytkownik personelu ma pole `preferred_locale` (np. `en-GB`, `de-DE`); dla tabletu pacjenta język może wynikać z parametru w linku, nagłówka Accept-Language lub domyślnego ustawienia placówki.
- Komunikacja tylko przez HTTPS.
- Domyślny format payloadu to JSON (`application/json`), z wyjątkiem endpointów uploadu plików (`multipart/form-data`).
- Uwierzytelnianie: sesja dla panelu personelu (cookie Django + CSRF). Tablet (poczekalnia) korzysta z tej samej sesji z rolą **TABLET**; **brak tokenów jednorazowych i linków pacjenta**.
- Format czasu: ISO 8601 UTC.
- **Paginacja offsetowa** (`page` / `page_size`): domyślne `page_size` **20**, maksimum **100** — stałe `DEFAULT_LIST_LIMIT` i `MAX_LIST_LIMIT` w `apps.core.api_utils` (m.in. pacjenci, staff-users, lista dokumentów medycznych, lista dokumentów intake, audyt globalny, audyt przy dokumencie).
- **Limit listy** (`limit`): listy recepcji/słowników (placówki, gabinety, kolejki, wpisy, tablety, batche importów) używają parametru `limit` z **tym samym domyślnie 20 i maks. 100** (`parse_list_limit` w tym samym module).
- **Lista outbox / intake-outbox** (`GET /outbox-events`, `GET /intake-outbox-events`): parametr `limit` przez **`parse_list_limit`** — ten sam domyślny rozmiar **20** i maks. **100** co pozostałe listy staff.
- Inne wspólne parametry:
  - `page` (domyślnie `1`), gdzie występuje paginacja offsetowa
  - `ordering` (pola po przecinku, prefiks `-` dla malejąco), jeśli opisano przy endpoincie
  - parametry filtrowania specyficzne dla zasobu

## 1. Zasoby
- `auth` -> `staff_user` (logowanie, wylogowanie, bieżąca sesja, dostęp wg roli)
- `staff-users` -> `staff_user`
- `patients` -> `patient`
- `clinic-sites` -> `clinic_site`
- `consulting-rooms` -> `consulting_room`
- `daily-queues` -> `daily_queue`
- `queue-entries` -> `queue_entry`
- `tablet-devices` -> `tablet_device`
- `patient-sessions` -> `patient_form_session` (cykl życia sesji bez tokenu; flow tabletu: rola TABLET wybiera kolejkę i pacjenta, backend tworzy/aktualizuje sesję i zwraca `intake_form_id`; latest-wins)
- `consent-definitions` -> `consent_definition`
- `anamnesis-definitions` -> `anamnesis_question_definition`, `anamnesis_option_definition`
- `intake-forms` -> `patient_intake_form`
- `intake-consents` -> `patient_intake_consent`
- `medical-documents` -> `medical_document`
- `medical-document-versions` -> `medical_document_version`
- `intake-documents` -> `intake_document_version` (tylko odczyt: lista, szczegóły, podgląd PDF; RECEPTION/ADMIN, scope po `clinic_site`)
- `doctor-text-templates` -> `doctor_text_template`
- `imports` -> `patient_import_batch`, `patient_import_error`
- `outbox-events` -> `outbox_event`
- `audit-events` -> `audit_event`
- `operations` -> akcje domenowe niebędące czystym CRUD (publikacja, retry, retencja)
- `observability` -> ekspozycja metryk i health-checków
- `patient-results` -> portal wyniki (US-018): request-otp, verify-otp, pobranie PDF; bez auth staff – logowanie pacjenta phone+DOB, OTP 15 min

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

- **GET** `/staff-users/{id}/clinic-sites`
  - Opis: Lista przypisanych klinik dla użytkownika personelu (np. dla lekarza DOCTOR).
  - Response JSON: lista obiektów clinic_site.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`, `404 NOT_FOUND`.

- **POST** `/staff-users/{id}/clinic-sites`
  - Opis: Aktualizacja przypisanych klinik dla użytkownika. Zastępuje obecne przypisania (zarządzane przez ADMIN).
  - Request JSON:
    ```json
    {
      "clinic_site_ids": ["uuid1", "uuid2"]
    }
    ```
  - Response JSON: zaktualizowana lista obiektów clinic_site.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `403 FORBIDDEN`, `404 NOT_FOUND`.

### 2.3 Pacjenci

- **GET** `/patients`
  - Opis: Wyszukiwanie/listowanie pacjentów.
  - Parametry zapytania: `search`, `last_name`, `date_of_birth`, `phone`, `doctolib_patient_id`, `is_active`. Parametr `date_of_birth` musi być w formacie ISO `YYYY-MM-DD`; nieprawidłowy format zwraca `400 VALIDATION_ERROR`.
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
          "street": "Main 1",
          "city": "Berlin",
          "postal_code": "10115",
          "country_code": "DE"
        }
      ],
      "pagination": {"page": 1, "page_size": 20, "total": 1}
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR` (np. nieprawidłowy format `date_of_birth`), `403 FORBIDDEN`.

- **POST** `/patients`
  - Opis: Tworzy pacjenta. Użytkownik tworzący jest pobierany z uwierzytelnionej sesji; brak pola w body żądania dla aktora.
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
      "country_code": "DE"
    }
    ```
  - Response JSON:
    ```json
    {
      "patient": {"id": "uuid", "doctolib_patient_id": null}
    }
    ```
  - Kody sukcesu: `201 CREATED`.
  - Kody błędów: `400 VALIDATION_ERROR` (np. nieprawidłowy format telefonu: `^[0-9+() -]{7,20}$`), `409 UNIQUE_CONSTRAINT`.

- **GET** `/patients/{id}`
- **PATCH** `/patients/{id}`
  - Opis: Odczyt/aktualizacja pacjenta.
  - Parametry zapytania: brak.
  - Request JSON (`PATCH`): mutowalne pola demograficzne/kontaktowe.
  - Response JSON: obiekt pacjenta.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `409 UNIQUE_CONSTRAINT`.

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
  - Opis: Zarządzanie dedykowanymi tabletami. Model używa **tylko `android_id`** (unikalny identyfikator urządzenia); pola `name` i `device_code` zostały usunięte (migracja).
  - Parametry zapytania: `is_active`, `search`.
  - Request JSON (create):
    ```json
    {
      "android_id": "device-android-id-string",
      "is_active": true
    }
    ```
  - Response JSON: obiekt tabletu (`id`, `android_id`, `is_active`, `last_seen_at`, `created_at`).
  - **Auto-rejestracja:** przy logowaniu tabletu (rola TABLET) z nieznanym `android_id` backend może utworzyć wpis `TabletDevice`.
  - Kody sukcesu: `200 OK`, `201 CREATED`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 DUPLICATE_ANDROID_ID`.

- **POST** `/tablet-devices/{id}/heartbeat`
  - Opis: Aktualizuje `last_seen_at` urządzenia.
  - Request JSON: `{}`.
  - Response JSON: `{"last_seen_at":"2026-02-16T10:00:00Z"}`.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`.

### 2.7 Sesje pacjenta (bez tokenu; flow tabletu, latest-wins)

- **POST** `/queue-entries/{id}/sessions`
  - Opis: Tworzy lub aktualizuje sesję formularza dla wybranego wpisu kolejki (US-004). Używane przez **tablet** (rola TABLET) lub recepcję (RECEPTION/ADMIN). **Brak tokenu jednorazowego** – autoryzacja oparta na sesji (TABLET + formularz intake w wybranej kolejce).
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "tablet_device_id": "uuid",
      "form_locale": "de-DE",
      "expires_in_minutes": 120
    }
    ```
  - Response JSON:
    ```json
    {
      "session_id": "uuid",
      "intake_form_id": "uuid",
      "expires_at": "2026-02-16T12:00:00Z"
    }
    ```
  - Kody sukcesu: `201 CREATED`.
  - Kody błędów: `404 QUEUE_ENTRY_OR_DEVICE_NOT_FOUND`, `400 VALIDATION_ERROR`. Dozwolone role: **TABLET**, RECEPTION, ADMIN.

- **Brak** endpointu `/patient-sessions/validate` – przepływ z tokenem został usunięty. Tablet uzyskuje dostęp do formularza intake przez uwierzytelnioną sesję (rola TABLET) i `intake_form_id` zwrócony z POST sessions.

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

- **GET** `/intake-forms/by-session/{session_id}` (opcjonalnie, kompatybilność wsteczna)
- **GET** `/intake-forms/{id}` (lub równoważny endpoint kontekstu)
  - Opis: Pobiera kontekst formularza intake dla tabletu. **Tablet (rola TABLET)** jest uwierzytelniony sesją; brak tokenu. Dostęp dozwolony, gdy formularz intake należy do wpisu kolejki w kolejce dostępnej dla użytkownika (TABLET). Używane do: ekran weryfikacji danych pacjenta i formularza (zgody, anamneza, podpis, submit).
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
  - Kody błędów: `403 FORBIDDEN` (np. TABLET nie ma dostępu do tego formularza), `404 NOT_FOUND`.

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
  - Opis: Finalizuje formularz w jednej transakcji (US-005/006/007). **Bez tokenu** – wywołujący jest uwierzytelniony (TABLET lub RECEPTION/ADMIN). Sesja oznaczana jako zużyta/zakończona w razie potrzeby; status wpisu kolejki ustawiany na PATIENT_COMPLETED.
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {}
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
  - Kody błędów: `400 REQUIRED_CONSENTS_MISSING`, `400 REQUIRED_ANAMNESIS_MISSING`, `400 SIGNATURE_REQUIRED`, `403 FORBIDDEN`, `409 FORM_ALREADY_SUBMITTED`.

### 2.10 Dokumenty medyczne i workflow lekarza

**Flow lekarza (Wideodermatoskop):** Numery zmian i zdjęcia pochodzą z Wideodermatoskopu. (1) Lekarz wpisuje numery zmian z urządzenia (np. 2, 3, 12, 13, 22, 25, 56). (2) Dla każdej **grupy** numerów lekarz podaje listę numerów w `lesion_numbers` (np. `[2, 13, 56]`), wypełnia **jeden wspólny opis** (cechy dermatoskopowe, ocena kliniczna, ryzyko złośliwości) oraz korzysta z tekstu generowanego i ewentualnie go edytuje (`generated_text` / `edited_text`). (3) Przykład: grupa 1 `lesion_numbers: [2, 13, 56]` → jeden opis; grupa 2 `lesion_numbers: [3, 12, 22, 25]` → drugi opis. (4) Reszta Befundu bez zmian: zakres badania, Fitzpatrick, ocena globalna, rekomendacje, ocena końcowa, zapis szkicu / publikacja. Schemat ciała nie jest używany w formularzu Befund. Do PDF trafia tekst końcowy (`edited_text` lub `generated_text`) per grupa.

- **GET** `/medical-documents`
  - Opis: Lista robocza lekarza.
  - Parametry zapytania: `status`, `queue_date`, `doctor_view` (`pending_review`, `published`, `failed`), `patient_search`, `page` (domyślnie `1`), `page_size` (domyślnie **20**, maks. **100**).
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
            "lesion_numbers": [2, 3],
            "dermatoscopic_features": ["ASYMMETRY", "INHOMOGENEOUS_PIGMENTATION"],
            "clinical_assessment": "CONTROL_NEEDED",
            "malignancy_risk": "NO_SUSPICION",
            "generated_text": "Läsion Nr. 2, 3 zeigen dermatoskopisch ...",
            "edited_text": "Läsion Nr. 2, 3 zeigen dermatoskopisch ..."
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

- **POST** `/medical-documents/{id}/publish`
  - Opis: Publikuje wersję dokumentu i idempotentnie kolejkuje łańcuch outbox (US-009/010).
  - Parametry zapytania: brak.
  - Request JSON:
    ```json
    {
      "publish_request_id": "uuid-or-client-key",
      "publish_locale": "pl-PL",
      "resend_sms": true
    }
    ```
  - Response JSON:
    ```json
    {
      "published": true,
      "idempotent_replay": false,
      "medical_document_id": "uuid",
      "version_no": 3,
      "version_status": "PUBLISHED",
      "publish_locale": "pl-PL",
      "outbox": [
        {"event_type": "GENERATE_PDF", "status": "PENDING"}
      ]
    }
    ```
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `409 PUBLICATION_IN_PROGRESS`, `422 BUSINESS_RULE_VIOLATION`.

### 2.10a Szablony tekstów lekarskich

- **GET** `/doctor-text-templates`
  - Opis: Lista szablonów tekstu dostępnych dla lekarza (zasięg kliniki + prywatne).
  - Parametry zapytania: `template_locale`, `scope` (`clinic|private|all`), `is_active`.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **POST** `/doctor-text-templates`
- **GET/PATCH/DELETE** `/doctor-text-templates/{id}`
  - Opis: CRUD prywatnych i publicznych (klinika) szablonów tekstowych lekarza.
  - Request JSON (create):
    ```json
    {
      "name": "Dr. Meyer Default",
      "template_locale": "de-DE",
      "template_body": "Läsion {{lesion_no}} zeigt ...",
      "clinic_site_id": null,
      "is_active": true
    }
    ```
  - Kody sukcesu: `201 CREATED`, `200 OK`.
  - Kody błędów: `400 VALIDATION_ERROR`, `400 TEMPLATE_PLACEHOLDER_NOT_ALLOWED`, `400 INVALID_TEXT_CONTENT`, `403 FORBIDDEN`, `409 TEMPLATE_NAME_CONFLICT`.
  - Uwagi:
    - Treść szablonu to wyłącznie plain text (bez HTML/JS).
    - Placeholdery są obsługiwane wyłącznie z allowlisty (bez logiki warunkowej, pętli i DSL).

- **GET** `/medical-documents/{id}/versions`
  - Opis: Historia wersji. Lekarz widzi tylko, jeśli jest autorem dokumentu lub dokument jest w zakresie jego przypisanych klinik/kolejek.
  - Parametry zapytania: paginacja/sortowanie po `-version_no`.
  - Response JSON: lista wersji.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`.

- **GET** `/medical-documents/{id}/audit-trail`
  - Opis: Zdarzenia audytowe powiązane z danym dokumentem. Lekarz widzi tylko, jeśli jest autorem dokumentu lub dokument jest w zakresie jego przypisanych klinik/kolejek.
  - Parametry zapytania: `page` (domyślnie `1`), `page_size` (domyślnie **20**, maks. **100**).
  - Response JSON: `{ "items": [...], "pagination": { "page", "page_size", "total" } }`.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`, `403 FORBIDDEN`.

- **GET** `/medical-document-versions/{id}`
  - Opis: Szczegóły wskazanej wersji i stan przetwarzania.
  - Response JSON: obiekt wersji z flagami PDF/HiDrive/SMS.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND`.

### 2.10a Dokumenty intake (PDF) – RECEPTION/ADMIN

Dostęp tylko dla ról **RECEPTION** i **ADMIN**. RECEPTION widzi wyłącznie dokumenty z przypisanych placówek (`clinic_site`); ADMIN – wszystkie. Zasób read-only (lista, szczegóły, podgląd pliku PDF).

- **GET** `/intake-documents`
  - Opis: Lista wersji dokumentów intake (wygenerowane PDF). Używane przez recepcję i admina do przeglądania/odtwarzania dokumentów.
  - Parametry zapytania: `queue_date` (YYYY-MM-DD), `pdf_generation_status` (PENDING, IN_PROGRESS, COMPLETED, FAILED), `patient_search` (nazwisko/imiona), `clinic_site_id`, `page` (domyślnie `1`), `page_size` (domyślnie **20**, maks. **100**).
  - Response JSON: `{ "items": [...], "pagination": { "page", "page_size", "total" } }`. Każdy element: `id`, `version_no`, `form_locale`, `pdf_generation_status`, `created_at`, `queue_entry_id`, `intake_form_id`, `queue_date`, `clinic_site_id`, `clinic_site_name`, `patient` (id, first_name, last_name, date_of_birth), `pdf_available`, `hidrive_sent`, `processing_error_message`.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN` (np. rola DOCTOR).

- **GET** `/intake-documents/{id}`
  - Opis: Szczegóły jednej wersji dokumentu intake.
  - Response JSON: obiekt szczegółów (jak element listy + m.in. `pdf_local_path`, `pdf_checksum_sha256`, `hidrive_path`, `hidrive_sent_at`).
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`, `404 NOT_FOUND` (brak dostępu lub brak rekordu).

- **GET** `/intake-documents/{id}/preview-pdf`
  - Opis: Zwraca plik PDF do podglądu inline (`Content-Disposition: inline`). Dostępne tylko gdy `pdf_generation_status == COMPLETED` i plik istnieje w `MEDIA_ROOT`.
  - Response: `Content-Type: application/pdf`, body binarny.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `404 NOT_FOUND` (dokument nie w scope, brak pliku lub status ≠ COMPLETED).

### 2.11 Importy (XLSX, harmonogram)

- **POST** `/imports/patients/pdf` — **wycofany.** Import pacjentów z PDF Doctolib został usunięty. Użyj „Import z pliku” w adminie (XLSX) lub przyszłego `POST /imports/patients/xlsx` po wdrożeniu.

- **GET** `/imports/batches`
  - Opis: Lista batchy importu.
  - Parametry zapytania: `limit` (domyślnie **20**, maks. **100**, jak inne listy `parse_list_limit`).
  - Response JSON: lista batchy.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **GET** `/imports/batches/{id}`
  - Opis: Szczegóły batcha.
  - Response JSON:
    ```json
    {
      "id": "uuid",
      "source_file_name": "export_20260308.xlsx",
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
  - Parametry zapytania: brak.
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

### 2.12 Outbox i operacje (Admin/Ops)

- **GET** `/outbox-events`
  - Opis: Operacyjny widok kolejki outbox.
  - Parametry zapytania: `status`, `event_type`, `retry_count_gte`, `limit` (domyślnie **20**, maks. **100**; `parse_list_limit`).
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
  - Opis: Ręczne uruchomienie cyklu przetwarzania zadań outbox (bezpieczny endpoint admina).
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
  - Parametry zapytania: `event_type`, `actor_user_id`, `patient_id`, `medical_document_id`, `context_clinic_site_id`, `outbox_event_id`, `from`, `to` (UUID dla identyfikatorów encji; ISO datetime dla `from`/`to`), `page` (domyślnie `1`), `page_size` (domyślnie **20**, maks. **100**).
  - Response JSON: `{ "items": [...], "pagination": { "page", "page_size", "total" } }`. Po anonimizacji lub usunięciu encji FK może być NULL; API nadal zwraca ID z `metadata._ref` w celu compliance.
  - Kody sukcesu: `200 OK`.
  - Kody błędów: `403 FORBIDDEN`.

- **GET** `/observability/health`
  - Opis: Liveness/readiness aplikacji, DB, przetwarzania zadań outbox i integracji.
  - Response JSON:
    ```json
    {
      "status": "ok",
      "checks": {
        "db": "ok",
        "outbox_tasks": "ok",
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
  - **Tablet (poczekalnia):** ta sama sesja z rolą **TABLET**. Brak tokenu jednorazowego; tablet wybiera kolejkę i pacjenta, POST sessions zwraca `intake_form_id`; dostęp do formularza i submit są autoryzowane przez `request.user.role == TABLET` oraz formularz intake w dozwolonym zakresie (np. kolejka).

- Autoryzacja (RBAC wg `staff_user.role`):
  - **TABLET**: tylko: lista kolejek na dziś (wybór), lista wpisów kolejki, POST queue-entries/{id}/sessions, GET kontekstu formularza intake, PUT anamneza/zgody, upload podpisu, POST submit intake. Brak wyszukiwarki pacjentów, braku CRUD kolejek, braku zarządzania użytkownikami.
  - `RECEPTION`: kolejki, wpisy kolejki, tworzenie/aktualizacja pacjentów, generacja sesji (POST sessions), importy read/write.
  - `DOCTOR`: odczyt/zapis dokumentów medycznych, publikacja/republikacja, podgląd wersji.
  - `ADMIN`: zarządzanie użytkownikami, słownik zgód, operacje techniczne, pełny podgląd audytu/outbox.
  - Ochrona endpointów przez klasy uprawnień Django + kontrole na poziomie obiektu.

- Kontrole sesji/bezpieczeństwa:
  - Timeout bezczynności egzekwowany po stronie serwera (sesja tabletu może trwać kilka godzin; brak edycji danych pacjenta na tablecie).
  - Ochrona brute-force na `/auth/login`.
  - HSTS i przekierowanie do HTTPS.
  - Hasła przechowywane wyłącznie przez hashery Django.
  - Brak sekretów w kodzie; konfiguracja przez zmienne środowiskowe.

- Utwardzenie API:
  - Rate limiting (przykładowa polityka):
    - `/auth/login`: 5 req/min/IP + bucket per username.
    - endpointy mutujące (domyślnie): 60 req/min/user.
    - operacje administracyjne: 10 req/min/user.
  - Limity rozmiaru żądań dla podpisów/uploadów.
  - Sanityzacja plain-text dla narracji lekarza i treści szablonów przed zapisem/generowaniem PDF.
  - Sanityzacja wejścia i allowlisty dla pól sortowania/filtrowania.
  - Audyt wszystkich akcji bezpieczeństwa (błędy logowania, publikacje, retry, retencja).

## 4. Walidacja i logika biznesowa

### 4.1 Reguły walidacji zasobów

- `staff_user`
  - `username` unikalny, `email` unikalny (case-insensitive), `role` w `RECEPTION|DOCTOR|ADMIN|TABLET`.
  - `phone_number` regex: `^[0-9+() -]{7,20}$`.

- `patient`
  - Wymagane: `first_name`, `last_name`, `date_of_birth`, `phone`, `email`.
  - `phone` regex: `^[0-9+() -]{7,20}$`.
  - `date_of_birth <= current_date`.
  - `(first_name, last_name, phone, date_of_birth)` unikalne.
  - `doctolib_patient_id` jest opcjonalne, ale unikalne gdy istnieje.

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
  - **Brak tokenu** – pole `token_hash` zostało usunięte (migracja). Sesja identyfikowana po id; autoryzacja tabletu po roli TABLET i zakresie kolejki/intake.
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
  - `publish_locale` jest wymagane dla `PUBLISHED` i musi pasować do `^(de|en|pl)(-[A-Z]{2})?$`.
  - `pdf_generation_status='COMPLETED'` wymaga `pdf_local_path`.
  - `hidrive_sent=true` wymaga ukończonego PDF, `pdf_local_path` i `hidrive_sent_at`.
  - `sms_sent=true` wymaga `sms_sent_at`.
  - `local_pdf_deleted_at` dozwolone tylko gdy `hidrive_sent=true` i `sms_sent=true`.

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
  - `metadata` musi być obiektem JSON. Zarezerwowany klucz `_ref` przechowuje niezmienną kopię ID encji (patient_id, medical_document_id, context_clinic_site_id itd.) w celu compliance po anonimizacji/usunięciu.

### 4.2 Implementacja logiki biznesowej w API

- Manualne dodanie pacjenta wspiera brak `doctolib_patient_id`:
  - Jeśli brak `doctolib_patient_id`, API nadal tworzy pacjenta bez nadawania statusu tymczasowego i bez metadanych alertu.

- Ujednolicona ingestia:
  - Dodanie ręczne, import pliku i autoimport korzystają ze wspólnego serwisu ingestii z tymi samymi walidacjami i deduplikacją.

- Idempotentny import:
  - Wykorzystanie unikalności `first_name + last_name + phone + date_of_birth`, opcjonalnego `doctolib_patient_id` oraz kluczy zewnętrznych wizyty do unikania duplikatów pacjentów/wizyt.

- Model sesji latest-wins (bez tokenu):
  - Utworzenie sesji (POST queue-entries/{id}/sessions) tworzy nowy `patient_form_session` (bez pola token) i atomowo przełącza `queue_entry.active_session_id`.
  - Tablet (TABLET) lub recepcja wywołuje POST sessions; backend zwraca `intake_form_id`. Brak endpointu walidacji tokenu.

- Transakcyjny submit intake:
  - Weryfikuje akceptację wymaganych aktywnych zgód.
  - Weryfikuje obecność podpisu.
  - Ustawia formularz na `SUBMITTED`, zapisuje `submitted_at`, oznacza sesję jako zużyta (`consumed_at`) w razie potrzeby i aktualizuje status kolejki w jednej transakcji. Wywołujący jest uwierzytelniony (TABLET lub RECEPTION/ADMIN); brak tokenu w żądaniu.

- Workflow lekarza:
  - Zapis szkicu aktualizuje/tworzy najnowszą wersję draft; lekarz wpisuje/edyuje tekst w `medical_payload` (np. `edited_text`, `summary_edited_text`).
  - Lekarz zapisuje w `medical_payload` finalne teksty edytowane (oraz opcjonalnie wygenerowane z szablonu).
  - Request publikacji musi zawierać `publish_locale`; backend zapisuje je w `medical_document_version` i traktuje jako źródło prawdy dla języka PDF.
  - Publikacja używa locka wiersza na `medical_document` i kontroli idempotencji:
    - ten sam `publish_request_id` zwraca sukces-replay;
    - publikacja już w toku zwraca idempotentny sukces (bez duplikacji łańcucha outbox).

- Łańcuch transactional outbox:
  - Transakcja publikacji enqueuje `GENERATE_PDF`.
  - Worker po sukcesie PDF enqueuje `HIDRIVE_UPLOAD`.
  - Worker po sukcesie uploadu enqueuje `SMS_SEND`. **Treść SMS:** wyłącznie logistyczna – „Nowa dokumentacja w Cogito“ (bez linku; pacjent pobiera przez portal wyniki).
  - Retry i dead-letter obsługiwane przez statusy/liczniki outbox.

- Portal wyniki dla pacjenta (US-018, PRD 3.4a):
  - SMS wyłącznie logistyczny; pacjent wchodzi na np. wyniki.cogitomedica.pl.
  - Logowanie: telefon + data urodzenia (zweryfikowane w recepcji).
  - OTP: 6-cyfrowy kod, ważność 15 min; wysyłany asynchronicznie gdy telefon+DOB się zgadzają.
  - Po prawidłowym OTP: serwowanie PDF przez HTTPS. **Audyt (`audit_event`):** typowane zdarzenia m.in. `PATIENT_RESULTS_OTP_REQUEST`, `PATIENT_RESULTS_OTP_VERIFY`, `PATIENT_RESULTS_DOCUMENTS_LISTED`, `PATIENT_RESULTS_PDF_DOWNLOAD`, `PATIENT_RESULTS_PDF_DOWNLOAD_DENIED` z `event_time`, `patient_id` (gdy dotyczy) oraz `metadata` (`client_ip`, wynik żądania OTP, powód odmowy pobrania itd.).
  - Lekarz może wycofać publikację; pacjent po wpisaniu OTP nie zobaczy wycofanego pliku.

- Republikacja:
  - Edycja opublikowanego dokumentu tworzy kolejną wersję i uruchamia łańcuch ponownie; ścieżka archiwum jest nadpisywana zgodnie z wymaganiem biznesowym.
  - API wspiera opcjonalny `resend_sms`.

- Polityka retencji:
  - Harmonogram/ręczne zadanie retencji (Django Tasks) usuwa lokalny PDF tylko gdy `hidrive_sent=true` i `sms_sent=true`, a wiek dokumentu przekracza 30 dni.
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

- Wersja schematu: `medical_payload_schema_version: 1`.
- `medical_payload` przechowuje dane ustrukturyzowane i teksty:
  - dane globalne (`fitzpatrick_type`, `overall_image_assessment`, `recommendations`, `final_assessment`),
  - grupy zmian (`lesions[]`) – każda grupa ma listę numerów z Wideodermatoskopu i wspólny opis,
  - teksty wygenerowane i końcowe (`generated_text`, `edited_text` per grupa; `summary_generated_text`, `summary_edited_text`).
- Zapis tekstów odbywa się niezależnie od języka UI; `authoring_locale` wskazuje język roboczy lekarza.
- Pola narracyjne są plain text i podlegają limitom długości oraz sanityzacji po stronie backendu.

**Struktura `lesions[]`** – każdy element:

| Pole | Typ | Wymagane | Opis |
|------|-----|----------|------|
| `lesion_numbers` | array of integer | tak | Numery zmian z Wideodermatoskopu w tej grupie opisu |
| `dermatoscopic_features` | array of string | nie | Kody cech dermatoskopowych |
| `clinical_assessment` | string | tak | Kod oceny kliniczno-dermatoskopowej |
| `malignancy_risk` | string | tak | Kod ryzyka złośliwości |
| `generated_text` | string | nie | Tekst wygenerowany przez system |
| `edited_text` | string | nie | Tekst po edycji przez lekarza |

**Walidacja `lesion_numbers`:**
- Nie może być puste: `lesion_numbers.length >= 1`.
- Brak duplikatów w jednej tablicy: po usunięciu duplikatów długość tablicy musi być taka sama (np. `[2, 3, 2]` → błąd).

**Reguły walidacyjne (do implementacji):** Dla każdego elementu `lesions[]`: `lesion_numbers` niepuste i bez duplikatów; `clinical_assessment` i `malignancy_risk` z zdefiniowanych zestawów. Opcjonalnie: każdy numer z Wideodermatoskopu tylko w jednej grupie w obrębie całego `lesions` (unikalność globalna) – do decyzji produktu.

Przykład:

```json
{
  "medical_payload_schema_version": 1,
  "medical_payload": {
    "authoring_locale": "de-DE",
    "fitzpatrick_type": "TYPE_III",
    "overall_image_assessment": "CONTROL_NEEDED",
    "lesions": [
      {
        "lesion_numbers": [2, 3],
        "dermatoscopic_features": ["ASYMMETRY", "INHOMOGENEOUS_PIGMENTATION"],
        "clinical_assessment": "CONTROL_NEEDED",
        "malignancy_risk": "NO_SUSPICION",
        "generated_text": "Läsion Nr. 2, 3 zeigen dermatoskopisch ...",
        "edited_text": "Läsion Nr. 2, 3 zeigen dermatoskopisch ..."
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

