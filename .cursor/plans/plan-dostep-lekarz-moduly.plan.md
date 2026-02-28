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

## 2a. Polityka widoczności dla DOCTOR (object-level)

Lekarz widzi **wyłącznie** dane przypisane do **swojej kliniki**, **swojego gabinetu** i **swojej dziennej kolejki**:

- **Kolejki dzienne (daily-queues):** tylko kolejki dla **przypisanego lekarzowi** `consulting_room` w ramach **jego** `clinic_site`.
- **Wpisy kolejki (queue entries):** tylko wpisy z tych kolejek (w efekcie: pacjenci ze swojej dziennej kolejki, swojego gabinetu, w swojej klinice).
- **Dokumenty medyczne:** tylko dokumenty powiązane z tymi wpisami kolejki (czyli z dziennej kolejki swojego gabinetu w swojej klinice).
- **Pacjenci:** tylko pacjenci **ze swojej kliniki** (np. pacjenci mający wizyty/wpisy w kolejkach danej kliniki – definicja do uzupełnienia w modelu, np. przez `queue_entry` → `daily_queue` → `clinic_site_id`).

**Wymóg implementacyjny:** `staff_user` musi mieć przypisanie do kliniki i gabinetu (np. `clinic_site_id`, `consulting_room_id` lub relacja many-to-many), aby backend mógł stosować filtry object-level we wszystkich endpointach z sekcji 3.

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

Lekarz widzi **tylko kolejki swojego gabinetu w swojej klinice** (zgodnie z polityką widoczności 2a). Musi móc wybrać datę i zobaczyć listę pacjentów (wpisów) ze swojej dziennej kolejki oraz otworzyć/utworzyć dokument medyczny dla wybranego wpisu. Nie zarządza kolejkami ani sesjami.


| Moduł / Zasób                                            | Dostęp DOCTOR | Uwagi                                                                                                                                          |
| -------------------------------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| GET `/daily-queues`                                      | Tak (read)    | Tylko kolejki dla **przypisanego lekarzowi** `consulting_room` w **jego** `clinic_site` (np. filtry po dacie).                                 |
| GET `/daily-queues/{id}/entries`                         | Tak (read)    | Tylko jeśli `daily_queue` należy do gabinetu i kliniki lekarza. Lista wpisów (np. `entry_status=PATIENT_COMPLETED`) – pacjenci do opracowania. |
| GET `/queue-entries/{id}`                                | Tak (read)    | Tylko jeśli wpis należy do kolejki z gabinetu/kliniki lekarza. Szczegóły wpisu (pacjent, status, notatki).                                     |
| POST/PATCH/DELETE daily-queues, POST/PATCH queue-entries | Nie           | Zarządzanie kolejką i wpisami należy do RECEPTION.                                                                                             |


---

### 3.3. Pacjenci (tylko odczyt) – obowiązkowy dostęp w ramach swojej kliniki

Lekarz **musi** mieć dostęp do pacjentów **ze swojej kliniki** (zgodnie z polityką widoczności 2a): wyszukiwanie i podgląd pacjentów mających wizyty w kolejkach danej kliniki (np. powiązanie przez `queue_entry` → `daily_queue` → `clinic_site_id`). Dane pacjenta są też dostępne w kontekście dokumentu (intake summary w GET `/medical-documents/{id}`).


| Moduł / Zasób                                       | Dostęp DOCTOR | Uwagi                                                                                                                               |
| --------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| GET `/patients`                                     | Tak (read)    | Wyszukiwanie pacjentów **ze swojej kliniki** (np. `search`, `last_name`, `date_of_birth`). Wyniki ograniczone do pacjentów kliniki. |
| GET `/patients/{id}`                                | Tak (read)    | Szczegóły pacjenta – tylko jeśli pacjent należy do kliniki lekarza (np. ma w historii wpis w kolejce tej kliniki).                  |
| GET `/patients/{id}/contact-history`                | Tak (read)    | Historia kontaktów – tylko dla pacjentów ze swojej kliniki.                                                                         |
| POST/PATCH `/patients`, POST `/patients/{id}/merge` | Nie           | Tworzenie/edycja pacjentów i scalanie – RECEPTION/ADMIN.                                                                            |


---

### 3.4. Lokacje i gabinety (tylko odczyt)

Potrzebne do kontekstu i filtrów w widoku „kolejka / lista dokumentów”. Lekarz powinien widzieć co najmniej **swoją** klinikę i **swój** gabinet (np. do wyświetlenia w nagłówku lub filtrze).


| Moduł / Zasób                                    | Dostęp DOCTOR | Uwagi                                                                                       |
| ------------------------------------------------ | ------------- | ------------------------------------------------------------------------------------------- |
| GET `/clinic-sites`                              | Tak (read)    | Lista placówek (w praktyce dla lekarza: co najmniej jego `clinic_site`).                    |
| GET `/consulting-rooms`                          | Tak (read)    | Lista gabinetów (np. z `clinic_site_id`); dla lekarza – co najmniej jego `consulting_room`. |
| POST/PATCH/DELETE clinic-sites, consulting-rooms | Nie           | ADMIN.                                                                                      |


