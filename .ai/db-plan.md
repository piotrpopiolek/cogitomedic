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
  - `CHECK (role IN ('RECEPTION','DOCTOR','ADMIN','TABLET'))`
  - `CHECK (phone_number IS NULL OR phone_number ~ '^[0-9+() -]{7,20}$')`

### 1.2. Pozostałe tabele wymagane przez PRD

#### `staff_user_clinic_site`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `staff_user_id` `uuid` NOT NULL FK -> `staff_user(id)` ON DELETE CASCADE
- `clinic_site_id` `uuid` NOT NULL FK -> `clinic_site(id)` ON DELETE CASCADE
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (staff_user_id, clinic_site_id)`

#### `patient_clinic_site`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `patient_id` `uuid` NOT NULL FK -> `patient(id)` ON DELETE CASCADE
- `clinic_site_id` `uuid` NOT NULL FK -> `clinic_site(id)` ON DELETE CASCADE
- `last_visit_at` `timestamptz` NOT NULL DEFAULT `now()`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (patient_id, clinic_site_id)`

#### `patient`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `first_name` `varchar(100)` NOT NULL
- `last_name` `varchar(100)` NOT NULL
- `date_of_birth` `date` NOT NULL
- `phone` `varchar(20)` NOT NULL
- `email` `citext` NOT NULL
- `doctolib_patient_id` `varchar(64)` NULL UNIQUE
- `street` `varchar(150)` NULL
- `city` `varchar(100)` NULL
- `postal_code` `varchar(20)` NULL
- `country_code` `char(2)` NOT NULL DEFAULT `'DE'`
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (first_name, last_name, phone, date_of_birth)`
  - `CHECK (phone ~ '^[0-9+() -]{7,20}$')`
  - `CHECK (date_of_birth <= current_date)`

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
- `pdf_import_default_consulting_room_id` `uuid` NULL FK -> `consulting_room(id)` ON DELETE SET NULL
- `pdf_import_shift_code` `queue_shift_enum` NOT NULL DEFAULT `'FULL_DAY'`
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
- `assigned_doctor_id` `uuid` NULL FK -> `staff_user(id)` ON DELETE SET NULL
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
- `active_session_id` `uuid` NULL
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
  - `FK (active_session_id, id) -> patient_form_session(id, queue_entry_id) ON DELETE RESTRICT`

#### `tablet_device`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `android_id` `varchar(128)` NOT NULL UNIQUE
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `last_seen_at` `timestamptz` NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Uwaga: Pola `name` i `device_code` zostały usunięte (migracja). Identyfikacja urządzenia tylko przez `android_id`. Auto-dopisanie: przy pierwszym logowaniu tabletu z nieznanym `android_id` tworzony jest wpis.

#### `patient_form_session`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `queue_entry_id` `uuid` NOT NULL FK -> `queue_entry(id)` ON DELETE CASCADE
- `tablet_device_id` `uuid` NULL FK -> `tablet_device(id)` ON DELETE SET NULL
- `form_locale` `varchar(10)` NOT NULL DEFAULT `'de-DE'`
- `expires_at` `timestamptz` NOT NULL
- `consumed_at` `timestamptz` NULL
- `created_by_user_id` `uuid` NOT NULL FK -> `staff_user(id)` ON DELETE RESTRICT
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (id, queue_entry_id)`
  - `CHECK (form_locale ~ '^(de|en|pl)(-[A-Z]{2})?$')`
  - `CHECK (expires_at > created_at)`
  - `CHECK (consumed_at IS NULL OR consumed_at <= expires_at)`
- Uwaga: Pole `token_hash` zostało usunięte (migracja). Sesja bez tokenu; autoryzacja tabletu: rola TABLET + zakres kolejki/intake.

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

#### `anamnesis_question_definition`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `code` `varchar(80)` NOT NULL
- `version` `integer` NOT NULL DEFAULT `1`
- `question_text_de` `text` NOT NULL
- `question_text_en` `text` NOT NULL
- `answer_type` `varchar(30)` NOT NULL DEFAULT `'SINGLE_CHOICE'`
- `is_required` `boolean` NOT NULL DEFAULT `true`
- `display_order` `smallint` NOT NULL DEFAULT `0`
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `effective_from` `date` NOT NULL DEFAULT `current_date`
- `effective_to` `date` NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (code, version)`
  - `CHECK (answer_type IN ('SINGLE_CHOICE','MULTI_CHOICE','BOOLEAN','TEXT_OPTIONAL'))`
  - `CHECK (effective_to IS NULL OR effective_to >= effective_from)`

#### `anamnesis_option_definition`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `question_id` `uuid` NOT NULL FK -> `anamnesis_question_definition(id)` ON DELETE CASCADE
- `code` `varchar(80)` NOT NULL
- `option_text_de` `text` NOT NULL
- `option_text_en` `text` NOT NULL
- `display_order` `smallint` NOT NULL DEFAULT `0`
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (question_id, code)`

