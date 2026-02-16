# REST API Plan

## 0. Assumptions
- API base path is `/api/v1`.
- Transport is HTTPS only.
- JSON is default payload format (`application/json`), except file upload endpoints (`multipart/form-data`).
- Authentication is session-based for staff web UI (Django auth cookie + CSRF) and bearer token for tablet/patient links.
- Time format is ISO 8601 UTC.
- All list endpoints support pagination/filtering/sorting with common parameters:
  - `page` (default `1`)
  - `page_size` (default `20`, max `100`)
  - `ordering` (comma-separated fields, prefix `-` for desc)
  - resource-specific filter params

## 1. Resources
- `auth` -> `staff_user` (login, logout, current session, role access)
- `staff-users` -> `staff_user`
- `patients` -> `patient`
- `patient-contact-history` -> `patient_contact_history`
- `clinic-sites` -> `clinic_site`
- `consulting-rooms` -> `consulting_room`
- `daily-queues` -> `daily_queue`
- `queue-entries` -> `queue_entry`
- `tablet-devices` -> `tablet_device`
- `patient-sessions` -> `patient_form_session` (one-time token lifecycle, latest-wins)
- `consent-definitions` -> `consent_definition`
- `intake-forms` -> `patient_intake_form`
- `intake-consents` -> `patient_intake_consent`
- `medical-documents` -> `medical_document`
- `medical-document-versions` -> `medical_document_version`
- `imports` -> `patient_import_batch`, `patient_import_error`
- `outbox-events` -> `outbox_event`
- `audit-events` -> `audit_event`
- `operations` -> domain actions not pure CRUD (publish, merge, retry, retention)
- `observability` -> metrics/health surfaces for operations

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

### 2.3 Patients

- **GET** `/patients`
  - Description: Search/list patients.
  - Query params: `search`, `last_name`, `date_of_birth`, `phone`, `identity_status`, `doctolib_patient_id`, `is_active`.
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
          "identity_status": "TEMPORARY",
          "identity_alert_created_at": "2026-02-16T09:00:00Z",
          "identity_resolution_due_at": "2026-02-17T09:00:00Z"
        }
      ],
      "pagination": {"page": 1, "page_size": 20, "total": 1}
    }
    ```
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **POST** `/patients`
  - Description: Create patient (manual path supports temporary identity).
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
  - Success: `201 CREATED`.
  - Errors: `400 VALIDATION_ERROR`, `409 DUPLICATE_EXTERNAL_SOURCE`, `422 INVALID_BUSINESS_STATE`.

- **GET** `/patients/{id}`
- **PATCH** `/patients/{id}`
  - Description: Read/update patient.
  - Query params: none.
  - Request JSON (`PATCH`): mutable demographic/contact fields.
  - Response JSON: patient object.
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `409 UNIQUE_CONSTRAINT`.

- **POST** `/patients/{id}/merge`
  - Description: Merge temporary patient into confirmed patient (US-018).
  - Query params: none.
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
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `409 MERGE_CONFLICT`, `422 SOURCE_NOT_TEMPORARY`.

- **GET** `/patients/{id}/contact-history`
  - Description: Contact changes timeline.
  - Query params: pagination only.
  - Request JSON: none.
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
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`, `403 FORBIDDEN`.

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
  - Description: Manage dedicated tablets.
  - Query params: `is_active`, `search`.
  - Request JSON:
    ```json
    {
      "name": "Tablet-1",
      "device_code": "TAB001",
      "is_active": true
    }
    ```
  - Response JSON: tablet object.
  - Success: `200 OK`, `201 CREATED`.
  - Errors: `400 VALIDATION_ERROR`, `409 DUPLICATE_DEVICE`.

- **POST** `/tablet-devices/{id}/heartbeat`
  - Description: Update device `last_seen_at`.
  - Request JSON: `{}`.
  - Response JSON: `{"last_seen_at":"2026-02-16T10:00:00Z"}`.
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

### 2.7 Patient sessions and token flow (latest-wins)