---

### 3.5. Dokumenty medyczne i wersje (główny moduł lekarza)

Pełny flow lekarza (US-008, US-009, US-010): lista dokumentów do opracowania, podgląd intake + szkic, zapis szkicu, generowanie tekstu, publikacja, edycja opublikowanego i ponowna wysyłka.


| Moduł / Zasób                                | Dostęp DOCTOR | Uwagi                                                                                                                                                                                |
| -------------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| GET `/medical-documents`                     | Tak           | Lista „work queue” **tylko dla dokumentów z kolejki swojego gabinetu w swojej klinice**. Parametry: `status`, `queue_date`, `doctor_view`, `patient_search`. Zgodne z api-plan 2.10. |
| GET `/medical-documents/{id}`                | Tak           | Tylko jeśli dokument należy do kolejki gabinetu/kliniki lekarza. Pełny kontekst: intake summary (zgody, anamneza, body map, pacjent), aktualna wersja, statusy PDF/HiDrive/SMS.      |
| POST `/medical-documents`                    | Tak           | Utworzenie dokumentu dla `queue_entry_id` (idempotentnie, gdy intake SUBMITTED).                                                                                                     |
| PATCH `/medical-documents/{id}/draft`        | Tak           | Zapis szkicu (medical_payload, diagnosis_code, procedure_code) – US-008, US-009.                                                                                                     |
| POST `/medical-documents/{id}/generate-text` | Tak           | Generowanie tekstów Befund z wybranych opcji (bez publikacji).                                                                                                                       |
| POST `/medical-documents/{id}/publish`       | Tak           | Publikacja z `publish_request_id`, `publish_locale`, opcjonalnie `resend_sms` – US-009, US-010.                                                                                      |
| GET `/medical-documents/{id}/versions`       | Tak           | Historia wersji dokumentu.                                                                                                                                                           |
| GET `/medical-document-versions/{id}`        | Tak           | Szczegóły wersji (status generowania PDF, HiDrive, SMS).                                                                                                                             |


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

### 3.8. Audit (audit-events dla dokumentów lekarza)

Lekarz **musi** mieć dostęp do zdarzeń audytowych dla **dokumentów, które opublikował** (oraz ogólniej: dla dokumentów w swoim zakresie widoczności – kolejka swojego gabinetu w swojej klinice). Umożliwia to weryfikację „kto i kiedy zapisał/opublikował” oraz potrzeby compliance.


| Moduł / Zasób                             | Dostęp DOCTOR           | Uwagi                                                                                                                                                                                                                                                                     |
| ----------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET `/audit-events`                       | Tak (read, ograniczony) | Lista zdarzeń **tylko** dla dokumentów medycznych z zakresu lekarza (np. filtr `medical_document_id` ∈ dokumenty dostępne dla lekarza). Alternatywnie: filtr `actor_user_id = current_user` dla zdarzeń inicjowanych przez tego lekarza („dokumenty, które opublikował”). |
| GET `/medical-documents/{id}/audit-trail` | Tak (read)              | Zdarzenia audytowe powiązane z danym dokumentem – tylko jeśli dokument należy do kolejki gabinetu/kliniki lekarza. Zalecane dla widoku „historia zdarzeń przy dokumencie”.                                                                                                |


Pełna lista audit-events (wszystkie typy zdarzeń, wszystkie podmioty) pozostaje w module ADMIN.

---

### 3.9. Moduły bez dostępu dla DOCTOR


| Moduł / Zasób                                                                        | Dostęp DOCTOR | Uwagi                                                        |
| ------------------------------------------------------------------------------------ | ------------- | ------------------------------------------------------------ |
| Staff users (GET/POST/PATCH/DELETE `/staff-users`)                                   | Nie           | ADMIN.                                                       |
| Consent definitions (CRUD `/consent-definitions`)                                    | Nie           | Słownik zgód – ADMIN.                                        |
| Anamnesis definitions (CRUD `/anamnesis-definitions`)                                | Nie           | Słownik anamnezy – ADMIN.                                    |
| Intake forms – zapis (PATCH body_map, PUT consents/anamnesis, POST signature/submit) | Nie           | Tablet/recepcja; lekarz tylko odczyt w kontekście dokumentu. |
| Patient sessions (POST `/queue-entries/{id}/sessions`)                               | Nie           | TABLET/RECEPTION/ADMIN.                                      |
| Tablet devices (CRUD `/tablet-devices`)                                              | Nie           | RECEPTION/ADMIN.                                             |
| Imports (POST `/imports/patients`, GET batches, emergency template)                  | Nie           | RECEPTION/ADMIN.                                             |
| Operations: retention (POST `/operations/retention/run`)                             | Nie           | ADMIN.                                                       |
| Merge patients (POST `/patients/{id}/merge`)                                         | Nie           | ADMIN.                                                       |


---

## 4. Encje w bazie (db-plan) – pod kątem roli DOCTOR

