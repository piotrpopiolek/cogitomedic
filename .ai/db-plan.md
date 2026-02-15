# Schemat bazy danych PostgreSQL – Cogitomedica Digital Consents

## 1. Lista tabel z ich kolumnami, typami danych i ograniczeniami

### 1.1. Tabele docelowe (bez kompatybilności wstecznej)

#### `staff_user`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `password` `varchar(128)` NOT NULL
- `last_login` `timestamptz` NULL
- `is_superuser` `boolean` NOT NULL DEFAULT `false`
- `username` `varchar(150)` NOT NULL UNIQUE
- `first_name` `varchar(50)` NOT NULL
- `last_name` `varchar(100)` NOT NULL
- `email` `citext` NOT NULL UNIQUE
- `phone_number` `varchar(20)` NULL
- `is_staff` `boolean` NOT NULL DEFAULT `false`
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `date_joined` `timestamptz` NOT NULL DEFAULT `now()`
- `code` `varchar(50)` NOT NULL DEFAULT `''`
- `role` `staff_role_enum` NOT NULL DEFAULT `'RECEPTION'`
- `preferred_locale` `varchar(10)` NOT NULL DEFAULT `'de-DE'`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `CHECK (role IN ('RECEPTION','DOCTOR','ADMIN'))`
  - `CHECK (phone_number IS NULL OR phone_number ~ '^[0-9+() -]{7,20}$')`

### 1.2. Pozostałe tabele wymagane przez PRD

#### `patient`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `first_name` `varchar(100)` NOT NULL
- `last_name` `varchar(100)` NOT NULL
- `date_of_birth` `date` NOT NULL
- `phone` `varchar(20)` NOT NULL
- `email` `citext` NOT NULL
- `doctolib_patient_id` `varchar(64)` NULL UNIQUE
- `identity_status` `patient_identity_status_enum` NOT NULL DEFAULT `'CONFIRMED'`
- `identity_alert_created_at` `timestamptz` NULL
- `identity_resolution_due_at` `timestamptz` NULL
- `street` `varchar(150)` NULL
- `city` `varchar(100)` NULL
- `postal_code` `varchar(20)` NULL
- `country_code` `char(2)` NOT NULL DEFAULT `'DE'`
- `external_source` `varchar(30)` NULL
- `external_source_id` `varchar(100)` NULL
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (external_source, external_source_id)`
  - `CHECK (phone ~ '^[0-9+() -]{7,20}$')`
  - `CHECK (date_of_birth <= current_date)`
  - `CHECK ((identity_status = 'CONFIRMED' AND doctolib_patient_id IS NOT NULL) OR (identity_status = 'TEMPORARY' AND doctolib_patient_id IS NULL AND identity_alert_created_at IS NOT NULL AND identity_resolution_due_at IS NOT NULL))`
  - `CHECK (identity_resolution_due_at IS NULL OR identity_alert_created_at IS NULL OR identity_resolution_due_at >= identity_alert_created_at)`

#### `patient_contact_history`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `patient_id` `uuid` NOT NULL FK -> `patient(id)` ON DELETE CASCADE
- `phone` `varchar(20)` NULL
- `email` `citext` NULL
- `changed_by_user_id` `uuid` NULL FK -> `staff_user(id)` ON DELETE SET NULL
- `changed_at` `timestamptz` NOT NULL DEFAULT `now()`
- `reason` `varchar(100)` NULL

#### `clinic_site`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `code` `varchar(20)` NOT NULL UNIQUE
- `name` `varchar(120)` NOT NULL
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`

#### `consulting_room`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `clinic_site_id` `uuid` NOT NULL FK -> `clinic_site(id)` ON DELETE RESTRICT
- `code` `varchar(20)` NOT NULL
- `name` `varchar(120)` NOT NULL
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (clinic_site_id, code)`
  - `UNIQUE (id, clinic_site_id)`

#### `daily_queue`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `queue_date` `date` NOT NULL
- `clinic_site_id` `uuid` NOT NULL FK -> `clinic_site(id)` ON DELETE RESTRICT
- `consulting_room_id` `uuid` NOT NULL
- `shift_code` `queue_shift_enum` NOT NULL DEFAULT `'FULL_DAY'`
- `source` `queue_source_enum` NOT NULL DEFAULT `'MANUAL'`
- `status` `queue_status_enum` NOT NULL DEFAULT `'OPEN'`
- `created_by_user_id` `uuid` NOT NULL FK -> `staff_user(id)` ON DELETE RESTRICT
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (queue_date, clinic_site_id, consulting_room_id, shift_code)`
  - `FK (consulting_room_id, clinic_site_id) -> consulting_room(id, clinic_site_id) ON DELETE RESTRICT`

