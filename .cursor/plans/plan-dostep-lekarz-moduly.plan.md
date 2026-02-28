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

Lekarz widzi dane w oparciu o szerszy i bezpieczniejszy model autoryzacji (koncepcja OR - autorstwo lub dzisiejsza przypisana kolejka):

- **Kolejki dzienne (daily-queues):** widzi kolejki, do których jest bezpośrednio przypisany w grafiku na dany dzień (`assigned_doctor_id == current_user.id`). Pozwala to na współdzielenie gabinetu fizycznego bez mieszania list pacjentów z różnych zmian (Shift).
- **Pacjenci:** widzi pacjentów przypisanych do klinik (`clinic_site`), w których lekarz kiedykolwiek pracował lub jest do nich przypisany (odczyt na podstawie zdenormalizowanej tabeli `patient_clinic_site`). To eliminuje "silosy gabinetowe" i pozwala widzieć całą historię leczenia pacjenta w ramach placówki.
- **Dokumenty medyczne i Wersje:** ma dostęp, jeśli jest **twórcą** dokumentu (`created_by_user_id == current_user.id`) **LUB** dokument należy do dzisiejszej kolejki, do której lekarz jest przypisany.
- **Zdarzenia Audytowe:** Dostępne tylko w obrębie dokumentów, do których lekarz ma prawo wglądu. Aby zapobiec potężnym zapytaniom SQL (JOIN), klucze autoryzacyjne (`clinic_site_id`, `assigned_doctor_id`) muszą być spłaszczane i zapisywane bezpośrednio w `metadata` logu audytowego przy jego tworzeniu.
- **Szablony tekstu:** Zamiast jednej flagi "globalne", szablony "ogólnodostępne" są przypisane do konkretnej kliniki (`clinic_site_id`). Pozwala to na wieloplacówkowość (Multi-Tenant) bez "śmiecenia" szablonami między miastami.

**Wymóg implementacyjny:** Relacja lekarza z klinikami (`staff_user_clinic_site`). Przypisanie do zmiany (`assigned_doctor_id` w `daily_queue`). Automatyczne uzupełnianie `patient_clinic_site` pod spodem. Lekarz bez przypisanej kliniki widzi puste listy wyników (nie zwracamy błędów 403, po prostu brak danych).

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

Lekarz widzi **tylko kolejki przypisane bezpośrednio do niego na dany dzień/zmianę** (`assigned_doctor_id`). Musi móc wybrać datę i zobaczyć listę pacjentów (wpisów) ze swojej dziennej kolejki oraz otworzyć/utworzyć dokument medyczny dla wybranego wpisu. Nie zarządza kolejkami ani sesjami. W przypadku braku przypisanych kolejek listy są puste.


| Moduł / Zasób                                            | Dostęp DOCTOR | Uwagi                                                                                                      |
| -------------------------------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------- |
| GET `/daily-queues`                                      | Tak (read)    | Tylko kolejki, gdzie `assigned_doctor_id == current_user.id`.                                              |
| GET `/daily-queues/{id}/entries`                         | Tak (read)    | Tylko jeśli `daily_queue` jest przypisana do lekarza. Lista wpisów (np. `entry_status=PATIENT_COMPLETED`). |
| GET `/queue-entries/{id}`                                | Tak (read)    | Tylko jeśli wpis należy do kolejki przypisanej do lekarza.                                                 |
| POST/PATCH/DELETE daily-queues, POST/PATCH queue-entries | Nie           | Zarządzanie kolejką i wpisami należy do RECEPTION.                                                         |


---

### 3.3. Pacjenci (tylko odczyt) – historia pacjenta w obrębie kliniki

Lekarz **musi** mieć dostęp do pacjentów w klinikach, do których jest przypisany (nie tylko z "jego gabinetu"), tak aby nie tworzyć silosów medycznych. Wyszukiwanie i podgląd pacjentów opiera się o relację `patient_clinic_site`.