- **POST** `/queue-entries/{id}/sessions`
  - Description: Generate one-time patient link/token and set as active session (US-004).
  - Query params: none.
  - Request JSON:
    ```json
    {
      "tablet_device_id": "uuid",
      "ttl_minutes": 30
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
  - Success: `201 CREATED`.
  - Errors: `404 QUEUE_ENTRY_NOT_FOUND`, `409 ENTRY_NOT_ELIGIBLE`, `422 TOKEN_GENERATION_FAILED`.

- **POST** `/patient-sessions/validate`
  - Description: Validate token before tablet form access.
  - Query params: none.
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
      "patient_snapshot": {
        "first_name": "Jan",
        "last_name": "Kowalski",
        "date_of_birth": "1980-01-01",
        "phone": "+49111111111",
        "email": "jan@example.com"
      }
    }
    ```
  - Success: `200 OK`.
  - Errors: `401 TOKEN_INVALID_OR_EXPIRED`, `409 TOKEN_NOT_ACTIVE_SESSION`, `410 TOKEN_CONSUMED`.

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

### 2.9 Intake forms and consents (Tablet flow)

- **GET** `/intake-forms/by-session/{session_id}`
  - Description: Fetch or initialize intake form context for patient tablet.
  - Query params: none.
  - Request JSON: none.
  - Response JSON:
    ```json
    {
      "intake_form_id": "uuid",
      "queue_entry_id": "uuid",
      "form_status": "IN_PROGRESS",
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
  - Errors: `401 TOKEN_INVALID_OR_EXPIRED`, `404 SESSION_NOT_FOUND`.

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
  - Description: Finalize form and consume token in one transaction (US-005/006/007).
  - Query params: none.
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
  - Success: `200 OK`.
  - Errors: `400 REQUIRED_CONSENTS_MISSING`, `400 SIGNATURE_REQUIRED`, `401 TOKEN_INVALID_OR_EXPIRED`, `409 FORM_ALREADY_SUBMITTED`.

### 2.10 Medical documents and doctor workflow

- **GET** `/medical-documents`
  - Description: List doctor work queue.
  - Query params: `status`, `queue_date`, `doctor_view` (`pending_review`, `published`, `failed`), `patient_search`.
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
        "body_map_data": []
      },
      "current_version": {
        "version_no": 2,
        "version_status": "DRAFT",
        "medical_payload_schema_version": 1,
        "medical_payload": {},
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
        "symptoms": ["pain"],
        "notes": "Clinical observation"
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
      "outbox": [
        {"event_type": "GENERATE_PDF", "status": "PENDING"}
      ]
    }
    ```
  - Success: `200 OK`.
  - Errors: `400 VALIDATION_ERROR`, `409 PUBLICATION_IN_PROGRESS`, `422 BUSINESS_RULE_VIOLATION`.

- **GET** `/medical-documents/{id}/versions`
  - Description: Version history.
  - Query params: pagination/sort by `-version_no`.
  - Response JSON: version list.
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

- **GET** `/medical-document-versions/{id}`
  - Description: Retrieve specific version details and processing state.
  - Response JSON: version object with PDF/HiDrive/SMS flags.
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

### 2.11 Imports (manual, scheduled, emergency)

- **POST** `/imports/patients`
  - Description: Upload `.csv/.xlsx` for daily import (US-003/011/015).
  - Query params: `mode` (`daily` or `scheduled`).
  - Request: `multipart/form-data` with file.
  - Response JSON:
    ```json
    {
      "batch_id": "uuid",
      "status": "PROCESSING",
      "source_system": "DOCTOLIB_EXPORT"
    }
    ```
  - Success: `202 ACCEPTED`.
  - Errors: `400 INVALID_FILE_FORMAT`, `422 TEMPLATE_MISMATCH`, `403 FORBIDDEN`.

- **POST** `/imports/patients/emergency`
  - Description: Emergency template import path (US-017).
  - Query params: none.
  - Request: `multipart/form-data` with strict template file.
  - Response JSON: batch object.
  - Success: `202 ACCEPTED`.
  - Errors: `400 INVALID_TEMPLATE`, `422 MISSING_DOCTOLIB_ID`, `403 FORBIDDEN`.

- **GET** `/imports/batches`
  - Description: List import batches.
  - Query params: `status`, `source_system`, `import_type`, `created_from`, `created_to`.
  - Response JSON: batch list.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **GET** `/imports/batches/{id}`
  - Description: Batch details.
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
  - Success: `200 OK`.
  - Errors: `404 NOT_FOUND`.

- **GET** `/imports/batches/{id}/errors`
  - Description: Row-level error report.
  - Query params: pagination.
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
  - Query params: `status`, `event_type`, `available_before`, `retry_count_gte`.
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
  - Description: Manual trigger for outbox worker cycle (safe admin endpoint).
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
  - Query params: `event_type`, `actor_user_id`, `patient_id`, `medical_document_id`, `from`, `to`.
  - Response JSON: audit events list.
  - Success: `200 OK`.
  - Errors: `403 FORBIDDEN`.