#### `queue_entry`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `daily_queue_id` `uuid` NOT NULL FK -> `daily_queue(id)` ON DELETE CASCADE
- `patient_id` `uuid` NOT NULL FK -> `patient(id)` ON DELETE RESTRICT
- `active_session_id` `uuid` NULL FK -> `patient_form_session(id)` ON DELETE SET NULL
- `entry_status` `queue_entry_status_enum` NOT NULL DEFAULT `'WAITING'`
- `position_no` `integer` NOT NULL
- `visit_external_id` `varchar(100)` NULL
- `appointment_time` `timestamptz` NULL
- `notes` `text` NULL
- `created_by_user_id` `uuid` NOT NULL FK -> `staff_user(id)` ON DELETE RESTRICT
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (daily_queue_id, position_no)`

#### `tablet_device`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `name` `varchar(50)` NOT NULL UNIQUE
- `device_code` `varchar(50)` NOT NULL UNIQUE
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `last_seen_at` `timestamptz` NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`

#### `patient_form_session`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `queue_entry_id` `uuid` NOT NULL FK -> `queue_entry(id)` ON DELETE CASCADE
- `tablet_device_id` `uuid` NULL FK -> `tablet_device(id)` ON DELETE SET NULL
- `token_hash` `char(64)` NOT NULL UNIQUE
- `expires_at` `timestamptz` NOT NULL
- `consumed_at` `timestamptz` NULL
- `created_by_user_id` `uuid` NOT NULL FK -> `staff_user(id)` ON DELETE RESTRICT
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `CHECK (expires_at > created_at)`
  - `CHECK (consumed_at IS NULL OR consumed_at <= expires_at)`

#### `consent_definition`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `code` `varchar(60)` NOT NULL
- `version` `integer` NOT NULL
- `title_de` `varchar(200)` NOT NULL
- `content_de` `text` NOT NULL
- `is_required` `boolean` NOT NULL DEFAULT `true`
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `display_order` `smallint` NOT NULL DEFAULT `0`
- `effective_from` `date` NOT NULL DEFAULT `current_date`
- `effective_to` `date` NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (code, version)`
  - `CHECK (effective_to IS NULL OR effective_to >= effective_from)`

#### `patient_intake_form`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `queue_entry_id` `uuid` NOT NULL UNIQUE FK -> `queue_entry(id)` ON DELETE CASCADE
- `session_id` `uuid` NOT NULL UNIQUE FK -> `patient_form_session(id)` ON DELETE RESTRICT
- `form_status` `intake_status_enum` NOT NULL DEFAULT `'IN_PROGRESS'`
- `body_map_schema_version` `smallint` NOT NULL DEFAULT `1`
- `body_map_data` `jsonb` NOT NULL DEFAULT `'[]'::jsonb`
- `signature_file_path` `varchar(500)` NULL
- `signature_sha256` `char(64)` NULL
- `submitted_at` `timestamptz` NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `CHECK (jsonb_typeof(body_map_data) = 'array')`
  - `CHECK ((form_status <> 'SUBMITTED') OR (submitted_at IS NOT NULL AND signature_file_path IS NOT NULL))`

#### `patient_intake_consent`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `intake_form_id` `uuid` NOT NULL FK -> `patient_intake_form(id)` ON DELETE CASCADE
- `consent_definition_id` `uuid` NOT NULL FK -> `consent_definition(id)` ON DELETE RESTRICT
- `accepted` `boolean` NOT NULL
- `accepted_at` `timestamptz` NULL
- Ograniczenia:
  - `UNIQUE (intake_form_id, consent_definition_id)`
  - `CHECK ((accepted = true AND accepted_at IS NOT NULL) OR (accepted = false AND accepted_at IS NULL))`

#### `medical_document`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `queue_entry_id` `uuid` NOT NULL UNIQUE FK -> `queue_entry(id)` ON DELETE RESTRICT
- `intake_form_id` `uuid` NOT NULL FK -> `patient_intake_form(id)` ON DELETE RESTRICT
- `status` `medical_doc_status_enum` NOT NULL DEFAULT `'DRAFT'`
- `current_version_no` `integer` NOT NULL DEFAULT `0`
- `last_published_at` `timestamptz` NULL
- `created_by_user_id` `uuid` NOT NULL FK -> `staff_user(id)` ON DELETE RESTRICT
- `updated_by_user_id` `uuid` NULL FK -> `staff_user(id)` ON DELETE SET NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `CHECK (current_version_no >= 0)`

#### `medical_document_version`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `medical_document_id` `uuid` NOT NULL FK -> `medical_document(id)` ON DELETE CASCADE
- `version_no` `integer` NOT NULL
- `version_status` `doc_version_status_enum` NOT NULL DEFAULT `'DRAFT'`
- `pdf_generation_status` `pdf_status_enum` NOT NULL DEFAULT `'PENDING'`
- `medical_payload_schema_version` `smallint` NOT NULL DEFAULT `1`
- `medical_payload` `jsonb` NOT NULL DEFAULT '{}'::jsonb
- `diagnosis_code` `varchar(50)` NULL
- `procedure_code` `varchar(50)` NULL
- `pdf_local_path` `varchar(500)` NULL
- `pdf_checksum_sha256` `char(64)` NULL
- `hidrive_path` `varchar(500)` NULL
- `hidrive_sent` `boolean` NOT NULL DEFAULT `false`
- `hidrive_sent_at` `timestamptz` NULL
- `sms_sent` `boolean` NOT NULL DEFAULT `false`
- `sms_sent_at` `timestamptz` NULL
- `local_pdf_deleted_at` `timestamptz` NULL
- `publish_requested_by_user_id` `uuid` NULL FK -> `staff_user(id)` ON DELETE SET NULL
- `published_by_user_id` `uuid` NULL FK -> `staff_user(id)` ON DELETE SET NULL
- `published_at` `timestamptz` NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (medical_document_id, version_no)`
  - `CHECK (version_no > 0)`
  - `CHECK (jsonb_typeof(medical_payload) = 'object')`
  - `CHECK ((version_status <> 'PUBLISHED') OR (published_at IS NOT NULL AND pdf_local_path IS NOT NULL))`
  - `CHECK ((hidrive_sent = false) OR hidrive_sent_at IS NOT NULL)`
  - `CHECK ((sms_sent = false) OR sms_sent_at IS NOT NULL)`