| Moduł / Zasób                                       | Dostęp DOCTOR | Uwagi                                                                                                                       |
| --------------------------------------------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------- |
| GET `/patients`                                     | Tak (read)    | Wyszukiwanie pacjentów (np. `search`, `last_name`, `date_of_birth`). Wyniki ograniczone do pacjentów z przypisanych klinik. |
| GET `/patients/{id}`                                | Tak (read)    | Szczegóły pacjenta – tylko jeśli pacjent należy do kliniki w zakresie lekarza.                                              |
| GET `/patients/{id}/contact-history`                | Tak (read)    | Historia kontaktów – tylko dla pacjentów z zakresu klinik lekarza.                                                          |
| POST/PATCH `/patients`, POST `/patients/{id}/merge` | Nie           | Tworzenie/edycja pacjentów i scalanie – RECEPTION/ADMIN.                                                                    |


---

### 3.4. Lokacje i gabinety (tylko odczyt)

Potrzebne do kontekstu i filtrów w widoku „kolejka / lista dokumentów”. Lekarz powinien widzieć co najmniej **swoją** klinikę i **swój** gabinet (np. do wyświetlenia w nagłówku lub filtrze).


| Moduł / Zasób                                    | Dostęp DOCTOR | Uwagi                                                                                    |
| ------------------------------------------------ | ------------- | ---------------------------------------------------------------------------------------- |
| GET `/clinic-sites`                              | Tak (read)    | Lista placówek (tylko te kliniki, do których lekarz jest obecnie przypisany).            |
| GET `/consulting-rooms`                          | Tak (read)    | Lista gabinetów (np. z `clinic_site_id`); dla lekarza – tylko te gabinety z tych klinik. |
| POST/PATCH/DELETE clinic-sites, consulting-rooms | Nie           | ADMIN.                                                                                   |


---

### 3.5. Dokumenty medyczne i wersje (główny moduł lekarza)

Pełny flow lekarza (US-008, US-009, US-010): lista dokumentów do opracowania, podgląd intake + szkic, zapis szkicu, generowanie tekstu, publikacja, edycja opublikowanego i ponowna wysyłka.


| Moduł / Zasób                                | Dostęp DOCTOR | Uwagi                                                                                                                                                      |
| -------------------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET `/medical-documents`                     | Tak           | Lista „work queue” **tylko dla dokumentów z własnych kolejek LUB własnego autorstwa**. Parametry: `status`, `queue_date`, `doctor_view`, `patient_search`. |
| GET `/medical-documents/{id}`                | Tak           | Tylko jeśli dokument należy do kolejki lekarza LUB lekarz jest jego autorem. Pełny kontekst.                                                               |
| POST `/medical-documents`                    | Tak           | Utworzenie dokumentu dla `queue_entry_id` – tylko jeśli wpis należy do dzisiejszej kolejki przypisanej do lekarza.                                         |
| PATCH `/medical-documents/{id}/draft`        | Tak           | Zapis szkicu (medical_payload, diagnosis_code, procedure_code) – US-008, US-009.                                                                           |
| POST `/medical-documents/{id}/generate-text` | Tak           | Generowanie tekstów Befund z wybranych opcji (bez publikacji).                                                                                             |
| POST `/medical-documents/{id}/publish`       | Tak           | Publikacja z `publish_request_id`, `publish_locale`, opcjonalnie `resend_sms` – US-009, US-010.                                                            |
| GET `/medical-documents/{id}/versions`       | Tak           | Historia wersji dokumentu – tylko dla dokumentów w zakresie lekarza.                                                                                       |
| GET `/medical-document-versions/{id}`        | Tak           | Szczegóły wersji (status generowania PDF, HiDrive, SMS) – tylko dla wersji dokumentów w zakresie lekarza.                                                  |


Lekarz **nie** wywołuje bezpośrednio endpointów intake (PATCH/PUT/POST na `/intake-forms/...`) – dane intake są tylko do odczytu w `intake_summary` w ramach dokumentu medycznego.

---

### 3.6. Szablony tekstu lekarza (US-019)

Lekarz zarządza własnymi szablonami i korzysta z szablonów publicznych w swojej klinice.