- **Odczyt (bezpośrednio lub przez API), z filtrem object-level (klinika, gabinet):**  
`staff_user` (własny + przypisanie do `clinic_site`, `consulting_room`), `patient` (tylko pacjenci ze swojej kliniki), `daily_queue` (tylko kolejki swojego gabinetu w swojej klinice), `queue_entry`, `clinic_site`, `consulting_room`, `patient_intake_form` (w kontekście dokumentu), `patient_intake_consent`, `medical_document`, `medical_document_version`, `doctor_text_template` (własne + globalne), `audit_event` (tylko zdarzenia powiązane z dokumentami w zakresie lekarza).
- **Zapis (przez serwisy aplikacyjne):**  
`medical_document`, `medical_document_version` (draft, publish), `doctor_text_template` (własne). Outbox jest zapisywany przez serwis publikacji; lekarz nie operuje na tabeli outbox bezpośrednio.
- **Brak dostępu (nawet odczytu) w normalnym flow:**  
`patient_form_session` (tworzenie/zarządzanie – recepcja/tablet), `consent_definition`, `anamnesis_question_definition`, `anamnesis_option_definition` (słowniki – ADMIN), `outbox_event` (operacyjnie – ADMIN), `patient_import_batch`, `patient_import_error`. Pełna lista `audit_event` bez filtra – ADMIN.

---

## 5. Rekomendowana implementacja uprawnień

1. **Endpointy API:**
  Dla każdego endpointu z sekcji 3.x „Tak” – sprawdzenie `request.user.role in ('DOCTOR', 'ADMIN')` (lub dedykowana permission class) oraz **object-level check zgodnie z polityką widoczności (2a)**: kolejki/wpisy/dokumenty/pacjenci tylko ze swojej kliniki i swojego gabinetu. Wymóg: model użytkownika (np. `staff_user`) musi zawierać przypisanie do `clinic_site` i `consulting_room` (lub relację many-to-many). ADMIN może pomijać filtry object-level (pełna widoczność operacyjna) – do ustalenia w implementacji.
2. **Frontend (panel lekarza):**
  Ukrycie nawigacji i akcji do modułów z sekcji 3.9; menu ograniczone do: work queue (dokumenty), wybór kolejki/daty (read-only), pacjenci (wyszukiwanie w swojej klinice), szablony tekstu, audit (dla swoich dokumentów), wylogowanie. Brak linków do: użytkownicy, słowniki zgód/anamnezy, import, outbox, retention, merge pacjentów.
3. **Dashboard (US-014):**
  Widok „Status dokumentów” oparty o GET `/medical-documents` z `doctor_view=pending_review` / `published` / `failed` (wyniki już ograniczone do zakresu lekarza); alerty „wymagające interwencji” = dokumenty z `doctor_view=failed`. Nie udostępniać lekarzowi surowej listy outbox-events ani przycisku „Retry” na poziomie pojedynczego zdarzenia – ewentualnie przycisk „Ponów publikację” na poziomie dokumentu, realizowany przez operację po stronie backendu, jeśli produkt tak zdecyduje.
4. **Audit:**
  Lekarz ma dostęp do GET `/audit-events` (z filtrem po dokumentach w swoim zakresie lub po `actor_user_id = current_user`) oraz do GET `/medical-documents/{id}/audit-trail` dla dokumentów w swoim zakresie. Pełna lista audit-events bez filtra pozostaje w module ADMIN.

---

## 6. Podsumowanie – moduły z dostępem DOCTOR


| Kategoria               | Moduły / zasoby z dostępem (odczyt i/lub zapis)                                                                                                                                 |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth                    | login, logout, me                                                                                                                                                                |
| Kolejki (read-only)     | daily-queues (GET), daily-queues/{id}/entries (GET), queue-entries/{id} (GET) – **tylko swoja dzienna kolejka, swój gabinet, swoja klinika**                                    |
| Pacjenci (read-only)    | patients (GET), patients/{id} (GET), patients/{id}/contact-history (GET) – **tylko pacjenci ze swojej kliniki**                                                                  |
| Lokacje (read-only)     | clinic-sites (GET), consulting-rooms (GET)                                                                                                                                       |
| Dokumenty medyczne      | medical-documents (GET, POST), medical-documents/{id} (GET), draft (PATCH), generate-text (POST), publish (POST), versions (GET); medical-document-versions/{id} (GET) – **tylko dokumenty z kolejki swojego gabinetu w swojej klinice** |
| Szablony lekarza        | doctor-text-templates (GET, POST, GET/PATCH/DELETE własne)                                                                                                                       |
| Audit (ograniczony)     | audit-events (GET z filtrem po dokumentach w zakresie / po actor_user_id), medical-documents/{id}/audit-trail (GET) – **dla dokumentów, które lekarz opublikował / do których ma dostęp** |
| Observability           | status w ramach medical-documents; opcjonalnie GET /observability/health                                                                                                         |


Wszystkie pozostałe moduły (staff-users, consent/anamnesis definitions, intake write, sessions, tablet devices, imports, outbox, operations, retention, pełna lista audit bez filtra, merge) – **bez dostępu** dla roli DOCTOR (zarezerwowane dla RECEPTION, ADMIN lub TABLET zgodnie z api-plan i db-plan).