- `CHECK (local_pdf_deleted_at IS NULL OR (hidrive_sent = true AND sms_sent = true))`

#### `outbox_event`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `medical_document_version_id` `uuid` NOT NULL FK -> `medical_document_version(id)` ON DELETE CASCADE
- `aggregate_type` `varchar(50)` NOT NULL DEFAULT `'MEDICAL_DOCUMENT_VERSION'`
- `aggregate_id` `uuid` NOT NULL
- `event_type` `outbox_event_type_enum` NOT NULL
- `payload_schema_version` `smallint` NOT NULL DEFAULT `1`
- `payload` `jsonb` NOT NULL
- `status` `outbox_status_enum` NOT NULL DEFAULT `'PENDING'`
- `retry_count` `smallint` NOT NULL DEFAULT `0`
- `max_retries` `smallint` NOT NULL DEFAULT `10`
- `available_at` `timestamptz` NOT NULL DEFAULT `now()`
- `locked_at` `timestamptz` NULL
- `processed_at` `timestamptz` NULL
- `error_message` `text` NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `CHECK (retry_count >= 0 AND max_retries > 0 AND retry_count <= max_retries)`
  - `CHECK (jsonb_typeof(payload) = 'object')`
  - `CHECK (aggregate_type = 'MEDICAL_DOCUMENT_VERSION')`
  - `CHECK (aggregate_id = medical_document_version_id)`

#### `patient_import_batch`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `source_file_name` `varchar(255)` NOT NULL
- `source_file_sha256` `char(64)` NOT NULL
- `import_type` `import_type_enum` NOT NULL DEFAULT `'DAILY_FILE_IMPORT'`
- `source_system` `import_source_system_enum` NOT NULL DEFAULT `'DOCTOLIB_EXPORT'`
- `status` `import_status_enum` NOT NULL DEFAULT `'PROCESSING'`
- `total_rows` `integer` NOT NULL DEFAULT `0`
- `inserted_rows` `integer` NOT NULL DEFAULT `0`
- `error_rows` `integer` NOT NULL DEFAULT `0`
- `created_by_user_id` `uuid` NOT NULL FK -> `staff_user(id)` ON DELETE RESTRICT
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `finished_at` `timestamptz` NULL
- Ograniczenia:
  - `CHECK (total_rows >= 0 AND inserted_rows >= 0 AND error_rows >= 0)`