| Moduł / Zasób                        | Dostęp DOCTOR   | Uwagi                                                                                              |
| ------------------------------------ | --------------- | -------------------------------------------------------------------------------------------------- |
| GET `/doctor-text-templates`         | Tak             | Lista szablonów (własne + z przypisanych klinik), filtry: `template_locale`, `scope`, `is_active`. |
| POST `/doctor-text-templates`        | Tak             | Tworzenie własnego szablonu.                                                                       |
| GET `/doctor-text-templates/{id}`    | Tak             | Odczyt szablonu (własny lub dla przypisanej kliniki).                                              |
| PATCH `/doctor-text-templates/{id}`  | Tak             | Tylko dla szablonów własnych (`owner_user_id = current_user`).                                     |
| DELETE `/doctor-text-templates/{id}` | Tak             | Tylko dla szablonów własnych (lub soft-deactivate).                                                |
| Szablony kliniki (`clinic_site_id`)  | Odczyt / użycie | Edycja/usuwanie szablonów kliniki – ADMIN.                                                         |


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

Lekarz **musi** mieć dostęp do zdarzeń audytowych dla **dokumentów do których ma dostęp (autorstwo LUB kolejka)**. Umożliwia to weryfikację zdarzeń w obrębie własnej pracy lekarza i jego pacjentów z danego dnia.


| Moduł / Zasób                             | Dostęp DOCTOR           | Uwagi                                                                                                                   |
| ----------------------------------------- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| GET `/audit-events`                       | Tak (read, ograniczony) | Lista zdarzeń **tylko** dla dokumentów medycznych z zakresu autoryzacji lekarza (szybki odczyt po kluczach `metadata`). |
| GET `/medical-documents/{id}/audit-trail` | Tak (read)              | Zdarzenia audytowe powiązane z danym dokumentem – tylko jeśli dokument jest w zakresie dostępu lekarza.                 |


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

- **Odczyt (bezpośrednio lub przez API), z filtrem object-level (klinika + autorstwo + przypisana kolejka):**  
`staff_user` (własny + przypisanie do klinik via `staff_user_clinic_site`), `patient` (pacjenci przypisani do klinik lekarza via `patient_clinic_site`), `daily_queue` (tylko kolejki przypisane po `assigned_doctor_id`), `queue_entry`, `clinic_site`, `consulting_room`, `patient_intake_form` (w kontekście dokumentu), `patient_intake_consent`, `medical_document`, `medical_document_version`, `doctor_text_template` (własne + klinikowe), `audit_event` (tylko zdarzenia powiązane z dokumentami w zakresie autoryzacji lekarza).
- **Zapis (przez serwisy aplikacyjne):**  
`medical_document`, `medical_document_version` (draft, publish), `doctor_text_template` (własne). Outbox jest zapisywany przez serwis publikacji; lekarz nie operuje na tabeli outbox bezpośrednio.
- **Brak dostępu (nawet odczytu) w normalnym flow:**  
`patient_form_session` (tworzenie/zarządzanie – recepcja/tablet), `consent_definition`, `anamnesis_question_definition`, `anamnesis_option_definition` (słowniki – ADMIN), `outbox_event` (operacyjnie – ADMIN), `patient_import_batch`, `patient_import_error`. Pełna lista `audit_event` bez filtra – ADMIN.

---

## 4a. TODO przed implementacją

1. **[ZROBIONE] Domknięcie decyzji architektonicznych (jedno źródło prawdy):**
  Ujednolicić nazewnictwo i reguły między `plan-dostep-lekarz-moduly.plan.md`, `.ai/prd.md`, `.ai/db-plan.md`, `.ai/api-plan.md`, `.ai/api-plan-pl.md` (szczególnie: autorstwo OR kolejka, zasięg kliniki vs gabinet, audit po `metadata`).
2. **[ZROBIONE] Finalny kontrakt autoryzacji object-level:**
  Spisać finalne reguły w formie testowalnych warunków (`ALLOW` / `DENY`) dla: `daily-queues`, `patients`, `medical-documents`, `audit-events`, `doctor-text-templates`.
3. **[ZROBIONE] Plan migracji danych i rollback:**
  Przygotować migracje DB dla nowych relacji (m.in. przypisania klinik, przypisanie lekarza do zmiany/kolejki, denormalizacja pacjent-klinika, klucze kontekstowe audytu), wraz z planem backfillu i bezpiecznym rollbackiem.
4. **[ZROBIONE] Kontrakty API i kompatybilność FE/BE:**
  Zamrozić payloady i filtry endpointów (w tym endpointy przypisań klinik oraz zakres szablonów), a następnie potwierdzić wpływ zmian na istniejące widoki frontendu.
