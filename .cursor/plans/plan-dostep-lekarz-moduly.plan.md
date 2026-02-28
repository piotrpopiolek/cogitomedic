---
name: ""
overview: ""
todos: []
isProject: false
---

# Plan dostępu lekarza (rola DOCTOR) do modułów

Document opracowany na podstawie: `.ai/prd.md`, `.ai/db-plan.md`, `.ai/api-plan.md`, `README.md`.

---

## 1. Cel

Określenie, do jakich modułów (zasobów, endpointów API i powiązanych encji w DB) powinien mieć dostęp użytkownik z rolą **DOCTOR**, aby realizować flow opisany w PRD (US-008, US-009, US-010, US-019) oraz obserwowalność z US-014.

---

## 2. Podsumowanie RBAC (z api-plan i db-plan)


| Rola      | Zakres dostępu (skrót)                                                                                                                |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| TABLET    | Kolejki (wybór), wpisy kolejki, sesje, formularz intake (GET/PATCH/PUT/POST submit). Bez CRUD kolejek, bez zarządzania użytkownikami. |
| RECEPTION | Kolejki, wpisy, pacjenci (CRUD), sesje, import (odczyt/zapis).                                                                        |
| DOCTOR    | Dokument medyczny (odczyt/zapis), publikacja/republikacja, wersje; podgląd danych w kontekście dokumentu.                             |
| ADMIN     | Użytkownicy, słowniki (zgody, anamneza), scalanie pacjentów, outbox/operacje, pełny audit.                                            |


---

## 3. Moduły – dostęp lekarza (DOCTOR)

### 3.1. Auth (wspólne dla wszystkich ról)


| Moduł / Zasób       | Dostęp DOCTOR | Uwagi                                                                         |
| ------------------- | ------------- | ----------------------------------------------------------------------------- |
| POST `/auth/login`  | Tak           | Logowanie (US-001).                                                           |
| POST `/auth/logout` | Tak           | Wylogowanie.                                                                  |
| GET `/auth/me`      | Tak           | Bieżący użytkownik, rola, uprawnienia (np. `queue.read`, `document.publish`). |


---

### 3.2. Kolejki i wpisy (tylko odczyt)

Lekarz musi móc wybrać datę/gabinet i zobaczyć listę pacjentów (wpisów) do przeglądu oraz otworzyć/utworzyć dokument medyczny dla wybranego wpisu. Nie zarządza kolejkami ani sesjami.


| Moduł / Zasób                                            | Dostęp DOCTOR | Uwagi                                                                                                        |
| -------------------------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------ |
| GET `/daily-queues`                                      | Tak (read)    | Lista kolejek (np. po dacie, lokacji, gabinecie) – wybór kontekstu pracy.                                    |
| GET `/daily-queues/{id}/entries`                         | Tak (read)    | Lista wpisów kolejki (np. filtrowanie po `entry_status=PATIENT_COMPLETED`) – lista pacjentów do opracowania. |
| GET `/queue-entries/{id}`                                | Tak (read)    | Szczegóły wpisu (pacjent, status, notatki) w razie potrzeby.                                                 |
| POST/PATCH/DELETE daily-queues, POST/PATCH queue-entries | Nie           | Zarządzanie kolejką i wpisami należy do RECEPTION.                                                           |


---

### 3.3. Pacjenci (tylko odczyt w kontekście pracy lekarza)

Dane pacjenta lekarz widzi głównie w kontekście dokumentu (intake summary w GET `/medical-documents/{id}`). Opcjonalnie: wyszukiwanie pacjenta po nazwisku/dacie urodzenia, jeśli UI ma osobną „wyszukaj pacjenta”.