#### `patient_import_error`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `batch_id` `uuid` NOT NULL FK -> `patient_import_batch(id)` ON DELETE CASCADE
- `row_number` `integer` NOT NULL
- `error_code` `varchar(50)` NOT NULL
- `error_message` `text` NOT NULL
- `raw_row` `jsonb` NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `CHECK (row_number > 0)`

#### `audit_event`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `event_time` `timestamptz` NOT NULL DEFAULT `now()`
- `event_type` `varchar(80)` NOT NULL
- `actor_user_id` `uuid` NULL FK -> `staff_user(id)` ON DELETE SET NULL
- `patient_id` `uuid` NULL FK -> `patient(id)` ON DELETE SET NULL
- `medical_document_id` `uuid` NULL FK -> `medical_document(id)` ON DELETE SET NULL
- `outbox_event_id` `uuid` NULL FK -> `outbox_event(id)` ON DELETE SET NULL
- `metadata` `jsonb` NOT NULL DEFAULT '{}'::jsonb
- Ograniczenia:
  - `CHECK (jsonb_typeof(metadata) = 'object')`

## 2. Relacje między tabelami

- `staff_user` 1:N `daily_queue` (użytkownik tworzy wiele list dziennych).
- `clinic_site` 1:N `consulting_room` (lokalizacja ma wiele gabinetów).
- `consulting_room` 1:N `daily_queue` (gabinet ma wiele list dziennych w czasie).
- `daily_queue` 1:N `queue_entry` (lista dzienna zawiera wiele wpisów pacjentów).
- `patient` 1:N `queue_entry` (pacjent może mieć wiele wizyt/wpisów).
- `queue_entry` 1:N `patient_form_session` (historia regeneracji sesji/tokenów).
- `queue_entry.active_session_id` wskazuje aktualnie obowiązującą sesję w modelu `latest-wins`.
- `queue_entry` 1:1 `patient_intake_form` (jeden formularz pacjenta na wpis kolejki).
- `patient_intake_form` N:M `consent_definition` przez `patient_intake_consent`.
- `queue_entry` 1:1 `medical_document` (jeden dokument medyczny dla jednego przebiegu wizyty).
- `medical_document` 1:N `medical_document_version` (wersjonowanie szkic/publikacja/republikacja).
- `medical_document_version` 1:N `outbox_event` (relacja egzekwowana FK `outbox_event.medical_document_version_id`; np. `HIDRIVE_UPLOAD`, potem `SMS_SEND`).
- `patient_import_batch` 1:N `patient_import_error`.
- `patient` 1:N `patient_contact_history`.
- Relacje ról:
  - `staff_user.role='RECEPTION'` zarządza `daily_queue`, importami i tokenami.
  - `staff_user.role='DOCTOR'` edytuje `medical_document` i publikuje `medical_document_version`.
  - `staff_user.role='ADMIN'` zarządza słownikami (`consent_definition`) i użytkownikami.

## 3. Indeksy

### 3.1. Indeksy krytyczne (operacyjne)
- `patient(last_name, first_name, date_of_birth)`
- `patient(phone)`
- `patient(identity_status, created_at DESC)`
- `daily_queue(queue_date)`
- `daily_queue(queue_date, clinic_site_id, consulting_room_id, shift_code)` UNIQUE
- `queue_entry(daily_queue_id, entry_status, position_no)`
- `queue_entry(patient_id, created_at DESC)`
- `queue_entry(active_session_id)`
- `patient_form_session(token_hash)` UNIQUE
- `patient_form_session(queue_entry_id, consumed_at)`
- `patient_form_session(queue_entry_id, created_at DESC)`
- `consent_definition(code, is_active, effective_from DESC)`
- `patient_intake_form(form_status, submitted_at)`
- `patient_intake_consent(intake_form_id, accepted)`
- `medical_document(status, updated_at DESC)`
- `medical_document_version(medical_document_id, version_no DESC)` UNIQUE
- `medical_document_version(version_status, published_at DESC)`
- `medical_document_version(hidrive_sent, sms_sent, published_at)` (retencja + monitoring)
- `outbox_event(status, available_at)`
- `outbox_event(event_type, status, retry_count, available_at, payload_schema_version)`
- `outbox_event(medical_document_version_id, created_at DESC)`
- `patient_import_batch(status, created_at DESC)`
- `patient_import_batch(source_system, created_at DESC)`
- `audit_event(event_time DESC)`