5. **[ZROBIONE] Wydajność i indeksy (przed codingiem funkcji):**
  Zdefiniować wymagane indeksy i zapytania referencyjne dla `GET /patients`, `GET /medical-documents`, `GET /audit-events`; ustalić progi SLA i plan pomiaru.
6. **[ZROBIONE] Plan testów autoryzacji i regresji:**
  Przygotować macierz testów (role + przypadki graniczne), w tym scenariusze: utrata bieżącego przypisania, współdzielenie gabinetu na zmianach, dostęp do historii pacjenta w klinice, odczyt audytu.
7. **[ZROBIONE] Observability i bezpieczeństwo wdrożenia:**
  Ustalić minimalny zestaw logów/metryk (audit access denied, czasy endpointów, dead-letter/outbox), feature flag / rollout etapowy oraz kryteria GO/NO-GO.

---

## 4b. Plan migracji danych i rollback (MVP -> docelowy model)

1. **Migracja schematu (bez zmian behawioralnych):**
   - dodać `staff_user_clinic_site`,
   - dodać `daily_queue.assigned_doctor_id` (nullable),
   - dodać `patient_clinic_site`,
   - dodać `audit_event.context_clinic_site_id` + indeks GIN na `audit_event.metadata`,
   - w `doctor_text_template` wprowadzić `clinic_site_id` i rozpocząć odchodzenie od `is_global`.
2. **Backfill danych historycznych:**
   - uzupełnić `staff_user_clinic_site` na podstawie historycznych kolejek i gabinetów,
   - uzupełnić `patient_clinic_site` na podstawie `queue_entry -> daily_queue` (upsert po `(patient_id, clinic_site_id)`),
   - uzupełnić `daily_queue.assigned_doctor_id` tam, gdzie można wywnioskować lekarza z dokumentów/operacji dziennych,
   - uzupełnić `audit_event.metadata` kluczami `clinic_site_id`, `assigned_doctor_id`, `medical_document_id` (jeżeli brak).
3. **Tryb przejściowy aplikacji (kompatybilność):**
   - feature flag `doctor_scope_v2`,
   - przy `doctor_scope_v2=false`: stary mechanizm,
   - przy `doctor_scope_v2=true`: nowe reguły `AUTHOR OR ASSIGNED_QUEUE` + kliniki,
   - podwójny zapis kontekstu audytu (stare + nowe pola) do czasu stabilizacji.
4. **Przełączenie i czyszczenie technicznego długu:**
   - po weryfikacji metryk i testów: domyślnie `doctor_scope_v2=true`,
   - usunąć odwołania do `staff_user_consulting_room` w kodzie i dokumentacji,
   - zakończyć migrację `doctor_text_template` (brak `is_global`, tylko `owner_user_id` XOR `clinic_site_id`).
5. **Rollback (bez utraty danych):**
   - rollback logiczny: wyłączyć `doctor_scope_v2`,
   - rollback schematu: pozostawić nowe kolumny jako nieużywane (nie usuwać od razu),
   - rollback danych: brak kasowania backfillowanych rekordów; incydenty adresować korektą danych.

---

## 4c. Kontrakty API do zamrożenia (Definition of Done)

1. **Staff przypisania klinik:**
   - `GET /staff-users/{id}/clinic-sites`
   - `POST /staff-users/{id}/clinic-sites` z payloadem:
     - `clinic_site_ids: uuid[]` (replace-all)
2. **Kolejki lekarza:**
   - `GET /daily-queues` zwraca tylko rekordy, gdzie `assigned_doctor_id == current_user.id`
   - `GET /daily-queues/{id}/entries` i `GET /queue-entries/{id}` respektują ten sam filtr
3. **Pacjenci:**
   - `GET /patients` filtruje po `patient_clinic_site` i `staff_user_clinic_site`
4. **Dokumenty i audit:**
   - `GET /medical-documents*`: reguła `AUTHOR OR ASSIGNED_QUEUE`
   - `GET /audit-events`: filtrowanie po kluczach kontekstowych w `audit_event.metadata`
   - `GET /medical-documents/{id}/audit-trail`: tylko dla dokumentów w zakresie autoryzacji lekarza
5. **Szablony tekstu:**
   - `GET /doctor-text-templates` z `scope=clinic|private|all`
   - create/update szablonu: `owner_user_id` XOR `clinic_site_id`