| Moduł / Zasób                                       | Dostęp DOCTOR      | Uwagi                                                                                                                |
| --------------------------------------------------- | ------------------ | -------------------------------------------------------------------------------------------------------------------- |
| GET `/patients`                                     | Opcjonalnie (read) | Wyszukiwanie pacjentów (np. `search`, `last_name`, `date_of_birth`) – jeśli panel ma osobny ekran „znajdź pacjenta”. |
| GET `/patients/{id}`                                | Opcjonalnie (read) | Szczegóły pacjenta poza kontekstem dokumentu (np. do weryfikacji).                                                   |
| POST/PATCH `/patients`, POST `/patients/{id}/merge` | Nie                | Tworzenie/edycja pacjentów i scalanie – RECEPTION/ADMIN.                                                             |
| GET `/patients/{id}/contact-history`                | Opcjonalnie (read) | Historia kontaktów – tylko jeśli wymagane w flow lekarza.                                                            |


Rekomendacja: na start wystarczy dostęp do pacjenta wyłącznie przez `intake_summary` i dane w `medical-documents`; ewentualne GET `/patients` (read) dodać, gdy pojawi się wyraźna potrzeba wyszukiwania po stronie lekarza.

---

### 3.4. Lokacje i gabinety (tylko odczyt)

Potrzebne do filtrów w widoku „kolejka / lista dokumentów” (wybór lokacji, gabinetu).


| Moduł / Zasób                                    | Dostęp DOCTOR | Uwagi                                     |
| ------------------------------------------------ | ------------- | ----------------------------------------- |
| GET `/clinic-sites`                              | Tak (read)    | Lista placówek.                           |
| GET `/consulting-rooms`                          | Tak (read)    | Lista gabinetów (np. z `clinic_site_id`). |
| POST/PATCH/DELETE clinic-sites, consulting-rooms | Nie           | ADMIN.                                    |


---

### 3.5. Dokumenty medyczne i wersje (główny moduł lekarza)

Pełny flow lekarza (US-008, US-009, US-010): lista dokumentów do opracowania, podgląd intake + szkic, zapis szkicu, generowanie tekstu, publikacja, edycja opublikowanego i ponowna wysyłka.


| Moduł / Zasób                                | Dostęp DOCTOR | Uwagi                                                                                                                                                        |
| -------------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| GET `/medical-documents`                     | Tak           | Lista „work queue” (parametry: `status`, `queue_date`, `doctor_view` = `pending_review` / `published` / `failed`, `patient_search`). Zgodne z api-plan 2.10. |
| GET `/medical-documents/{id}`                | Tak           | Pełny kontekst: intake summary (zgody, anamneza, body map, pacjent), aktualna wersja (draft/published), statusy PDF/HiDrive/SMS.                             |
| POST `/medical-documents`                    | Tak           | Utworzenie dokumentu dla `queue_entry_id` (idempotentnie, gdy intake SUBMITTED).                                                                             |
| PATCH `/medical-documents/{id}/draft`        | Tak           | Zapis szkicu (medical_payload, diagnosis_code, procedure_code) – US-008, US-009.                                                                             |
| POST `/medical-documents/{id}/generate-text` | Tak           | Generowanie tekstów Befund z wybranych opcji (bez publikacji).                                                                                               |
| POST `/medical-documents/{id}/publish`       | Tak           | Publikacja z `publish_request_id`, `publish_locale`, opcjonalnie `resend_sms` – US-009, US-010.                                                              |
| GET `/medical-documents/{id}/versions`       | Tak           | Historia wersji dokumentu.                                                                                                                                   |
| GET `/medical-document-versions/{id}`        | Tak           | Szczegóły wersji (status generowania PDF, HiDrive, SMS).                                                                                                     |


Lekarz **nie** wywołuje bezpośrednio endpointów intake (PATCH/PUT/POST na `/intake-forms/...`) – dane intake są tylko do odczytu w `intake_summary` w ramach dokumentu medycznego.

---

### 3.6. Szablony tekstu lekarza (US-019)

Lekarz zarządza własnymi szablonami i korzysta z szablonów globalnych (klinika).