### 3.2. Indeksy częściowe (PostgreSQL partial indexes)
- `outbox_event(status, available_at)` WHERE `status IN ('PENDING','FAILED')`
- `medical_document_version(published_at)` WHERE `version_status='PUBLISHED' AND hidrive_sent=true AND sms_sent=true AND local_pdf_deleted_at IS NULL`
- `patient_form_session(expires_at)` WHERE `consumed_at IS NULL`
- `queue_entry(daily_queue_id, position_no)` WHERE `entry_status IN ('WAITING','IN_PROGRESS')`
- `patient(doctolib_patient_id)` WHERE `doctolib_patient_id IS NOT NULL`
- `patient(identity_resolution_due_at)` WHERE `identity_status = 'TEMPORARY'`
- `queue_entry(daily_queue_id, visit_external_id)` UNIQUE WHERE `visit_external_id IS NOT NULL`

### 3.3. Indeksy GIN dla JSONB
- `patient_intake_form` -> `GIN (body_map_data jsonb_path_ops)`
- `medical_document_version` -> `GIN (medical_payload jsonb_path_ops)`
- `outbox_event` -> `GIN (payload jsonb_path_ops)`
- `audit_event` -> `GIN (metadata jsonb_path_ops)`

## 4. Zasady PostgreSQL (jeśli dotyczy)