6. **Publikacja dokumentu:**
   - `POST /medical-documents/{id}/publish` wymaga `publish_locale`
   - `publish_locale` jest persistowane na `medical_document_version`

---

## 4d. Wydajność i SLA (przed implementacją endpointów)

1. **SLA p95 (target):**
   - `GET /patients`: <= 250 ms (page_size <= 20)
   - `GET /medical-documents`: <= 300 ms
   - `GET /audit-events`: <= 300 ms
2. **Indeksy krytyczne:**
   - `patient_clinic_site(patient_id, clinic_site_id)` + odwrotny `(clinic_site_id, patient_id)`
   - `daily_queue(assigned_doctor_id, queue_date, status)`
   - `medical_document(created_by_user_id, created_at)` + indeksy relacyjne do `queue_entry`
   - `audit_event USING GIN (metadata jsonb_path_ops)` oraz B-Tree po `event_time`
3. **Zapytania referencyjne do benchmarków:**
   - wyszukiwarka pacjentów (`search` + `clinic_site` scope)
   - work queue lekarza (`doctor_view`, `queue_date`)
   - audit feed lekarza (filtr po `metadata.assigned_doctor_id`)
4. **Warunek wejścia na produkcję:**
   - brak pełnych skanów tabel dla krytycznych endpointów przy danych testowych >= 1M rekordów audit.

---

## 4e. Plan testów autoryzacji i regresji

1. **Role i zakresy:**
   - testy `DOCTOR`, `ADMIN`, `RECEPTION`, `TABLET` dla endpointów sekcji 3.x
2. **Scenariusze krytyczne:**
   - lekarz traci bieżące przypisanie, ale widzi własne historyczne dokumenty (AUTHOR)
   - dwóch lekarzy dzieli gabinet na zmianach i widzi tylko swoje kolejki
   - lekarz widzi historię pacjenta w swojej klinice, nie widzi poza kliniką
   - audit zwraca tylko dokumenty w zakresie autoryzacji
3. **Testy kontraktowe API:**
   - walidacja payloadów i filtrów z sekcji 4c
4. **Testy wydajnościowe:**
   - smoke performance dla `/patients`, `/medical-documents`, `/audit-events` z danymi wolumenowymi

---

## 4f. Observability, feature flag i rollout

1. **Minimalne logi:**
   - `doctor_scope_decision` (`ALLOW`/`DENY`, endpoint, reason_code)
   - `audit_scope_query` (czas, liczba rekordów)
2. **Metryki:**
   - `doctor_scope_denied_total`
   - `doctor_scope_allowed_total`
   - `endpoint_latency_ms{endpoint=...}` (p50/p95/p99)
3. **Feature flag:**
   - `doctor_scope_v2` (off -> old behavior, on -> nowy model)
4. **Rollout:**
   - etap 1: staging + testy integracyjne
   - etap 2: produkcja na wybranej klinice (canary)
   - etap 3: pełne włączenie i usunięcie starej ścieżki
5. **GO/NO-GO:**
   - GO: brak krytycznych DENY false-positive, SLA spełnione, brak wzrostu 5xx
   - NO-GO: przekroczenia SLA lub błędy autoryzacji wpływające na workflow lekarza

---

## 5. Rekomendowana implementacja uprawnień

1. **Endpointy API:**
  Dla każdego endpointu z sekcji 3.x „Tak” – sprawdzenie `request.user.role in ('DOCTOR', 'ADMIN')` (lub dedykowana permission class) oraz **object-level check zgodnie z polityką widoczności (2a)**:  
  - kolejki/wpisy po `assigned_doctor_id`,  
  - pacjenci po `patient_clinic_site` i `staff_user_clinic_site`,  
  - dokumenty po regule `AUTHOR OR ASSIGNED_QUEUE`,  
  - audit po kluczach kontekstowych w `audit_event.metadata`.  
  Lekarz bez przypisanej kliniki/kolejki otrzymuje pustą listę. ADMIN może pomijać filtry object-level (pełna widoczność operacyjna).