| Moduł / Zasób                        | Dostęp DOCTOR   | Uwagi                                                                                 |
| ------------------------------------ | --------------- | ------------------------------------------------------------------------------------- |
| GET `/doctor-text-templates`         | Tak             | Lista szablonów (global + prywatne), filtry: `template_locale`, `scope`, `is_active`. |
| POST `/doctor-text-templates`        | Tak             | Tworzenie własnego szablonu (np. `is_global: false`).                                 |
| GET `/doctor-text-templates/{id}`    | Tak             | Odczyt szablonu (własny lub globalny).                                                |
| PATCH `/doctor-text-templates/{id}`  | Tak             | Tylko dla szablonów własnych (`owner_user_id = current_user`).                        |
| DELETE `/doctor-text-templates/{id}` | Tak             | Tylko dla szablonów własnych (lub soft-deactivate).                                   |
| Szablony globalne (`is_global=true`) | Odczyt / użycie | Edycja/usuwanie szablonów globalnych – ADMIN.                                         |


---

### 3.7. Observability / dashboard lekarza (US-014)

PRD i api-plan: „prosty dashboard recepcji/lekarza” – status dokumentów i błędów wymagających interwencji. Lekarz nie zarządza outboxem ani metrykami technicznymi.


| Moduł / Zasób                                                             | Dostęp DOCTOR      | Uwagi                                                                                                                                                    |
| ------------------------------------------------------------------------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Status dokumentów (pdf_generation_status, hidrive_sent, sms_sent, FAILED) | Tak                | Już w GET `/medical-documents` i GET `/medical-documents/{id}` oraz w `doctor_view=failed`. Wystarczy do „czerwonej lampki” i listy dokumentów z błędem. |
| GET `/outbox-events`                                                      | Nie                | Pełna kolejka outbox – ADMIN/Ops (api-plan 2.12).                                                                                                        |
| POST `/outbox-events/{id}/retry`                                          | Nie                | ADMIN/Ops.                                                                                                                                               |
| POST `/operations/outbox/process`                                         | Nie                | ADMIN/Ops.                                                                                                                                               |
| GET `/observability/health`                                               | Opcjonalnie (read) | Tylko jeśli UI lekarza ma pokazywać „system niedostępny”; zwykle wystarczy obsługa błędów 5xx.                                                           |
| GET `/observability/metrics`                                              | Nie                | Prometheus/OTEL – środowisko operacyjne, nie panel lekarza.                                                                                              |


---

### 3.8. Moduły bez dostępu dla DOCTOR


| Moduł / Zasób                                                                        | Dostęp DOCTOR                | Uwagi                                                                                                           |
| ------------------------------------------------------------------------------------ | ---------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Staff users (GET/POST/PATCH/DELETE `/staff-users`)                                   | Nie                          | ADMIN.                                                                                                          |
| Consent definitions (CRUD `/consent-definitions`)                                    | Nie                          | Słownik zgód – ADMIN.                                                                                           |
| Anamnesis definitions (CRUD `/anamnesis-definitions`)                                | Nie                          | Słownik anamnezy – ADMIN.                                                                                       |
| Intake forms – zapis (PATCH body_map, PUT consents/anamnesis, POST signature/submit) | Nie                          | Tablet/recepcja; lekarz tylko odczyt w kontekście dokumentu.                                                    |
| Patient sessions (POST `/queue-entries/{id}/sessions`)                               | Nie                          | TABLET/RECEPTION/ADMIN.                                                                                         |
| Tablet devices (CRUD `/tablet-devices`)                                              | Nie                          | RECEPTION/ADMIN.                                                                                                |
| Imports (POST `/imports/patients`, GET batches, emergency template)                  | Nie                          | RECEPTION/ADMIN.                                                                                                |
| Operations: retention (POST `/operations/retention/run`)                             | Nie                          | ADMIN.                                                                                                          |
| Audit (GET `/audit-events`)                                                          | Nie (lub bardzo ograniczony) | Pełna lista – ADMIN; ewentualnie w przyszłości: tylko zdarzenia powiązane z dokumentami dostępnymi dla lekarza. |
| Merge patients (POST `/patients/{id}/merge`)                                         | Nie                          | ADMIN.                                                                                                          |


---

## 4. Encje w bazie (db-plan) – pod kątem roli DOCTOR