#### `patient_intake_form`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `queue_entry_id` `uuid` NOT NULL UNIQUE FK -> `queue_entry(id)` ON DELETE CASCADE
- `session_id` `uuid` NOT NULL UNIQUE
- `form_status` `intake_status_enum` NOT NULL DEFAULT `'IN_PROGRESS'`
- `body_map_schema_version` `smallint` NOT NULL DEFAULT `1`
- `body_map_data` `jsonb` NOT NULL DEFAULT `'[]'::jsonb`
- `anamnesis_schema_version` `smallint` NOT NULL DEFAULT `1`
- `anamnesis_payload` `jsonb` NOT NULL DEFAULT '{}'::jsonb
- `signature_file_path` `varchar(500)` NULL
- `signature_sha256` `char(64)` NULL
- `submitted_at` `timestamptz` NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (id, queue_entry_id)`
  - `FK (session_id, queue_entry_id) -> patient_form_session(id, queue_entry_id) ON DELETE RESTRICT`
  - `CHECK (jsonb_typeof(body_map_data) = 'array')`
  - `CHECK (jsonb_typeof(anamnesis_payload) = 'object')`
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
- `intake_form_id` `uuid` NOT NULL UNIQUE
- `status` `medical_doc_status_enum` NOT NULL DEFAULT `'DRAFT'`
- `current_version_no` `integer` NOT NULL DEFAULT `0`
- `last_published_at` `timestamptz` NULL
- `created_by_user_id` `uuid` NOT NULL FK -> `staff_user(id)` ON DELETE RESTRICT
- `updated_by_user_id` `uuid` NULL FK -> `staff_user(id)` ON DELETE SET NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `FK (intake_form_id, queue_entry_id) -> patient_intake_form(id, queue_entry_id) ON DELETE RESTRICT`
  - `CHECK (current_version_no >= 0)`

#### `medical_document_version`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `medical_document_id` `uuid` NOT NULL FK -> `medical_document(id)` ON DELETE CASCADE
- `version_no` `integer` NOT NULL
- `version_status` `doc_version_status_enum` NOT NULL DEFAULT `'DRAFT'`
- `publish_request_id` `uuid` NULL
- `publish_locale` `varchar(10)` NULL
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
  - `UNIQUE (medical_document_id, publish_request_id)`
  - `CHECK (version_no > 0)`
  - `CHECK (jsonb_typeof(medical_payload) = 'object')`
  - `CHECK ((version_status <> 'PUBLISHED') OR (publish_request_id IS NOT NULL))`
  - `CHECK (publish_locale IS NULL OR publish_locale ~ '^(de|en|pl)(-[A-Z]{2})?$')`
  - `CHECK ((version_status <> 'PUBLISHED') OR (publish_locale IS NOT NULL))`
  - `CHECK ((version_status <> 'PUBLISHED') OR (published_at IS NOT NULL))`
  - `CHECK ((pdf_generation_status <> 'COMPLETED') OR (pdf_local_path IS NOT NULL))`
  - `CHECK ((hidrive_sent = false) OR (pdf_generation_status = 'COMPLETED' AND pdf_local_path IS NOT NULL))`
  - `CHECK ((hidrive_sent = false) OR hidrive_sent_at IS NOT NULL)`
  - `CHECK ((sms_sent = false) OR sms_sent_at IS NOT NULL)`
  - `CHECK (local_pdf_deleted_at IS NULL OR (hidrive_sent = true AND sms_sent = true))`

#### `doctor_text_template`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `owner_user_id` `uuid` NULL FK -> `staff_user(id)` ON DELETE CASCADE
- `clinic_site_id` `uuid` NULL FK -> `clinic_site(id)` ON DELETE CASCADE
- `name` `varchar(120)` NOT NULL
- `template_locale` `varchar(10)` NOT NULL DEFAULT `'de-DE'`
- `template_body` `text` NOT NULL
- `is_active` `boolean` NOT NULL DEFAULT `true`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `CHECK (template_locale ~ '^(de|en|pl)(-[A-Z]{2})?$')`
  - `CHECK ((owner_user_id IS NOT NULL AND clinic_site_id IS NULL) OR (owner_user_id IS NULL AND clinic_site_id IS NOT NULL))`
  - `UNIQUE (owner_user_id, name, template_locale)`
  - `UNIQUE (clinic_site_id, name, template_locale)`

#### `translation_key`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `key` `varchar(255)` NOT NULL UNIQUE
- `category` `varchar(30)` NOT NULL
- `description` `text` NULL
- `is_html_allowed` `boolean` NOT NULL DEFAULT `false`
- `allowed_placeholders` `jsonb` NOT NULL DEFAULT `'[]'::jsonb`
- `status` `varchar(20)` NOT NULL DEFAULT `'ACTIVE'`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `CHECK (category IN ('doctor','reception','waiting_room','administration','other'))`
  - `CHECK (status IN ('ACTIVE','DEPRECATED'))`
  - `CHECK (jsonb_typeof(allowed_placeholders) = 'array')`

#### `translation_value`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `translation_key_id` `uuid` NOT NULL FK -> `translation_key(id)` ON DELETE CASCADE
- `language_code` `varchar(8)` NOT NULL
- `value` `text` NOT NULL
- `updated_by_user_id` `uuid` NULL FK -> `staff_user(id)` ON DELETE SET NULL
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (translation_key_id, language_code)`
  - `CHECK (language_code IN ('de','en','pl'))`