2. **Frontend (panel lekarza):**
  Ukrycie nawigacji i akcji do modułów z sekcji 3.9; menu ograniczone do: work queue (dokumenty), wybór kolejki/daty (read-only), pacjenci (wyszukiwanie z przypisanych klinik), szablony tekstu, audit (dla dokumentów w zakresie lekarza), wylogowanie. Brak linków do: użytkownicy, słowniki zgód/anamnezy, import, outbox, retention, merge pacjentów.
3. **Dashboard (US-014):**
  Widok „Status dokumentów” oparty o GET `/medical-documents` z `doctor_view=pending_review` / `published` / `failed` (wyniki już ograniczone do zakresu autoryzacji lekarza); alerty „wymagające interwencji” = dokumenty z `doctor_view=failed`.
4. **Audit:**
  Lekarz ma dostęp do GET `/audit-events` (z filtrem po dokumentach w swoim zakresie) oraz do GET `/medical-documents/{id}/audit-trail` dla dokumentów w swoim zakresie autoryzacji (AUTHOR OR ASSIGNED_QUEUE).

---

## 5a. Kontrakt autoryzacji object-level (ALLOW / DENY)

1. **`daily-queues`**
  - `ALLOW`: `daily_queue.assigned_doctor_id == current_user.id`
  - `DENY`: każdy inny przypadek
2. **`queue-entries`**
  - `ALLOW`: `queue_entry.daily_queue.assigned_doctor_id == current_user.id`
  - `DENY`: każdy inny przypadek
3. **`patients`**
  - `ALLOW`: istnieje rekord `patient_clinic_site(patient_id, clinic_site_id)` oraz `clinic_site_id` jest w `staff_user_clinic_site` lekarza
  - `DENY`: pacjent poza zakresem klinik lekarza
4. **`medical-documents`**
  - `ALLOW`: `medical_document.created_by_user_id == current_user.id` **OR** `medical_document.queue_entry.daily_queue.assigned_doctor_id == current_user.id`
  - `DENY`: brak obu warunków
5. **`audit-events`**
  - `ALLOW`: `audit_event.metadata.assigned_doctor_id == current_user.id` **OR** (`audit_event.metadata.actor_user_id == current_user.id` i event dotyczy dokumentu widocznego dla lekarza)
  - `DENY`: brak obu warunków
6. **`doctor-text-templates`**
  - `ALLOW-READ`: `owner_user_id == current_user.id` **OR** `clinic_site_id` w `staff_user_clinic_site` lekarza
  - `ALLOW-WRITE`: tylko `owner_user_id == current_user.id`
  - `DENY`: każdy inny przypadek

---

## 6. Podsumowanie – moduły z dostępem DOCTOR


| Kategoria            | Moduły / zasoby z dostępem (odczyt i/lub zapis)                                                                                                                                                       |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth                 | login, logout, me                                                                                                                                                                                     |
| Kolejki (read-only)  | daily-queues (GET), daily-queues/{id}/entries (GET), queue-entries/{id} (GET) – **tylko kolejki przypisane do lekarza (`assigned_doctor_id`)**                                                        |
| Pacjenci (read-only) | patients (GET), patients/{id} (GET), patients/{id}/contact-history (GET) – **pacjenci z przypisanych klinik lekarza (`patient_clinic_site`)**                                                         |
| Lokacje (read-only)  | clinic-sites (GET), consulting-rooms (GET)                                                                                                                                                            |
| Dokumenty medyczne   | medical-documents (GET, POST), medical-documents/{id} (GET), draft (PATCH), generate-text (POST), publish (POST), versions (GET); medical-document-versions/{id} (GET) – **AUTHOR OR ASSIGNED_QUEUE** |
| Szablony lekarza     | doctor-text-templates (GET, POST, GET/PATCH/DELETE własne)                                                                                                                                            |
| Audit (ograniczony)  | audit-events (GET z filtrem po dokumentach w zakresie), medical-documents/{id}/audit-trail (GET) – **dla dokumentów w zakresie autoryzacji lekarza**                                                  |
| Observability        | status w ramach medical-documents; opcjonalnie GET /observability/health                                                                                                                              |


Wszystkie pozostałe moduły (staff-users, consent/anamnesis definitions, intake write, sessions, tablet devices, imports, outbox, operations, retention, pełna lista audit bez filtra, merge) – **bez dostępu** dla roli DOCTOR (zarezerwowane dla RECEPTION, ADMIN lub TABLET zgodnie z api-plan i db-plan).