- **Odczyt (bezpośrednio lub przez API):**  
`staff_user` (własny), `patient` (w kontekście queue_entry/document), `daily_queue`, `queue_entry`, `clinic_site`, `consulting_room`, `patient_intake_form` (tylko odczyt w kontekście dokumentu), `patient_intake_consent`, `medical_document`, `medical_document_version`, `doctor_text_template` (własne + globalne).
- **Zapis (przez serwisy aplikacyjne):**  
`medical_document`, `medical_document_version` (draft, publish), `doctor_text_template` (własne). Outbox jest zapisywany przez serwis publikacji; lekarz nie operuje na tabeli outbox bezpośrednio.
- **Brak dostępu (nawet odczytu) w normalnym flow:**  
`patient_form_session` (tworzenie/zarządzanie – recepcja/tablet), `consent_definition`, `anamnesis_question_definition`, `anamnesis_option_definition` (słowniki – ADMIN), `outbox_event` (operacyjnie – ADMIN), `patient_import_batch`, `patient_import_error`, `audit_event` (pełna lista – ADMIN).

---

## 5. Rekomendowana implementacja uprawnień

1. **Endpointy API:**
  Dla każdego endpointu z sekcji 3.x „Tak” – sprawdzenie `request.user.role in ('DOCTOR', 'ADMIN')` (lub dedykowana permission class), z object-level check tam, gdzie zwracane są dane wrażliwe (np. dokument medyczny tylko dla „swoich” lub według polityki kliniki).
2. **Frontend (panel lekarza):**
  Ukrycie nawigacji i akcji do modułów z sekcji 3.8; menu ograniczone do: work queue (dokumenty), wybór kolejki/daty (read-only), szablony tekstu, wylogowanie. Brak linków do: użytkownicy, słowniki zgód/anamnezy, import, outbox, retention, merge pacjentów.
3. **Dashboard (US-014):**
  Widok „Status dokumentów” oparty o GET `/medical-documents` z `doctor_view=pending_review` / `published` / `failed`; alerty „wymagające interwencji” = dokumenty z `doctor_view=failed` (np. `pdf_generation_status=FAILED` lub zdarzenie outbox w DEAD_LETTER powiązane z wersją). Nie udostępniać lekarzowi surowej listy outbox-events ani przycisku „Retry” na poziomie pojedynczego zdarzenia – ewentualnie jeden przycisk „Ponów publikację” na poziomie dokumentu, realizowany przez operację po stronie backendu (np. ponowne kolejkowanie zgodnie z PRD), jeśli produkt tak zdecyduje.
4. **Audit:**
  Zdarzenia (publikacja, zapis szkicu, retry) i tak zapisują `actor_user_id`; lekarz nie musi mieć dostępu do pełnej listy audit-events – to pozostaje w module ADMIN.

---

## 6. Podsumowanie – moduły z dostępem DOCTOR


| Kategoria                         | Moduły / zasoby z dostępem (odczyt i/lub zapis)                                                                                                                        |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth                              | login, logout, me                                                                                                                                                      |
| Kolejki (read-only)               | daily-queues (GET), daily-queues/{id}/entries (GET), queue-entries/{id} (GET)                                                                                          |
| Pacjenci (read-only, opcjonalnie) | patients (GET), patients/{id} (GET)                                                                                                                                    |
| Lokacje (read-only)               | clinic-sites (GET), consulting-rooms (GET)                                                                                                                             |
| Dokumenty medyczne                | medical-documents (GET, POST), medical-documents/{id} (GET), draft (PATCH), generate-text (POST), publish (POST), versions (GET); medical-document-versions/{id} (GET) |
| Szablony lekarza                  | doctor-text-templates (GET, POST, GET/PATCH/DELETE własne)                                                                                                             |
| Observability                     | status w ramach medical-documents; opcjonalnie GET /observability/health                                                                                               |


Wszystkie pozostałe moduły (staff-users, consent/anamnesis definitions, intake write, sessions, tablet devices, imports, outbox, operations, retention, audit, merge) – **bez dostępu** dla roli DOCTOR (zarezerwowane dla RECEPTION, ADMIN lub TABLET zgodnie z api-plan i db-plan).