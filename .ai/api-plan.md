# REST API Plan

**Live OpenAPI docs:** When the app is running, interactive documentation is available at [http://127.0.0.1:8000/api/docs/swagger/](http://127.0.0.1:8000/api/docs/swagger/) (Swagger UI) and [http://127.0.0.1:8000/api/docs/redoc/](http://127.0.0.1:8000/api/docs/redoc/) (ReDoc). The schema is exposed at `/api/schema/`.

## 0. Assumptions
- API base path is `/api/v1`.
- Backend runtime baseline is **Django 6.0.x**.
- Background tasks are defined with **Django Tasks** (`django.tasks`) and orchestrated with Transactional Outbox.
- The project uses one background-processing solution: **Django Tasks + Transactional Outbox**.
- **Portal languages:** The user interface (staff panel and patient tablet) is available in **German**, **English**, and **Polish**. Staff users have a `preferred_locale` field (e.g. `de-DE`, `en-GB`, `pl-PL`); for the patient tablet the language is resolved from session/form context.
- Transport is HTTPS only.
- JSON is default payload format (`application/json`), except file upload endpoints (`multipart/form-data`).
- Authentication is session-based for staff web UI (Django auth cookie + CSRF). Tablet (poczekalnia) uses the same session auth with role **TABLET**; there are **no one-time tokens or patient links**.
- Time format is ISO 8601 UTC.
- **Offset pagination** (`page` / `page_size`): default `page_size` **20**, maximum **100** — implemented as `DEFAULT_LIST_LIMIT` and `MAX_LIST_LIMIT` in `apps.core.api_utils` (staff list endpoints: patients, staff-users, medical documents list, intake documents list, global audit feed, per-document audit trail, etc.).
- **Capped list length** (`limit`): reception/dictionary-style lists (e.g. clinic-sites, consulting-rooms, daily-queues, queue entries, tablet-devices, import batches) use query param `limit` with the **same default 20 and max 100** via `parse_list_limit` in the same module.
- **Outbox / intake-outbox listing** (`GET /outbox-events`, `GET /intake-outbox-events`): query param `limit` uses **`parse_list_limit`** — same default **20** and max **100** as other staff lists.
- Other common list/query parameters:
  - `page` (default `1`) where offset pagination applies
  - `ordering` (comma-separated fields, prefix `-` for desc) where documented per endpoint
  - resource-specific filter params

## 1. Resources
- `auth` -> `staff_user` (login, logout, current session, role access)
- `staff-users` -> `staff_user`
- `patients` -> `patient`
- `clinic-sites` -> `clinic_site`
- `consulting-rooms` -> `consulting_room`
- `daily-queues` -> `daily_queue`
- `queue-entries` -> `queue_entry`
- `tablet-devices` -> `tablet_device`
- `patient-sessions` -> `patient_form_session` (session lifecycle without token; tablet flow: TABLET role selects queue and patient, backend creates/updates session and returns `intake_form_id`; latest-wins)
- `consent-definitions` -> `consent_definition`
- `anamnesis-definitions` -> `anamnesis_question_definition`, `anamnesis_option_definition`
- `intake-forms` -> `patient_intake_form`
- `intake-consents` -> `patient_intake_consent`
- `medical-documents` -> `medical_document`
- `medical-document-versions` -> `medical_document_version`
- `intake-documents` -> `intake_document_version` (read-only: list, detail, preview PDF; RECEPTION/ADMIN, scoped by `clinic_site`)
- `doctor-text-templates` -> `doctor_text_template`
- `imports` -> `patient_import_batch`, `patient_import_error`
- `outbox-events` -> `outbox_event`
- `audit-events` -> `audit_event`
- `operations` -> domain actions not pure CRUD (publish, retry, retention)
- `observability` -> metrics/health surfaces for operations
- `patient-results` -> portal wyniki (US-018): request-otp, verify-otp, download PDF; no staff auth – patient login by phone+DOB, OTP 15 min

## 2. Endpoints

### 2.1 Auth

- **POST** `/auth/login`
  - Description: Staff login (US-001).
  - Query params: none.
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
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `401 INVALID_CREDENTIALS`, `429 TOO_MANY_ATTEMPTS`.

- **POST** `/auth/logout`
  - Description: Ends active session.
  - Query params: none.
  - Request JSON: `{}`.
  - Response JSON: `{"message": "Logged out"}`.
  - Success: `200 OK`.
  - Errors: `401 UNAUTHENTICATED`.

- **GET** `/auth/me`
  - Description: Returns current authenticated staff user and permissions.
  - Query params: none.
  - Request JSON: none.
  - Response JSON:
    ```json
    {
      "id": "uuid",
      "username": "doctor1",
      "role": "DOCTOR",
      "permissions": ["queue.read", "document.publish"]
    }
    ```
  - Success: `200 OK`.
  - Errors: `401 UNAUTHENTICATED`.

### 2.2 Staff users (Admin)

- **GET** `/staff-users`
  - Description: List users.
  - Query params: `role`, `is_active`, `search`.
  - Request JSON: none.
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
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **POST** `/staff-users`
  - Description: Create user.
  - Query params: none.
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
  - Response JSON: created user object.
  - Success: `201 CREATED`.
  - Errors: `400 VALIDATION_ERROR`, `409 DUPLICATE_USERNAME_OR_EMAIL`, `403 FORBIDDEN`.

- **GET** `/staff-users/{id}`
- **PATCH** `/staff-users/{id}`
- **DELETE** `/staff-users/{id}`
  - Description: Read/update/deactivate user (`DELETE` is soft-delete via `is_active=false`).
  - Query params: none.
  - Request JSON (`PATCH`): partial fields (except immutable identifiers).
  - Response JSON: user object / `{"message":"User deactivated"}`.
  - Success: `200 OK`, `204 NO_CONTENT` (optional for delete).
  - Errors: `400 VALIDATION_ERROR`, `403 FORBIDDEN`, `404 NOT_FOUND`.

- **GET** `/staff-users/{id}/clinic-sites`
  - Description: List assigned clinic sites for a staff user (e.g. for a DOCTOR).
  - Response JSON: list of clinic site objects.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`, `404 NOT_FOUND`.

- **POST** `/staff-users/{id}/clinic-sites`
  - Description: Update assigned clinic sites for a staff user. Replaces current assignments (managed by ADMIN).
  - Request JSON:
    ```json
    {
      "clinic_site_ids": ["uuid1", "uuid2"]
    }
    ```
  - Response JSON: updated list of clinic site objects.
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `403 FORBIDDEN`, `404 NOT_FOUND`.

### 2.3 Patients

- **GET** `/patients`
  - Description: Search/list patients.
  - Query params: `search`, `last_name`, `date_of_birth`, `phone`, `doctolib_patient_id`, `is_active`. The `date_of_birth` must be in ISO format `YYYY-MM-DD`; invalid format returns `400 VALIDATION_ERROR`.
  - Request JSON: none.
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
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR` (e.g. invalid `date_of_birth` format), `403 FORBIDDEN`.

- **POST** `/patients`
  - Description: Create patient. The creating user is taken from the authenticated session; no request body field for actor.
  - Query params: none.
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
  - Success: `201 CREATED`.
  - Errors: `400 VALIDATION_ERROR` (e.g. invalid phone format: must match `^[0-9+() -]{7,20}$`), `409 UNIQUE_CONSTRAINT`.

- **GET** `/patients/{id}`
- **PATCH** `/patients/{id}`
  - Description: Read/update patient.
  - Query params: none.
  - Request JSON (`PATCH`): mutable demographic/contact fields.
  - Response JSON: patient object.
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `409 UNIQUE_CONSTRAINT`.

### 2.4 Clinic sites and consulting rooms

- **GET** `/clinic-sites`, **POST** `/clinic-sites`, **GET/PATCH/DELETE** `/clinic-sites/{id}`
  - Description: CRUD for clinic locations (admin-managed dictionary).
  - Query params: `is_active`, `search`.
  - Request JSON (create/update):
    ```json
    {
      "code": "BERLIN-1",
      "name": "Berlin Central",
      "is_active": true
    }
    ```
  - Response JSON: clinic site object.
  - Success: `200 OK`, `201 CREATED`.
  - Errors: `400 VALIDATION_ERROR`, `409 DUPLICATE_CODE`, `403 FORBIDDEN`.

- **GET** `/consulting-rooms`, **POST** `/consulting-rooms`, **GET/PATCH/DELETE** `/consulting-rooms/{id}`
  - Description: CRUD for rooms by site.
  - Query params: `clinic_site_id`, `is_active`, `search`.
  - Request JSON (create/update):
    ```json
    {
      "clinic_site_id": "uuid",
      "code": "R01",
      "name": "Room 1",
      "is_active": true
    }
    ```
  - Response JSON: room object.
  - Success: `200 OK`, `201 CREATED`.
  - Errors: `400 VALIDATION_ERROR`, `409 DUPLICATE_ROOM_CODE_PER_SITE`, `404 CLINIC_SITE_NOT_FOUND`.

### 2.5 Daily queues and queue entries (Reception)

- **GET** `/daily-queues`
  - Description: List queues for date/site/room/shift.
  - Query params: `queue_date`, `clinic_site_id`, `consulting_room_id`, `shift_code`, `status`.
  - Request JSON: none.
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
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`.

- **POST** `/daily-queues`
  - Description: Create queue for date/site/room/shift.
  - Query params: none.
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
  - Response JSON: queue object.
  - Success: `201 CREATED`.
  - Errors: `400 VALIDATION_ERROR`, `409 DUPLICATE_QUEUE`.

- **PATCH** `/daily-queues/{id}`
  - Description: Update queue status (`OPEN`/`CLOSED`).
  - Request JSON:
    ```json
    {
      "status": "CLOSED"
    }
    ```
  - Response JSON: queue object.
  - Success: `200 OK`.
  - Errors: `409 INVALID_STATE_TRANSITION`, `404 NOT_FOUND`.

- **GET** `/daily-queues/{id}/entries`
  - Description: List queue entries for waiting room.
  - Query params: `entry_status`, `patient_id`, `ordering` (default `position_no`).
  - Request JSON: none.
  - Response JSON: queue entry list.
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

- **POST** `/daily-queues/{id}/entries`
  - Description: Add patient to queue (manual reception flow).
  - Query params: none.
  - Request JSON:
    ```json
    {
      "patient_id": "uuid",
      "visit_external_id": null,
      "appointment_time": "2026-02-16T10:30:00Z",
      "notes": "Follow-up visit"
    }
    ```
  - Response JSON: created queue entry with assigned `position_no`.
  - Success: `201 CREATED`.
  - Errors: `400 VALIDATION_ERROR`, `404 QUEUE_OR_PATIENT_NOT_FOUND`, `409 UNIQUE_VISIT_EXTERNAL_ID`.

- **GET/PATCH/DELETE** `/queue-entries/{id}`
  - Description: Read/update/cancel queue entry.
  - Query params: none.
  - Request JSON (`PATCH`):
    ```json
    {
      "entry_status": "IN_PROGRESS",
      "notes": "Patient moved to room"
    }
    ```
  - Response JSON: queue entry object.
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `409 INVALID_STATE_TRANSITION`.

### 2.6 Tablet devices

- **GET** `/tablet-devices`, **POST** `/tablet-devices`, **GET/PATCH/DELETE** `/tablet-devices/{id}`
  - Description: Manage dedicated tablets. Model uses **`android_id`** (unique device identifier) and **`clinic_site_id`** (optional FK to ClinicSite). Tablet sees only queues of the assigned site; unassigned tablet gets empty queue list. Fields `name` and `device_code` have been removed (migration).
  - Query params: `is_active`, `search`.
  - Request JSON (create):
    ```json
    {
      "android_id": "device-android-id-string",
      "is_active": true,
      "clinic_site_id": "uuid-or-null"
    }
    ```
  - Request JSON (PATCH): `clinic_site_id` optional; `null` unassigns device from site.
  - Response JSON: tablet object (`id`, `android_id`, `is_active`, `last_seen_at`, `created_at`, `clinic_site_id`).
  - **Auto-registration:** If a tablet logs in (role TABLET) with an `android_id` not yet in the system, the backend may create a `TabletDevice` record automatically.
  - **TABLET scope:** When session has `tablet_device_id` and device has `clinic_site_id`, GET daily-queues and GET daily-queues/{id}/entries return only queues of that site; without assignment, empty list.
  - Success: `200 OK`, `201 CREATED`.
  - Errors: `400 VALIDATION_ERROR`, `409 DUPLICATE_ANDROID_ID`.

- **POST** `/tablet-devices/{id}/heartbeat`
  - Description: Update device `last_seen_at`.
  - Request JSON: `{}`.
  - Response JSON: `{"last_seen_at":"2026-02-16T10:00:00Z"}`.
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

### 2.7 Patient sessions (no token; tablet flow, latest-wins)

- **POST** `/queue-entries/{id}/sessions`
  - Description: Create or update form session for the selected queue entry (US-004). Used by **tablet** (role TABLET) or reception (RECEPTION/ADMIN). **No one-time token** – authorization is session-based (TABLET + intake_form in selected queue).
  - Query params: none.
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
  - Success: `201 CREATED`.
  - Errors: `404 QUEUE_ENTRY_OR_DEVICE_NOT_FOUND`, `400 VALIDATION_ERROR`. Allowed roles: **TABLET**, RECEPTION, ADMIN.

- **No** `/patient-sessions/validate` – token flow has been removed. Tablet accesses intake form by authenticated session (role TABLET) and `intake_form_id` returned from POST sessions.

### 2.8 Consent definitions (Admin dictionary)

- **GET** `/consent-definitions`
  - Description: List consents with active/effective filtering.
  - Query params: `is_active`, `effective_on`, `code`.
  - Request JSON: none.
  - Response JSON: list of consent definitions.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **POST** `/consent-definitions`
- **GET/PATCH/DELETE** `/consent-definitions/{id}`
  - Description: CRUD for consent versions.
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
  - Response JSON: consent object.
  - Success: `201 CREATED`, `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `409 DUPLICATE_CODE_VERSION`, `403 FORBIDDEN`.

### 2.8a Anamnesis definitions (Admin dictionary)

- **GET** `/anamnesis-definitions`
  - Description: List anamnesis questions and answer options (DE/EN) active for a given date.
  - Query params: `is_active`, `effective_on`, `locale` (`de-DE`|`en-GB`|`en-US`), `code`.
  - Request JSON: none.
  - Response JSON:
    ```json
    {
      "schema_version": 1,
      "items": [
        {
          "question_code": "Q1_MALIGNANT_MELANOMA_HISTORY",
          "question_text": "Have you ever been diagnosed with malignant melanoma?",
          "answer_type": "SINGLE_CHOICE",
          "is_required": true,
          "options": [
            {"option_code": "NO", "label": "No"},
            {"option_code": "YES", "label": "Yes"}
          ]
        }
      ]
    }
    ```
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **POST** `/anamnesis-definitions`
- **GET/PATCH/DELETE** `/anamnesis-definitions/{id}`
  - Description: CRUD for anamnesis question and option definitions.
  - Success: `201 CREATED`, `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `409 DUPLICATE_CODE_VERSION`, `403 FORBIDDEN`.

### 2.9 Intake forms and consents (Tablet flow)

- **GET** `/intake-forms/by-session/{session_id}` (optional, for backward compatibility)
- **GET** `/intake-forms/{id}` (or equivalent context endpoint)
  - Description: Fetch intake form context for tablet. **Tablet (role TABLET)** is authenticated by session; no token. Access allowed if the intake form belongs to a queue entry in a queue the user (TABLET) is allowed to access. Used for: patient data verification screen and form (consents, anamnesis, signature, submit).
  - Query params: none.
  - Request JSON: none.
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
          "question_text": "Have you ever been diagnosed with malignant melanoma?",
          "answer_type": "SINGLE_CHOICE",
          "is_required": true,
          "options": [
            {"option_code": "NO", "label": "No"},
            {"option_code": "YES", "label": "Yes"}
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
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN` (e.g. TABLET cannot access this form), `404 NOT_FOUND`.

- **PATCH** `/intake-forms/{id}`
  - Description: Save in-progress body map data and optional signature draft.
  - Query params: none.
  - Request JSON:
    ```json
    {
      "body_map_schema_version": 1,
      "body_map_data": [
        {"x": 0.42, "y": 0.31, "side": "front", "label": "pain"}
      ]
    }
    ```
  - Response JSON: updated form.
  - Success: `200 OK`.
  - Errors: `400 INVALID_JSON_SCHEMA`, `401 TOKEN_INVALID_OR_EXPIRED`, `409 FORM_ALREADY_SUBMITTED`.

- **PUT** `/intake-forms/{id}/consents`
  - Description: Replace consent acceptance set for intake form.
  - Query params: none.
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
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `409 CONSENT_NOT_ACTIVE_FOR_DATE`.

- **PUT** `/intake-forms/{id}/anamnesis`
  - Description: Replace anamnesis questionnaire answers for the intake form.
  - Query params: none.
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
  - Success: `200 OK`.
  - Errors: `400 INVALID_JSON_SCHEMA`, `400 UNKNOWN_QUESTION_OR_OPTION_CODE`, `409 FORM_ALREADY_SUBMITTED`.

- **POST** `/intake-forms/{id}/signature`
  - Description: Upload patient signature.
  - Query params: none.
  - Request JSON (base64 variant):
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
  - Success: `200 OK`.
  - Errors: `400 INVALID_SIGNATURE`, `413 PAYLOAD_TOO_LARGE`, `409 FORM_ALREADY_SUBMITTED`.

- **POST** `/intake-forms/{id}/submit`
  - Description: Finalize form in one transaction (US-005/006/007). **No token** – caller is authenticated (TABLET or RECEPTION/ADMIN). Session is marked consumed / completed as needed; queue entry status set to PATIENT_COMPLETED.
  - Query params: none.
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
  - Success: `200 OK`.
  - Errors: `400 REQUIRED_CONSENTS_MISSING`, `400 REQUIRED_ANAMNESIS_MISSING`, `400 SIGNATURE_REQUIRED`, `403 FORBIDDEN`, `409 FORM_ALREADY_SUBMITTED`.

### 2.10 Medical documents and doctor workflow

**Doctor flow (Wideodermatoskop):** Lesion numbers and images come from the Wideodermatoskop device. (1) The doctor enters lesion numbers from the device (e.g. 2, 3, 12, 13, 22, 25, 56). (2) For each **group** of numbers the doctor provides the list in `lesion_numbers` (e.g. `[2, 13, 56]`), fills in **one shared description** (dermatoscopic features, clinical assessment, malignancy risk) and uses generated text, optionally editing it (`generated_text` / `edited_text`). (3) Example: group 1 `lesion_numbers: [2, 13, 56]` → one description; group 2 `lesion_numbers: [3, 12, 22, 25]` → second description. (4) Rest of Befund unchanged: examination scope, Fitzpatrick, global assessment, recommendations, final assessment, draft save / publish. Body schema is not used in the Befund form. The final text (`edited_text` or `generated_text`) per group goes to PDF.

- **GET** `/medical-documents`
  - Description: List doctor work queue.
  - Query params: `status`, `queue_date`, `doctor_view` (`pending_review`, `published`, `failed`), `patient_search`, `page` (default `1`), `page_size` (default **20**, max **100**).
  - Request JSON: none.
  - Response JSON: paginated document list with latest version status flags (`pdf_generation_status`, `hidrive_sent`, `sms_sent`).
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **GET** `/medical-documents/{id}`
  - Description: Full document context (patient intake + medical draft/current version).
  - Query params: `include_versions=true|false`.
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
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`, `403 FORBIDDEN`.

- **POST** `/medical-documents`
  - Description: Create document for queue entry if not existing.
  - Request JSON:
    ```json
    {
      "queue_entry_id": "uuid"
    }
    ```
  - Response JSON: created or existing document.
  - Success: `201 CREATED` or `200 OK` (idempotent).
  - Errors: `404 QUEUE_ENTRY_NOT_FOUND`, `409 INTAKE_NOT_SUBMITTED`.

- **PATCH** `/medical-documents/{id}/draft`
  - Description: Save draft medical section (US-008/009).
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
  - Response JSON: latest draft version.
  - Success: `200 OK`.
  - Errors: `400 INVALID_JSON_SCHEMA`, `400 REQUIRED_MEDICAL_FIELDS_MISSING`, `409 DOCUMENT_NOT_EDITABLE`.

- **POST** `/medical-documents/{id}/publish`
  - Description: Publish document version and enqueue outbox chain idempotently (US-009/010).
  - Query params: none.
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
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `409 PUBLICATION_IN_PROGRESS`, `422 BUSINESS_RULE_VIOLATION`.

### 2.10a Doctor text templates

- **GET** `/doctor-text-templates`
  - Description: List text templates available to the doctor (clinic scope + private).
  - Query params: `template_locale`, `scope` (`clinic|private|all`), `is_active`.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **POST** `/doctor-text-templates`
- **GET/PATCH/DELETE** `/doctor-text-templates/{id}`
  - Description: CRUD for doctor text templates.
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
  - Success: `201 CREATED`, `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `403 FORBIDDEN`, `409 TEMPLATE_NAME_CONFLICT`.

- **GET** `/medical-documents/{id}/versions`
  - Description: Version history. Doctor can view only if document is authored by them or in their assigned clinic scope.
  - Query params: pagination/sort by `-version_no`.
  - Response JSON: version list.
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

- **GET** `/medical-documents/{id}/audit-trail`
  - Description: Audit events related to the given document. Doctor can view only if document is authored by them or in their assigned clinic scope.
  - Query params: `page` (default `1`), `page_size` (default **20**, max **100**).
  - Response JSON: `{ "items": [...], "pagination": { "page", "page_size", "total" } }`.
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`, `403 FORBIDDEN`.

- **GET** `/medical-document-versions/{id}`
  - Description: Retrieve specific version details and processing state.
  - Response JSON: version object with PDF/HiDrive/SMS flags.
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

### 2.10a Intake documents (PDF) – RECEPTION/ADMIN

Access for **RECEPTION** and **ADMIN** only. RECEPTION sees only documents from assigned clinic sites; ADMIN sees all. Read-only resource (list, detail, PDF file preview).

- **GET** `/intake-documents`
  - Description: List intake document versions (generated PDFs). Used by reception and admin to browse/retrieve documents.
  - Query params: `queue_date` (YYYY-MM-DD), `pdf_generation_status` (PENDING, IN_PROGRESS, COMPLETED, FAILED), `patient_search`, `clinic_site_id`, `page` (default `1`), `page_size` (default **20**, max **100**).
  - Response JSON: `{ "items": [...], "pagination": { "page", "page_size", "total" } }`. Each item: `id`, `version_no`, `form_locale`, `pdf_generation_status`, `created_at`, `queue_entry_id`, `intake_form_id`, `queue_date`, `clinic_site_id`, `clinic_site_name`, `patient` (id, first_name, last_name, date_of_birth), `pdf_available`, `hidrive_sent`, `processing_error_message`.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN` (e.g. DOCTOR role).

- **GET** `/intake-documents/{id}`
  - Description: Detail of one intake document version.
  - Response JSON: detail object (like list item plus e.g. `pdf_local_path`, `pdf_checksum_sha256`, `hidrive_path`, `hidrive_sent_at`).
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`, `404 NOT_FOUND`.

- **GET** `/intake-documents/{id}/preview-pdf`
  - Description: Returns the PDF file for inline preview (`Content-Disposition: inline`). Available only when `pdf_generation_status == COMPLETED` and file exists under `MEDIA_ROOT`.
  - Response: `Content-Type: application/pdf`, binary body.
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND` (document out of scope, file missing, or status ≠ COMPLETED).

### 2.11 Imports (XLSX, scheduled, emergency)

- **POST** `/imports/patients/pdf` — **removed.** Patient import from Doctolib PDF was retired. Use admin "Import z pliku" (XLSX) or future `POST /imports/patients/xlsx` when implemented.

- **POST** `/imports/patients/emergency`
  - Description: Emergency template import path (US-017).
  - Query params: none.
  - Request: `multipart/form-data` with strict template file.
  - Response JSON: batch object.
  - Success: `202 ACCEPTED`.
  - Errors: `400 INVALID_TEMPLATE`, `422 MISSING_DOCTOLIB_ID`, `403 FORBIDDEN`.

- **GET** `/imports/batches`
  - Description: List import batches.
  - Query params: `limit` (default **20**, max **100**, same as other `parse_list_limit` lists).
  - Response JSON: batch list.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **GET** `/imports/batches/{id}`
  - Description: Batch details.
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
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

- **GET** `/imports/batches/{id}/errors`
  - Description: Row-level error report.
  - Query params: none.
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
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

- **GET** `/imports/templates/emergency.xlsx`
  - Description: Download emergency fallback template.
  - Query params: none.
  - Request JSON: none.
  - Response: binary file.
  - Success: `200 OK`.
  - Errors: `404 TEMPLATE_NOT_FOUND`.

### 2.12 Outbox and operations (Admin/Ops)

- **GET** `/outbox-events`
  - Description: Operational queue view.
  - Query params: `status`, `event_type`, `retry_count_gte`, `limit` (default **20**, max **100**; `parse_list_limit`).
  - Request JSON: none.
  - Response JSON: outbox events list.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **POST** `/outbox-events/{id}/retry`
  - Description: Force retry a failed/dead-letter event.
  - Request JSON:
    ```json
    {
      "reason": "manual retry after provider recovery"
    }
    ```
  - Response JSON: updated event.
  - Success: `200 OK`.
  - Errors: `409 EVENT_NOT_RETRYABLE`, `404 NOT_FOUND`, `403 FORBIDDEN`.

- **POST** `/operations/outbox/process`
  - Description: Manual trigger for outbox task-processing cycle (safe admin endpoint).
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
  - Success: `202 ACCEPTED`.
  - Errors: `403 FORBIDDEN`, `429 RATE_LIMITED`.

- **POST** `/operations/retention/run`
  - Description: Manual retention run for local PDFs older than 30 days.
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
  - Success: `202 ACCEPTED`.
  - Errors: `403 FORBIDDEN`.

### 2.13 Audit and observability

- **GET** `/audit-events`
  - Description: Audit trail query.
  - Query params: `event_type`, `actor_user_id`, `patient_id`, `medical_document_id`, `context_clinic_site_id`, `outbox_event_id`, `from`, `to` (UUIDs for entity IDs; ISO datetime for `from`/`to`), `page` (default `1`), `page_size` (default **20**, max **100**).
  - Response JSON: `{ "items": [...], "pagination": { "page", "page_size", "total" } }`. When an entity is anonymized or deleted, its FK may be NULL; the API still exposes the ID from `metadata._ref` for compliance.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **GET** `/observability/health`
  - Description: Liveness/readiness for app, DB, outbox task processing, integrations.
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
  - Success: `200 OK` / `503 SERVICE_UNAVAILABLE`.
  - Errors: none.

- **GET** `/observability/metrics`
  - Description: Metrics endpoint (Prometheus/OpenTelemetry exporter bridge) including required PRD counters and latencies.
  - Response: text metrics payload.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN` (if not internal network).

## 3. Authentication and Authorization

- Authentication:
  - Staff API: Django authenticated session cookie, secure/httponly/samesite settings, CSRF protection for state-changing requests.
  - **Tablet (poczekalnia):** Same session auth with role **TABLET**. No one-time token; tablet selects queue and patient, POST sessions returns `intake_form_id`; form access and submit are authorized by `request.user.role == TABLET` and intake form in allowed scope (e.g. queue). See [.ai/proces-poczekalni.md](.ai/proces-poczekalni.md).

- Authorization (RBAC by `staff_user.role`):
  - **TABLET**: only: list today's queues (choice), list queue entries for a queue, POST queue-entries/{id}/sessions, GET intake form context, PUT anamnesis/consents, signature upload, POST intake submit. No patient search, no queue CRUD, no user management.
  - `RECEPTION`: queues, queue entries, patient create/update, session generation (POST sessions), import operations read/write.
  - `DOCTOR`: medical document read/write, publish/republish, version view.
  - `ADMIN`: user management, consent dictionary, operational controls, full audit/outbox visibility.
  - Endpoint guards implemented via Django permission classes + object-level checks.

- Session/security controls:
  - Idle timeout enforced server-side (tablet session may be several hours; no patient data editing on tablet).
  - Brute-force protection on `/auth/login`.
  - Strict transport security (HSTS) and HTTPS redirect.
  - Passwords stored with Django password hashers only.
  - No secrets in code; environment-based config only.

- API hardening:
  - Rate limits (example policy):
    - `/auth/login`: 5 req/min/IP + username bucket.
  - write endpoints default: 60 req/min/user.
    - admin operations: 10 req/min/user.
  - Request size limits for signatures/uploads.
  - Input sanitization and allowlists for ordering/filter fields.
  - Audit logging for all security-sensitive actions (login failures, publish, retries, retention runs).

## 4. Validation and Business Logic

### 4.1 Resource validation rules

- `staff_user`
  - `username` unique, `email` unique (case-insensitive), `role` in `RECEPTION|DOCTOR|ADMIN|TABLET`.
  - `phone_number` regex: `^[0-9+() -]{7,20}$`.

- `patient`
  - Required: `first_name`, `last_name`, `date_of_birth`, `phone`, `email`.
  - `phone` regex: `^[0-9+() -]{7,20}$`.
  - `date_of_birth <= current_date`.
  - `(first_name, last_name, phone, date_of_birth)` unique.
  - `doctolib_patient_id` is optional but unique when present.

- `consulting_room`
  - Unique per site: `(clinic_site_id, code)`.

- `daily_queue`
  - Unique key: `(queue_date, clinic_site_id, consulting_room_id, shift_code)`.
  - `(consulting_room_id, clinic_site_id)` must reference same site-room relation.

- `queue_entry`
  - `position_no` unique within queue.
  - Optional `visit_external_id` unique per queue when present.
  - Status must follow allowed state machine.

- `patient_form_session`
  - **No token** – `token_hash` has been removed (migration). Session is identified by id; authorization for tablet flow is by role TABLET and queue/intake scope.
  - `expires_at > created_at`.
  - `consumed_at <= expires_at` if set.

- `consent_definition`
  - Unique `(code, version)`.
  - `effective_to >= effective_from` when set.

- `patient_intake_form`
  - One-to-one with `queue_entry`.
  - `body_map_data` must be JSON array.
  - `form_status='SUBMITTED'` requires `submitted_at` and `signature_file_path`.

- `patient_intake_consent`
  - Unique `(intake_form_id, consent_definition_id)`.
  - `accepted=true` requires `accepted_at`; `accepted=false` requires `accepted_at=null`.

- `medical_document`
  - One-to-one with `queue_entry` and `intake_form`.
  - `current_version_no >= 0`.

- `medical_document_version`
  - Unique `(medical_document_id, version_no)`.
  - `version_no > 0`.
  - `medical_payload` must be JSON object.
  - `PUBLISHED` requires `publish_request_id` and `published_at`.
  - `publish_locale` is required for `PUBLISHED` and must match `^(de|en|pl)(-[A-Z]{2})?$`.
  - `pdf_generation_status='COMPLETED'` requires `pdf_local_path`.
  - `hidrive_sent=true` requires completed PDF, `pdf_local_path`, and `hidrive_sent_at`.
  - `sms_sent=true` requires `sms_sent_at`.
  - `local_pdf_deleted_at` allowed only if `hidrive_sent=true` and `sms_sent=true`.

- `outbox_event`
  - Unique `(medical_document_version_id, event_type)`.
  - `retry_count` bounded (`0 <= retry_count <= max_retries`, `max_retries > 0`).
  - `payload` JSON object.
  - `aggregate_type='MEDICAL_DOCUMENT_VERSION'`.
  - `aggregate_id=medical_document_version_id`.

- `patient_import_batch` and `patient_import_error`
  - Non-negative counters in batch.
  - `row_number > 0` in error rows.

- `audit_event`
  - `metadata` must be JSON object. Reserved key `_ref` stores immutable copy of entity IDs (patient_id, medical_document_id, context_clinic_site_id, etc.) for compliance after anonymization/deletion.

### 4.2 Business logic implementation in API

- Manual patient add supports missing `doctolib_patient_id`:
  - If no `doctolib_patient_id`, API still creates the patient without assigning a temporary status or alert metadata.

- Unified ingestion:
  - Manual add, file import, and scheduled import pass through a shared ingestion service with same dedup and validation rules.

- Idempotent import:
  - Use patient uniqueness `(first_name, last_name, phone, date_of_birth)`, optional `doctolib_patient_id`, and visit external keys to avoid duplicate patient/visit creation.

- Latest-wins session model (no token):
  - Session generation creates a new `patient_form_session` (no token field) and atomically switches `queue_entry.active_session_id`.
  - Tablet (TABLET) or reception calls POST sessions; backend returns `intake_form_id`. No token validation endpoint.

- Intake submit transaction:
  - Verifies required active consents are accepted.
  - Verifies signature presence.
  - Marks form `SUBMITTED`, stamps `submitted_at`, marks session consumed (`consumed_at`) if applicable, and updates queue status in one transaction. Caller is authenticated (TABLET or RECEPTION/ADMIN); no token in request.

- Doctor workflow:
  - Draft save updates/creates latest draft version; doctor enters/edits text in `medical_payload` (e.g. `edited_text`, `summary_edited_text`).
  - Doctor persists final edited text (and optional generated text from template) in `medical_payload`.
  - Publish request must provide `publish_locale`; backend persists it on `medical_document_version` and uses it as the authoritative PDF language for outbox generation.
  - Publish uses row lock on `medical_document` and idempotency checks:
    - same `publish_request_id` returns success replay;
    - publication already in progress returns idempotent success (no duplicate outbox chain).

- Transactional outbox chain:
  - Publish transaction enqueues `GENERATE_PDF`.
  - Django Tasks processing enqueues `HIDRIVE_UPLOAD` after successful PDF.
  - Django Tasks processing enqueues `SMS_SEND` after successful upload. **SMS content:** logistic only – „Nowa dokumentacja w Cogito“ (no link; patient fetches via portal wyniki).
  - Retries and dead-letter managed via outbox status/retry fields.

- Patient results portal (US-018, PRD 3.4a):
  - SMS is strictly logistic; patient visits e.g. wyniki.cogitomedica.pl.
  - Login: phone + date_of_birth (verified at reception).
  - OTP: 6-digit code, 15 min validity; sent asynchronously when phone+DOB match.
  - After valid OTP: serve PDF via HTTPS. **Audit (`audit_event`):** typed events such as `PATIENT_RESULTS_OTP_REQUEST`, `PATIENT_RESULTS_OTP_VERIFY`, `PATIENT_RESULTS_DOCUMENTS_LISTED`, `PATIENT_RESULTS_PDF_DOWNLOAD`, `PATIENT_RESULTS_PDF_DOWNLOAD_DENIED` with `event_time`, `patient_id` where applicable, and `metadata` including `client_ip` and outcomes (e.g. OTP request outcome, denied-download reason).
  - Doctor can revoke publication; patient will not see revoked file after OTP entry.

- Republishing:
  - Editing a published document creates next version and repeats chain; archive path is overwritten per business rule.
  - API supports optional `resend_sms`.

- Retention policy:
  - Scheduled/manual retention deletes local PDF only when both `hidrive_sent=true` and `sms_sent=true` and document age exceeds 30 days.
  - Deletion action creates audit event.

- Operational visibility:
  - API exposes health/metrics and outbox/import inspection endpoints.
  - Required PRD metrics are exported (`pending_count`, `failed_count`, `dead_letter_count`, `oldest_pending_age_seconds`, p95/p99 latencies, provider success ratios, import error rates).

### 4.3 `anamnesis_payload` v1 contract (Q1–Q11)

- API reads/writes anamnesis using stable codes only (`question_code`, `option_code`), independent of DE/EN UI wording.
- Localization (`question_text`, `option label`) is resolved from `form_locale` and `anamnesis-definitions`.

Minimal `PUT /intake-forms/{id}/anamnesis` request:

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

Option code mapping for Q1–Q11:
- `NO`, `YES`, `UNKNOWN` (binary and tri-state questions),
- `LOWER_BACK`, `THORACIC_SPINE`, `ABDOMEN`, `OTHER_LOCATION` (lesion location).

### 4.4 `medical_payload` v1 contract (Doctor Befund)

- Schema version: `medical_payload_schema_version: 1`.
- `medical_payload` stores both structured and narrative outputs:
  - global selections (`fitzpatrick_type`, `overall_image_assessment`, `recommendations`, `final_assessment`),
  - lesion groups (`lesions[]`) – each group has a list of Wideodermatoskop numbers and one shared description,
  - generated and final text (`generated_text`, `edited_text` per group; `summary_generated_text`, `summary_edited_text`).
- Text persistence is language-agnostic; `authoring_locale` records the doctor's working language.

**`lesions[]` element structure:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lesion_numbers` | array of integer | yes | Lesion numbers from Wideodermatoskop in this description group |
| `dermatoscopic_features` | array of string | no | Dermatoscopic feature codes |
| `clinical_assessment` | string | yes | Clinical-dermatoscopic assessment code |
| `malignancy_risk` | string | yes | Malignancy risk code |
| `generated_text` | string | no | System-generated text |
| `edited_text` | string | no | Text after doctor edit |

**`lesion_numbers` validation:**
- Must not be empty: `lesion_numbers.length >= 1`.
- No duplicates within the array: after removing duplicates the array length must be unchanged (e.g. `[2, 3, 2]` → error).

**Validation rules (for implementation):** For each `lesions[]` element: `lesion_numbers` non-empty and no duplicates; `clinical_assessment` and `malignancy_risk` from defined value sets. Optionally: each Wideodermatoskop number appears in only one group across the whole `lesions` array (global uniqueness) – product decision.

Example:

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

Enum codes (Befund v1):
- `examination_scope[]`: `INTIMATE_AREA_NOT_EXAMINED`, `ORAL_MUCOSA_NOT_EXAMINED`
- `fitzpatrick_type`: `TYPE_I`, `TYPE_II`, `TYPE_III`, `TYPE_IV`, `TYPE_V`, `TYPE_VI`, `TYPE_II_III`, `UNDETERMINED`
- `overall_image_assessment`: `NO_CONTROL_NEEDED`, `CONTROL_NEEDED`
- `lesions[].dermatoscopic_features[]`: `ASYMMETRY`, `IRREGULAR_BORDER`, `INHOMOGENEOUS_PIGMENTATION`, `MULTICOLOR`, `ATYPICAL_PIGMENT_NETWORK`, `IRREGULAR_GLOBULES`, `IRREGULAR_DOTS`, `STRUCTURELESS_AREAS`, `ATYPICAL_VASCULAR_STRUCTURES`, `REGRESSION_AREAS`
- `lesions[].clinical_assessment`: `UNREMARKABLE`, `SLIGHTLY_ATYPICAL`, `CONTROL_NEEDED`, `SUSPICIOUS`
- `lesions[].malignancy_risk`: `NO_SUSPICION`, `LOW_SUSPICION`, `CANNOT_EXCLUDE`
- `recommendations[]`: `FOLLOWUP_3_MONTHS`, `FOLLOWUP_6_MONTHS`, `PROMPT_VISIT_ON_CHANGE`, `NO_SHORT_TERM_FOLLOWUP_REQUIRED`
- `final_assessment`: `NO_HIGH_GRADE_SUSPICION`, `HIGH_GRADE_CANNOT_BE_EXCLUDED`