- **GET** `/observability/health`
  - Description: Liveness/readiness for app, DB, queue worker, integrations.
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
  - Patient tablet flow: signed opaque one-time token validated against `patient_form_session.token_hash`.
  - Token validity requires all conditions:
    - token hash matches active session;
    - `session.id == queue_entry.active_session_id`;
    - `consumed_at IS NULL`;
    - `expires_at > now()`.

- Authorization (RBAC by `staff_user.role`):
  - `RECEPTION`: queues, queue entries, patient create/update, token generation, import operations read/write.
  - `DOCTOR`: medical document read/write, publish/republish, version view.
  - `ADMIN`: user management, consent dictionary, merge patients, operational controls, full audit/outbox visibility.
  - Endpoint guards implemented via Django permission classes + object-level checks.

- Session/security controls:
  - Idle timeout enforced server-side.
  - Brute-force protection on `/auth/login` and token validation endpoint.
  - Strict transport security (HSTS) and HTTPS redirect.
  - Passwords stored with Django password hashers only.
  - No secrets in code; environment-based config only.

- API hardening:
  - Rate limits (example policy):
    - `/auth/login`: 5 req/min/IP + username bucket.
    - `/patient-sessions/validate`: 30 req/min/IP.
    - write endpoints default: 60 req/min/user.
    - admin operations: 10 req/min/user.
  - Request size limits for signatures/uploads.
  - Input sanitization and allowlists for ordering/filter fields.
  - Audit logging for all security-sensitive actions (login failures, publish, retries, merges, retention runs).

## 4. Validation and Business Logic

### 4.1 Resource validation rules

- `staff_user`
  - `username` unique, `email` unique (case-insensitive), `role` in `RECEPTION|DOCTOR|ADMIN`.
  - `phone_number` regex: `^[0-9+() -]{7,20}$`.

- `patient`
  - Required: `first_name`, `last_name`, `date_of_birth`, `phone`, `email`.
  - `phone` regex: `^[0-9+() -]{7,20}$`.
  - `date_of_birth <= current_date`.
  - `(external_source, external_source_id)` unique.
  - If `doctolib_patient_id` is null, `identity_alert_created_at` and `identity_resolution_due_at` must be set.
  - `identity_resolution_due_at >= identity_alert_created_at` when both present.

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
  - `token_hash` unique.
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
  - `metadata` must be JSON object.

### 4.2 Business logic implementation in API

- Manual patient add supports temporary identity:
  - If no `doctolib_patient_id`, API sets temporary identity alert timestamps and returns alert metadata.

- Unified ingestion:
  - Manual add, file import, and scheduled import pass through a shared ingestion service with same dedup and validation rules.

- Idempotent import:
  - Use external identifiers (`doctolib_patient_id`, visit external keys) to avoid duplicate patient/visit creation.

- Latest-wins token model:
  - Session generation creates a new `patient_form_session` and atomically switches `queue_entry.active_session_id`.
  - Old tokens become invalid automatically.

- Intake submit transaction:
  - Verifies required active consents are accepted.
  - Verifies signature presence.
  - Marks form `SUBMITTED`, stamps `submitted_at`, consumes token (`consumed_at`), and updates queue status in one transaction.

- Doctor workflow:
  - Draft save updates/creates latest draft version.
  - Publish uses row lock on `medical_document` and idempotency checks:
    - same `publish_request_id` returns success replay;
    - publication already in progress returns idempotent success (no duplicate outbox chain).

- Transactional outbox chain:
  - Publish transaction enqueues `GENERATE_PDF`.
  - Worker enqueues `HIDRIVE_UPLOAD` after successful PDF.
  - Worker enqueues `SMS_SEND` after successful upload.
  - Retries and dead-letter managed via outbox status/retry fields.

- Republishing:
  - Editing a published document creates next version and repeats chain; archive path is overwritten per business rule.
  - API supports optional `resend_sms`.

- Retention policy:
  - Scheduled/manual retention deletes local PDF only when both `hidrive_sent=true` and `sms_sent=true` and document age exceeds 30 days.
  - Deletion action creates audit event.

- Operational visibility:
  - API exposes health/metrics and outbox/import inspection endpoints.
  - Required PRD metrics are exported (`pending_count`, `failed_count`, `dead_letter_count`, `oldest_pending_age_seconds`, p95/p99 latencies, provider success ratios, import error rates).