#### `translation_cache_version`
- `id` `uuid` PK DEFAULT `gen_random_uuid()`
- `category` `varchar(30)` NOT NULL
- `language_code` `varchar(8)` NOT NULL
- `version` `bigint` NOT NULL DEFAULT `1`
- `created_at` `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` `timestamptz` NOT NULL DEFAULT `now()`
- Ograniczenia:
  - `UNIQUE (category, language_code)`
  - `CHECK (category IN ('doctor','reception','waiting_room','administration','other'))`
  - `CHECK (language_code IN ('de','en','pl'))`
  - `CHECK (version > 0)`

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
  - `UNIQUE (medical_document_version_id, event_type)`
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
- Import PDF Doctolib jest uruchamiany asynchronicznie przez Django Tasks; plik z uploadu jest tymczasowo zapisywany w `MEDIA_ROOT/imports/patients_pdf/`, a w bazie pozostaje wyłącznie hash, nazwa pliku i wynik batcha.
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
- `context_clinic_site_id` `uuid` NULL FK -> `clinic_site(id)` ON DELETE SET NULL
- `metadata` `jsonb` NOT NULL DEFAULT '{}'::jsonb
- Ograniczenia:
  - `CHECK (jsonb_typeof(metadata) = 'object')`
- Uwaga: W `metadata` zarezerwowany klucz `_ref` (obiekt) przechowuje niezmienną kopię ID encji (`patient_id`, `medical_document_id`, `context_clinic_site_id`, `actor_user_id`, `outbox_event_id`) w celu compliance po anonimizacji/usunięciu (gdy FK ulegnie SET NULL).

## 2. Relacje między tabelami

- `staff_user` N:M `clinic_site` przez `staff_user_clinic_site` (przypisanie lekarza do klinik; zarządza tym ADMIN).
- `staff_user` 1:N `daily_queue` (przypisanie lekarza do zmiany/kolejki w gabinecie przez `assigned_doctor_id`).
- `staff_user` 1:N `daily_queue` (użytkownik tworzy wiele list dziennych).
- `clinic_site` 1:N `consulting_room` (lokalizacja ma wiele gabinetów).
- `consulting_room` 1:N `daily_queue` (gabinet ma wiele list dziennych w czasie).
- `daily_queue` 1:N `queue_entry` (lista dzienna zawiera wiele wpisów pacjentów).
- `patient` 1:N `queue_entry` (pacjent może mieć wiele wizyt/wpisów).
- `queue_entry` 1:N `patient_form_session` (historia sesji, model latest-wins bez tokenu).
- `queue_entry.active_session_id` wskazuje aktualnie obowiązującą sesję w modelu `latest-wins`.
- `queue_entry` 1:1 `patient_intake_form` (jeden formularz pacjenta na wpis kolejki).
- `patient_intake_form` N:M `consent_definition` przez `patient_intake_consent`.
- `anamnesis_question_definition` 1:N `anamnesis_option_definition` (słownik pytań i opcji DE/EN).
- `patient_intake_form` przechowuje `anamnesis_payload` (odpowiedzi pacjenta kodami pytań/opcji, niezależnie od języka UI).
- `queue_entry` 1:1 `medical_document` (jeden dokument medyczny dla jednego przebiegu wizyty).
- `medical_document` 1:N `medical_document_version` (wersjonowanie szkic/publikacja/republikacja).
- `medical_document_version.publish_locale` przechowuje niezmienny język publikacji PDF per wersja.
- `patient_intake_form` 1:1 `medical_document` (jeden dokument medyczny na jeden formularz intake).
- `medical_document_version` 1:N `outbox_event` (relacja egzekwowana FK `outbox_event.medical_document_version_id`; np. `HIDRIVE_UPLOAD`, potem `SMS_SEND`).
- `staff_user` 1:N `doctor_text_template` (szablony prywatne lekarza); szablony publiczne mają `owner_user_id=NULL` i ustawione `clinic_site_id`.
- `translation_key` 1:N `translation_value`.
- `translation_cache_version` przechowuje licznik wersji cache tłumaczeń dla pary `category+language_code`.
- `patient_import_batch` 1:N `patient_import_error`.
- `patient` 1:N `patient_contact_history`.
- Relacje ról:
  - `staff_user.role='TABLET'`: dostęp tylko do wyboru kolejki, listy wpisów kolejki, POST sessions (bez tokenu), formularza intake (GET/PUT/POST).
  - `staff_user.role='RECEPTION'` zarządza `daily_queue`, importami i sesjami formularza (POST sessions).
  - `staff_user.role='DOCTOR'` edytuje `medical_document` i publikuje `medical_document_version`.
  - `staff_user.role='DOCTOR'` może zarządzać własnymi `doctor_text_template`.
  - `staff_user.role='ADMIN'` zarządza słownikami (`consent_definition`) i użytkownikami.