### 4.1. Typy ENUM
- `staff_role_enum`: `RECEPTION`, `DOCTOR`, `ADMIN`
- `patient_identity_status_enum`: `CONFIRMED`, `TEMPORARY`
- `queue_shift_enum`: `FULL_DAY`, `MORNING`, `AFTERNOON`, `EVENING`
- `queue_source_enum`: `MANUAL`, `IMPORT`
- `queue_status_enum`: `OPEN`, `CLOSED`
- `queue_entry_status_enum`: `WAITING`, `IN_PROGRESS`, `PATIENT_COMPLETED`, `DOCTOR_IN_PROGRESS`, `PUBLISHED`, `CANCELLED`
- `intake_status_enum`: `IN_PROGRESS`, `SUBMITTED`
- `medical_doc_status_enum`: `DRAFT`, `PUBLISHED`
- `doc_version_status_enum`: `DRAFT`, `PUBLISHED`
- `pdf_status_enum`: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`
- `outbox_event_type_enum`: `GENERATE_PDF`, `HIDRIVE_UPLOAD`, `SMS_SEND`
- `outbox_status_enum`: `PENDING`, `PROCESSING`, `PROCESSED`, `FAILED`, `DEAD_LETTER`
- `import_type_enum`: `DAILY_FILE_IMPORT`
- `import_source_system_enum`: `DOCTOLIB_EXPORT`, `OTHER`
- `import_status_enum`: `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`

### 4.2. Zasady aplikacyjne zamiast triggerów (docelowo: 0 triggerów domenowych)
- `updated_at` aktualizowane w warstwie aplikacyjnej (`auto_now=True` w modelach Django lub centralny serwis repozytorium).
- Tymczasowa tożsamość pacjenta:
  - ręczne dodanie bez `Doctolib Patient ID` zapisuje `identity_status='TEMPORARY'`,
  - w tej samej transakcji tworzony jest alert administracyjny (kanał operacyjny) i ustawiane są `identity_alert_created_at` oraz `identity_resolution_due_at`,
  - po uzupełnieniu `Doctolib Patient ID` rekord przechodzi na `identity_status='CONFIRMED'`, a alert jest zamykany.
- Model sesji `latest-wins` (bez ograniczenia do jednej sesji historycznej):
  - nowe wygenerowanie tokenu zawsze tworzy nowy rekord `patient_form_session`,
  - w tej samej transakcji `queue_entry.active_session_id` jest przestawiane na nową sesję,
  - walidacja tokenu wymaga jednocześnie: `session.id == queue_entry.active_session_id`, `consumed_at IS NULL`, `expires_at > now()`,
  - starsze sesje pozostają w historii audytowej i są automatycznie odrzucane przez walidację (bez zależności od joba cleanup).
- Walidacja wymaganych zgód przed `SUBMITTED`:
  - wykonywana w serwisie domenowym `submit_patient_intake_form()` wewnątrz transakcji,
  - brak przejścia stanu, jeśli niezaakceptowano wszystkich aktywnych zgód wymaganych.
- Publikacja wersji dokumentu:
  - wykonywana w serwisie `publish_document_version()` (`SELECT ... FOR UPDATE` na `medical_document`),
  - ten sam commit transakcyjny aktualizuje `medical_document` i `medical_document_version`.
- Enqueue outbox po publikacji:
  - wpis `GENERATE_PDF` tworzony jawnie przez serwis publikacji w tej samej transakcji,
  - wpis `HIDRIVE_UPLOAD` tworzony przez worker po sukcesie generowania PDF,
  - wpis `SMS_SEND` tworzony przez worker po sukcesie uploadu.
- Ochrona retencji:
  - realizowana przez `CHECK (local_pdf_deleted_at IS NULL OR (hidrive_sent = true AND sms_sent = true))` w `medical_document_version`,
  - dodatkowo job retencji wykonuje walidację stanu i zapis audytu przed usunięciem pliku.

### 4.3. Zasady integralności i bezpieczeństwa
- Wszystkie FK w module dokumentów z `ON DELETE RESTRICT` dla danych medycznych (brak przypadkowego usunięcia historii).
- `token_hash` przechowywany wyłącznie jako hash SHA-256 (brak jawnego tokenu w DB).
- `Doctolib Patient ID` jest obowiązkowym kluczem tożsamości dla danych importowanych; rekordy ręczne bez tego ID są formalnie tymczasowe i wymagają pilnego domknięcia alertu administracyjnego.
- Włączenie rozszerzeń:
  - `CREATE EXTENSION IF NOT EXISTS pgcrypto;`
  - `CREATE EXTENSION IF NOT EXISTS citext;`
- Rekomendowany poziom izolacji dla publikacji + outbox: transakcja ACID (`READ COMMITTED` + blokady wierszy `FOR UPDATE SKIP LOCKED` przy workerze cron).

## 5. Wszelkie dodatkowe uwagi lub wyjaśnienia dotyczące decyzji projektowych

- Model jest znormalizowany do 3NF; celowa denormalizacja jest ograniczona do pól JSONB:
  - `body_map_data` (koordynaty znaczników),
  - `medical_payload` (sztywna struktura formularza medycznego w kodzie, ale elastyczne przechowanie),
  - `payload` outbox.
- JSONB jest wersjonowany (`*_schema_version`) i walidowany kontraktem aplikacyjnym; każda zmiana kontraktu wymaga migracji danych historycznych.
- Dane klinicznie/prawnie krytyczne (`diagnosis_code`, `procedure_code`) są składowane relacyjnie, a JSONB pełni rolę pomocniczą.
- Observability nie opiera się na tabelach OLTP jako źródle metryk czasu rzeczywistego:
  - metryki outbox/import/integracji emitowane przez OpenTelemetry do backendu metryk (np. Prometheus/Grafana),
  - alerting i progi utrzymywane jako konfiguracja-as-code,
  - tabela `audit_event` służy do śladu zdarzeń i dochodzeń powdrożeniowych, nie do bieżącego monitoringu SLA.
- Wersjonowanie dokumentu realizowane w `medical_document_version`, co spełnia wymaganie ponownej publikacji i nadpisania pliku w HiDrive, zachowując historię audytową po stronie DB.
- Retencja 30 dni: operacja usuwa lokalny plik PDF (i ustawia `local_pdf_deleted_at`), ale nie usuwa rekordu wersji; dzięki temu pozostaje pełny ślad operacyjny.
- Zamiast bezpośredniej integracji API z Doctolib, schema wspiera codzienny import plików eksportowanych z Doctolib (z audytem batchy i błędów wierszy), co upraszcza wdrożenie i utrzymanie.
- Ograniczenie `UNIQUE(daily_queue_id, patient_id)` zostało celowo usunięte, aby dopuścić więcej niż jedną wizytę tego samego pacjenta w tym samym dniu i gabinecie.
- Założono pełne odejście od modeli legacy; `staff_user` jest docelową tabelą użytkowników, a stary moduł wyników (`results_labresults`) nie jest częścią nowego schematu.