## 3. Indeksy

### 3.1. Indeksy krytyczne (operacyjne)
- `patient(last_name, first_name, date_of_birth)`
- `patient(phone)`
- `patient(first_name, last_name, phone, date_of_birth)` UNIQUE
- `daily_queue(queue_date)`
- `daily_queue(queue_date, clinic_site_id, consulting_room_id, shift_code)` UNIQUE
- `queue_entry(daily_queue_id, entry_status, position_no)`
- `queue_entry(patient_id, created_at DESC)`
- `queue_entry(active_session_id)`
- `patient_form_session(queue_entry_id, consumed_at)`
- `patient_form_session(queue_entry_id, created_at DESC)`
- `patient_form_session(form_locale, created_at DESC)`
- `consent_definition(code, is_active, effective_from DESC)`
- `anamnesis_question_definition(code, is_active, effective_from DESC)`
- `anamnesis_option_definition(question_id, is_active, display_order)`
- `patient_intake_form(form_status, submitted_at)`
- `patient_intake_consent(intake_form_id, accepted)`
- `medical_document(status, updated_at DESC)`
- `medical_document_version(medical_document_id, version_no DESC)` UNIQUE
- `medical_document_version(version_status, published_at DESC)`
- `medical_document_version(hidrive_sent, sms_sent, published_at)` (retencja + monitoring)
- `patient_clinic_site(patient_id, clinic_site_id)`
- `doctor_text_template(owner_user_id, template_locale, is_active)`
- `doctor_text_template(clinic_site_id, template_locale, is_active)`
- `translation_key(category, status, key)`
- `translation_value(language_code, translation_key_id)`
- `translation_cache_version(category, language_code)` UNIQUE
- `outbox_event(status, available_at)`
- `outbox_event(event_type, status, retry_count, available_at, payload_schema_version)`
- `outbox_event(medical_document_version_id, created_at DESC)`
- `audit_event(event_time DESC)`
- `audit_event(patient_id, event_time DESC)`
- `audit_event(medical_document_id, event_time DESC)`
- `audit_event(context_clinic_site_id, event_time DESC)`
- `audit_event(outbox_event_id, event_time DESC)`
- `audit_event` -> `GIN (metadata jsonb_path_ops)` (w szczególności po `metadata->>'assigned_doctor_id'`)

### 3.2. Indeksy częściowe (PostgreSQL partial indexes)
- `outbox_event(status, available_at)` WHERE `status IN ('PENDING','FAILED')`
- `medical_document_version(published_at)` WHERE `version_status='PUBLISHED' AND hidrive_sent=true AND sms_sent=true AND local_pdf_deleted_at IS NULL`
- `patient_form_session(expires_at)` WHERE `consumed_at IS NULL`
- `queue_entry(daily_queue_id, position_no)` WHERE `entry_status IN ('WAITING','IN_PROGRESS')`
- `patient(doctolib_patient_id)` WHERE `doctolib_patient_id IS NOT NULL`
- `queue_entry(daily_queue_id, visit_external_id)` UNIQUE WHERE `visit_external_id IS NOT NULL`

### 3.3. Indeksy GIN dla JSONB
- `patient_intake_form` -> `GIN (body_map_data jsonb_path_ops)`
- `patient_intake_form` -> `GIN (anamnesis_payload jsonb_path_ops)`
- `medical_document_version` -> `GIN (medical_payload jsonb_path_ops)`
- `outbox_event` -> `GIN (payload jsonb_path_ops)`
- `audit_event` -> `GIN (metadata jsonb_path_ops)`

## 4. Zasady PostgreSQL (jeśli dotyczy)

### 4.1. Typy ENUM
- `staff_role_enum`: `RECEPTION`, `DOCTOR`, `ADMIN`, `TABLET`
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
- `import_type_enum`: `DAILY_FILE_IMPORT`, `EMERGENCY_TEMPLATE_IMPORT`
- `import_source_system_enum`: `DOCTOLIB_EXPORT`, `OTHER`
- `import_status_enum`: `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`

### 4.2. Zasady aplikacyjne zamiast triggerów (docelowo: 0 triggerów domenowych)
- `updated_at` aktualizowane w warstwie aplikacyjnej (`auto_now=True` w modelach Django lub centralny serwis repozytorium).
- Tożsamość pacjenta:
  - rekord pacjenta jest unikalny po `first_name`, `last_name`, `phone`, `date_of_birth`,
  - `doctolib_patient_id` jest opcjonalny, ale jeśli występuje, musi być unikalny,
  - ręczne dodanie bez `Doctolib Patient ID` nie tworzy osobnego statusu ani alertu administracyjnego.
- Model sesji `latest-wins` (bez tokenu):
  - utworzenie sesji (POST queue-entries/{id}/sessions) zawsze tworzy nowy rekord `patient_form_session` (bez pola token),
  - w tej samej transakcji `queue_entry.active_session_id` jest przestawiane na nową sesję,
  - autoryzacja tabletu: rola TABLET oraz intake_form w dozwolonym zakresie (np. kolejka); brak walidacji tokenu,
  - starsze sesje pozostają w historii audytowej; aktualna sesja wskazywana przez `queue_entry.active_session_id`.
- Walidacja wymaganych zgód przed `SUBMITTED`:
  - wykonywana w serwisie domenowym `submit_patient_intake_form()` wewnątrz transakcji,
  - brak przejścia stanu, jeśli niezaakceptowano wszystkich aktywnych zgód wymaganych.
- Walidacja wymaganych pytań anamnestycznych przed `SUBMITTED`:
  - wykonywana w tym samym serwisie `submit_patient_intake_form()` wewnątrz tej samej transakcji,
  - brak przejścia stanu, jeśli brak odpowiedzi dla pytań `is_required=true` aktywnych dla danej wersji ankiety.
- Publikacja wersji dokumentu:
  - wykonywana w serwisie `publish_document_version()` (`SELECT ... FOR UPDATE` na `medical_document`),
  - ten sam commit transakcyjny aktualizuje `medical_document` i `medical_document_version`,
  - `publish_locale` jest wymagane przy publikacji i zapisywane niemutowalnie na wersji,
  - `publish_request_id` (idempotency key) gwarantuje, że wielokrotne kliknięcie "Zatwierdź i wyślij" nie tworzy wielu wersji i wielu łańcuchów outbox.
- Tłumaczenia runtime:
  - źródłem prawdy są wyłącznie tabele `translation_key`/`translation_value`,
  - invalidacja cache między instancjami oparta o `translation_cache_version` (klucze wersjonowane, Postgres-only).
- Enqueue outbox po publikacji:
  - wpis `GENERATE_PDF` tworzony jawnie przez serwis publikacji w tej samej transakcji,
  - wpis `HIDRIVE_UPLOAD` tworzony przez zadanie Django Tasks po sukcesie generowania PDF,
  - wpis `SMS_SEND` tworzony przez zadanie Django Tasks po sukcesie uploadu.
- Ochrona retencji:
  - realizowana przez `CHECK (local_pdf_deleted_at IS NULL OR (hidrive_sent = true AND sms_sent = true))` w `medical_document_version`,
  - dodatkowo zadanie retencji (Django Tasks) wykonuje walidację stanu i zapis audytu przed usunięciem pliku.

### 4.3. Zasady integralności i bezpieczeństwa
- `ON DELETE RESTRICT` dla bytów medycznych wysokiego poziomu (`queue_entry`, `patient_intake_form`, `medical_document`) w celu ochrony historii klinicznej.
- `ON DELETE CASCADE` dopuszczalne dla bytów technicznych ściśle podrzędnych (`medical_document_version`, `outbox_event`), które nie mają samodzielnego znaczenia biznesowego bez rekordu nadrzędnego.
- Token jednorazowy został wycofany: w `patient_form_session` nie ma pola `token_hash`; sesja identyfikowana po id, autoryzacja tabletu po roli TABLET i zakresie kolejki.
- `Doctolib Patient ID` pozostaje opcjonalnym identyfikatorem pomocniczym; główna reguła unikalności pacjenta opiera się na `first_name + last_name + phone + date_of_birth`.
- Włączenie rozszerzeń:
  - `CREATE EXTENSION IF NOT EXISTS pgcrypto;`
  - `CREATE EXTENSION IF NOT EXISTS citext;`
- Rekomendowany poziom izolacji dla publikacji + outbox: transakcja ACID (`READ COMMITTED` + blokady wierszy `FOR UPDATE SKIP LOCKED` w przetwarzaniu zadań Django Tasks).

## 5. Wszelkie dodatkowe uwagi lub wyjaśnienia dotyczące decyzji projektowych

- Model jest znormalizowany do 3NF; celowa denormalizacja jest ograniczona do pól JSONB:
  - `body_map_data` (koordynaty znaczników),
  - `anamnesis_payload` (odpowiedzi pacjenta mapowane przez stabilne kody pytań/opcji, niezależne od lokalizacji DE/EN),
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
- **Portal wyniki (US-018, PRD 3.4a):** Proces udostępniania 4-etapowy: SMS logistyczny („Nowa dokumentacja w Cogito"), logowanie pacjenta phone+DOB, OTP 6-cyfrowy 15 min, serwowanie PDF przez HTTPS. Implementacja wymagać może nowej tabeli sesji OTP (np. `patient_results_otp_session`) do przechowania kodu i ważności; audyt pobrań w `audit_event`.
- Runtime backendu: Django 6 + natywne `django.tasks`; w projekcie obowiązuje jedno rozwiązanie asynchroniczne (Django Tasks + Outbox), a tabela `outbox_event` nadal jest źródłem prawdy o statusach procesu.
- **Języki portalu:** interfejs jest dostępny w języku niemieckim, angielskim i polskim. Pole `staff_user.preferred_locale` (np. `de-DE`, `en-GB`, `pl-PL`) określa preferowany język panelu personelu; dla tabletu pacjenta język wybierany jest w kontekście sesji/formularza.

### 5.1. Kontrakt `anamnesis_payload` v1 (Anamnesebogen Q1–Q11)

#### Kody pytań (językowo neutralne)
- `Q1_MALIGNANT_MELANOMA_HISTORY` (NO/YES)
- `Q2_WHITE_SKIN_CANCER_HISTORY` (NO/YES)
- `Q3_FAMILY_MELANOMA_FIRST_DEGREE` (NO/YES/UNKNOWN)
- `Q4_NEW_SKIN_CHANGES_PRESENT` (NO/YES)
- `Q4B_NEW_SKIN_CHANGES_LOCATION` (MULTI: `LOWER_BACK`, `THORACIC_SPINE`, `ABDOMEN`, `OTHER_LOCATION`)
- `Q5_EXISTING_CHANGES_EVOLUTION` (NO/YES)
- `Q6_SEVERE_SUNBURNS_CHILDHOOD` (NO/YES)
- `Q7_OCCUPATIONAL_SUN_EXPOSURE` (NO/YES)
- `Q8_PRIVATE_SUN_EXPOSURE` (NO/YES)
- `Q9_SOLARIUM_USAGE` (NO/YES)
- `Q10_IMMUNOSUPPRESSIVE_MEDICATION` (NO/YES)
- `Q11_HYDROCHLOROTHIAZIDE_USAGE` (NO/YES/UNKNOWN)

#### Struktura JSON (v1)
- `schema_version` — wersja kontraktu payloadu.
- `answered_at` — znacznik czasu ISO8601.
- `answers[]` — lista odpowiedzi mapowanych kodami pytań/opcji.
- `body_map_points[]` — opcjonalne punkty dla lokalizacji zmian (Q4/Q4B), kompatybilne z `body_map_data`.
- `free_text` — opcjonalne doprecyzowanie dla `OTHER_LOCATION`.

Przykład:

```json
{
  "schema_version": 1,
  "answered_at": "2026-02-16T10:02:33Z",
  "answers": [
    {"question_code": "Q1_MALIGNANT_MELANOMA_HISTORY", "selected_option_codes": ["NO"]},
    {"question_code": "Q2_WHITE_SKIN_CANCER_HISTORY", "selected_option_codes": ["YES"]},
    {"question_code": "Q3_FAMILY_MELANOMA_FIRST_DEGREE", "selected_option_codes": ["UNKNOWN"]},
    {"question_code": "Q4_NEW_SKIN_CHANGES_PRESENT", "selected_option_codes": ["YES"]},
    {
      "question_code": "Q4B_NEW_SKIN_CHANGES_LOCATION",
      "selected_option_codes": ["LOWER_BACK", "OTHER_LOCATION"],
      "free_text": "right shoulder blade",
      "body_map_points": [
        {"x": 0.45, "y": 0.34, "side": "back", "label": "new_lesion"}
      ]
    },
    {"question_code": "Q5_EXISTING_CHANGES_EVOLUTION", "selected_option_codes": ["NO"]},
    {"question_code": "Q6_SEVERE_SUNBURNS_CHILDHOOD", "selected_option_codes": ["YES"]},
    {"question_code": "Q7_OCCUPATIONAL_SUN_EXPOSURE", "selected_option_codes": ["NO"]},
    {"question_code": "Q8_PRIVATE_SUN_EXPOSURE", "selected_option_codes": ["YES"]},
    {"question_code": "Q9_SOLARIUM_USAGE", "selected_option_codes": ["NO"]},
    {"question_code": "Q10_IMMUNOSUPPRESSIVE_MEDICATION", "selected_option_codes": ["NO"]},
    {"question_code": "Q11_HYDROCHLOROTHIAZIDE_USAGE", "selected_option_codes": ["UNKNOWN"]}
  ]
}
```

#### Reguły walidacyjne v1
- Dla pytań `NO/YES`: dokładnie jedna opcja.
- Dla pytań `NO/YES/UNKNOWN`: dokładnie jedna opcja.
- Dla `Q4B_NEW_SKIN_CHANGES_LOCATION`:
  - dozwolone wielokrotne opcje,
  - jeśli wybrano `OTHER_LOCATION`, `free_text` powinno być niepuste,
  - `body_map_points` jest opcjonalne, ale rekomendowane przy `Q4_NEW_SKIN_CHANGES_PRESENT=YES`.
- Wartości DE/EN nie są zapisywane w payloadzie; zapisujemy wyłącznie kody.

### 5.2. Kontrakt `medical_payload` v1 (Befund lekarza)

**Kontekst (Wideodermatoskop):** Numery zmian i zdjęcia pochodzą z Wideodermatoskopu. Lekarz wpisuje numery z urządzenia i grupuje je: jedna **grupa** = jedna lista `lesion_numbers` + jeden wspólny opis (cechy, ocena, ryzyko, tekst). Schemat ciała nie jest używany w formularzu Befund (służył pacjentowi do zaznaczania obszarów).

#### Struktura logiczna
- `schema_version` (medical_payload_schema_version: 1)
- `authoring_locale` (`de-DE`/`en-*`)
- `examination_scope[]` (np. `INTIMATE_AREA_NOT_EXAMINED`, `ORAL_MUCOSA_NOT_EXAMINED`)
- `fitzpatrick_type` (np. `TYPE_I`, `TYPE_II`, ..., `TYPE_VI`, `TYPE_II_III`, `UNDETERMINED`)
- `overall_image_assessment` (`NO_CONTROL_NEEDED` | `CONTROL_NEEDED`)
- `lesions[]` (lista **grup** zmian – każda grupa ma wiele numerów z Wideodermatoskopu i jeden opis)
- `recommendations[]`
- `final_assessment`
- `summary_generated_text`, `summary_edited_text`
- `template_context` (np. `template_id`, `template_name`, `template_locale`)

#### Struktura `lesions[]`
Każdy element (jedna grupa opisu):
- `lesion_numbers` (array of int) — numery zmian z Wideodermatoskopu w tej grupie; **wymagane**, niepuste, bez duplikatów w tablicy
- `dermatoscopic_features[]` (np. `ASYMMETRY`, `IRREGULAR_BORDER`, `MULTICOLOR`) — opcjonalne
- `clinical_assessment` (`UNREMARKABLE`, `SLIGHTLY_ATYPICAL`, `CONTROL_NEEDED`, `SUSPICIOUS`) — **wymagane**
- `malignancy_risk` (`NO_SUSPICION`, `LOW_SUSPICION`, `CANNOT_EXCLUDE`) — **wymagane**
- `generated_text` — opcjonalne
- `edited_text` — opcjonalne

#### Pełna tabela kodów enum (Befund v1)

`examination_scope[]`
- `INTIMATE_AREA_NOT_EXAMINED` — DE: "Intimbereich nicht untersucht", EN: "Intimate area not examined"
- `ORAL_MUCOSA_NOT_EXAMINED` — DE: "Mundschleimhaut nicht untersucht", EN: "Oral mucosa not examined"

`fitzpatrick_type`
- `TYPE_I` — DE: "Hauttyp I nach Fitzpatrick", EN: "Fitzpatrick skin type I"
- `TYPE_II` — DE: "Hauttyp II nach Fitzpatrick", EN: "Fitzpatrick skin type II"
- `TYPE_III` — DE: "Hauttyp III nach Fitzpatrick", EN: "Fitzpatrick skin type III"
- `TYPE_IV` — DE: "Hauttyp IV nach Fitzpatrick", EN: "Fitzpatrick skin type IV"
- `TYPE_V` — DE: "Hauttyp V nach Fitzpatrick", EN: "Fitzpatrick skin type V"
- `TYPE_VI` — DE: "Hauttyp VI nach Fitzpatrick", EN: "Fitzpatrick skin type VI"
- `TYPE_II_III` — DE: "Hauttyp II–III nach Fitzpatrick", EN: "Fitzpatrick skin type II–III"
- `UNDETERMINED` — DE: "Hauttyp nicht eindeutig bestimmbar", EN: "Skin type cannot be determined clearly"

`overall_image_assessment`
- `NO_CONTROL_NEEDED` — DE: "Keine kontrollbedürftigen Hautveränderungen erkennbar", EN: "No skin changes requiring follow-up identified"
- `CONTROL_NEEDED` — DE: "Kontrollbedürftige Hautveränderungen erkennbar", EN: "Skin changes requiring follow-up identified"

`lesions[].dermatoscopic_features[]`
- `ASYMMETRY` — DE: "Asymmetrie", EN: "Asymmetry"
- `IRREGULAR_BORDER` — DE: "Unregelmäßige Begrenzung", EN: "Irregular border"
- `INHOMOGENEOUS_PIGMENTATION` — DE: "Inhomogene Pigmentierung", EN: "Inhomogeneous pigmentation"
- `MULTICOLOR` — DE: "Mehrfarbigkeit", EN: "Multicolor pattern"
- `ATYPICAL_PIGMENT_NETWORK` — DE: "Atypisches Pigmentnetz", EN: "Atypical pigment network"
- `IRREGULAR_GLOBULES` — DE: "Unregelmäßige Globuli", EN: "Irregular globules"
- `IRREGULAR_DOTS` — DE: "Unregelmäßige Punkte", EN: "Irregular dots"
- `STRUCTURELESS_AREAS` — DE: "Strukturlose Areale", EN: "Structureless areas"
- `ATYPICAL_VASCULAR_STRUCTURES` — DE: "Atypische Gefäßstrukturen", EN: "Atypical vascular structures"
- `REGRESSION_AREAS` — DE: "Regressionsareale (weißlich/narbig)", EN: "Regression areas (whitish/scar-like)"

`lesions[].clinical_assessment`
- `UNREMARKABLE` — DE: "Unauffällige Läsion", EN: "Unremarkable lesion"
- `SLIGHTLY_ATYPICAL` — DE: "Leicht atypische Läsion", EN: "Slightly atypical lesion"
- `CONTROL_NEEDED` — DE: "Kontrollbedürftige Läsion", EN: "Lesion requiring follow-up"
- `SUSPICIOUS` — DE: "Suspekte Läsion", EN: "Suspicious lesion"

`lesions[].malignancy_risk`
- `NO_SUSPICION` — DE: "Kein Malignitätsverdacht", EN: "No suspicion of malignancy"
- `LOW_SUSPICION` — DE: "Niedriger Malignitätsverdacht", EN: "Low suspicion of malignancy"
- `CANNOT_EXCLUDE` — DE: "Malignitätsverdacht kann nicht ausgeschlossen werden", EN: "Malignancy cannot be ruled out"

`recommendations[]`
- `FOLLOWUP_3_MONTHS` — DE: "Dermatologische Verlaufskontrolle in 3 Monaten empfohlen", EN: "Dermatological follow-up in 3 months recommended"
- `FOLLOWUP_6_MONTHS` — DE: "Dermatologische Verlaufskontrolle in 6 Monaten empfohlen", EN: "Dermatological follow-up in 6 months recommended"
- `PROMPT_VISIT_ON_CHANGE` — DE: "Bei klinischer Veränderung zeitnahe persönliche dermatologische Vorstellung empfohlen", EN: "Prompt in-person dermatology visit recommended if clinical change occurs"
- `NO_SHORT_TERM_FOLLOWUP_REQUIRED` — DE: "Aktuell keine kurzfristige Kontrolle erforderlich", EN: "No short-term follow-up currently required"

`final_assessment`
- `NO_HIGH_GRADE_SUSPICION` — DE: "Aktuell kein höhergradiger Malignitätsverdacht", EN: "Currently no high-grade suspicion of malignancy"
- `HIGH_GRADE_CANNOT_BE_EXCLUDED` — DE: "Ein höhergradiger Malignitätsverdacht kann nicht sicher ausgeschlossen werden", EN: "High-grade malignancy suspicion cannot be reliably excluded"

Przykład:

```json
{
  "schema_version": 1,
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
}
```

#### Reguły walidacyjne v1
- `lesions[]` może być puste tylko gdy `overall_image_assessment=NO_CONTROL_NEEDED`.
- Dla każdego elementu `lesions[]` wymagane są: `lesion_numbers` (niepuste, `length >= 1`), `clinical_assessment`, `malignancy_risk`.
- **`lesion_numbers`:** nie może być puste; w jednej tablicy brak duplikatów (po usunięciu duplikatów długość musi być taka sama; np. `[2, 3, 2]` → błąd).
- **`clinical_assessment`:** dozwolone wartości: `UNREMARKABLE`, `SLIGHTLY_ATYPICAL`, `CONTROL_NEEDED`, `SUSPICIOUS`.
- **`malignancy_risk`:** dozwolone wartości: `NO_SUSPICION`, `LOW_SUSPICION`, `CANNOT_EXCLUDE`.
- Opcjonalnie (do decyzji produktu): każdy numer z Wideodermatoskopu tylko w jednej grupie w obrębie całego `lesions` (unikalność globalna).
- `summary_edited_text` jest opcjonalne, ale jeśli puste, do PDF trafia `summary_generated_text`.
- Do PDF trafia zawsze tekst końcowy per grupa (`edited_text` jeśli istnieje, inaczej `generated_text`).
