---
name: plan-implementacji-cogitomedica
overview: Plan wdrożenia backendu Django dla Cogitomedica na bazie PRD i DB planu, z podziałem na fazy, zależności i Definition of Done dla MVP oraz etapów integracyjnych.
todos:
  - id: foundation-setup
    content: Zdefiniować architekturę aplikacji Django, konfigurację środowisk i standardy testowe/type hints.
    status: completed
  - id: db-migrations
    content: Zaimplementować modele i migracje zgodnie z .ai/db-plan.md wraz z indeksami i constraintami.
    status: completed
  - id: phase1-reception-tablet
    content: ""
    status: in_progress
  - id: phase2-medical-publish
    content: ""
    status: in_progress
  - id: outbox-integrations
    content: Uruchomić pipeline outbox + Django Tasks + PDF + HiDrive/SMS + retencję 30 dni.
    status: in_progress
  - id: api-contracts-priority
    content: ""
    status: in_progress
  - id: phase3-import-hidrive-api
    content: Dowieźć import dzienny i awaryjny oraz integrację API HiDrive (Faza 3).
    status: pending
  - id: observability-alerting
    content: Wdrożyć metryki, dashboardy, alerting i runbooki dla outbox/import/integracji.
    status: pending
  - id: hardening-release
    content: Wykonać hardening bezpieczeństwa, testy E2E i checklistę gotowości produkcyjnej.
    status: pending
  - id: doctor-templates-us019
    content: "Zaimplementować US-019 (szablony lekarza DE/EN): CRUD, aktywacja/dezaktywacja, uprawnienia globalne/prywatne i integracja z generate-text."
    status: pending
  - id: auth-session-hardening
    content: "Domknąć wymagania US-001: timeout sesji, polityki wygasania i testy bezpieczeństwa auth/session."
    status: pending
  - id: domain-audit-trail
    content: Dodać pełny audit trail zdarzeń domenowych (edycja tekstu, publikacja/republikacja, retencja) i włączyć go do DoD.
    status: in_progress
isProject: false
---

# Plan implementacji Cogitomedica (PRD + DB)

## Kontekst startowy

- Repo jest obecnie blisko stanu greenfield (aktywny szkielet Django: `[manage.py](C:/Users/piotr/Programming/cogitomedica/manage.py)`, `[cogitomedica/settings.py](C:/Users/piotr/Programming/cogitomedica/cogitomedica/settings.py)`, `[cogitomedica/urls.py](C:/Users/piotr/Programming/cogitomedica/cogitomedica/urls.py)`).
- Wymagania domenowe i model danych są już dobrze zdefiniowane w `[/.ai/prd.md](C:/Users/piotr/Programming/cogitomedica/.ai/prd.md)` i `[/.ai/db-plan.md](C:/Users/piotr/Programming/cogitomedica/.ai/db-plan.md)`.
- Priorytet: architektura warstwowa (API -> serializers/schemas -> services -> models), idempotentna publikacja, outbox, Django Tasks, testy przejść stanów i observability.

## Stan bieżący (aktualizacja)

- Etap 1 i Etap 2 oznaczone jako ukończone (foundation + modele/migracje).
- Runtime backendu podniesiony do Django 6.0.x, a mechanizm zadań tła ujednolicony do jednego rozwiązania: **Django Tasks + Transactional Outbox**.
- Dokumentacje projektowe (`README.md`, `.ai/prd.md`, `.ai/db-plan.md`, `.ai/api-plan.md`, `.ai/api-plan-pl.md`) zaktualizowane pod Django 6 i `django.tasks`.
- Zredukowano dług w zależnościach: aktualizacje krytycznych bibliotek HTTP/TLS, usunięcie duplikatu `dotenv`, usunięcie nieużywanych `django-select2`, `reportlab`, `PyPDF2`, dodanie `requirements-dev.txt` (pytest + QA), przejście na `psycopg`.
- Zaimplementowano kluczowe serwisy domenowe i testy: Faza 1 (`reception` + `intake`), Faza 2 (`medical`), pipeline outbox oraz bazowy audit trail.
- Decyzja wykonawcza: **API jest aktualnie najwyższym priorytetem**, a walidacja payloadów JSON ma być realizowana przez **Pydantic v2**.

## Docelowa architektura modułów

- Utwórz aplikacje Django (proponowany podział):
  - `apps/core` (wspólne: błędy domenowe, typy, utils, base model, telemetry).
  - `apps/users` (custom `staff_user`, role i auth).
  - `apps/reception` (patient, daily_queue, queue_entry, tablet session, import).
  - `apps/intake` (zgody, ankieta, body map, podpis).
  - `apps/medical` (medical_document, wersje, szablony lekarza).
  - `apps/outbox` (outbox_event + zadania Django Tasks).
  - `apps/integrations` (HiDrive mock/API, SMS provider).
  - `apps/operations` (audit_event, runbook hooks, metryki operacyjne).
- Utrzymaj kontrakty i routing API w osobnych pakietach `api/serializers/services` per aplikacja.

```mermaid
flowchart LR
  ReceptionUI --> ReceptionAPI
  TabletUI --> IntakeAPI
  DoctorUI --> MedicalAPI
  ReceptionAPI --> ReceptionService
  IntakeAPI --> IntakeService
  MedicalAPI --> MedicalService
  ReceptionService --> PostgresDB
  IntakeService --> PostgresDB
  MedicalService --> PostgresDB
  MedicalService --> OutboxService
  OutboxService --> PostgresDB
  DjangoTasksWorker --> OutboxService
  DjangoTasksWorker --> PdfGenerator
  DjangoTasksWorker --> HiDriveAdapter
  DjangoTasksWorker --> SmsAdapter
  MetricsExporter --> Prometheus
  Prometheus --> Grafana
```



## Etap 1: Fundament techniczny i standardy

- Skonfiguruj ustawienia aplikacji i środowisk (`dev/test/prod`) w `[cogitomedica/settings.py](C:/Users/piotr/Programming/cogitomedica/cogitomedica/settings.py)`:
  - `AUTH_USER_MODEL`, `LANGUAGES` (`de`, `en`), timezone, security flags per env, OpenTelemetry, Prometheus.
  - Rejestracja `TASKS`, limity batch/retry/circuit-breaker dla outbox.
- Dodaj wspólne mechanizmy:
  - bazowe klasy modeli (`UUID`, `created_at`, `updated_at`),
  - globalny handler błędów domenowych -> HTTP,
  - wspólne typed DTO (Pydantic/DRF) dla JSON payloadów (`schema_version`).
- Ustal standard testów `pytest` + `pytest-django` i fixture factory dla ról (`RECEPTION`, `DOCTOR`, `ADMIN`).

## Etap 2: Model danych i migracje (DB-first)

- Zaimplementuj modele i migracje 1:1 wg `[/.ai/db-plan.md](C:/Users/piotr/Programming/cogitomedica/.ai/db-plan.md)`:
  - ENUM-y, constraints, unique keys, partial indexes, GIN indexes, `citext`, `pgcrypto`.
  - Priorytet tabel krytycznych: `staff_user`, `patient`, `daily_queue`, `queue_entry`, `patient_form_session`, `patient_intake_form`, `medical_document`, `medical_document_version`, `outbox_event`, `patient_import_*`.
- Wydziel migracje na paczki tematyczne (identity/queue/intake/medical/outbox/import), aby uprościć rollback i review.
- Dodaj testy integralności DB (constraint tests) dla: statusów, idempotency key, retencji i tokenów.

## Etap 3: Faza 1 PRD (Recepcja + Tablet, API-first)

- Priorytet realizacji w tym etapie:
  - najpierw endpointy API (DRF) oparte o istniejące serwisy domenowe,
  - następnie domknięcie walidacji kontraktów i testów E2E.
- Zaimplementuj serwisy domenowe:
  - `create_or_update_patient_manual()` z `TEMPORARY` + alert admin przy braku `doctolib_patient_id`.
  - `create_queue_entry()` z dopuszczeniem wielu wizyt/dzień.
  - `issue_tablet_session_token_latest_wins()` (`active_session_id`, hash tokenu, expiry).
  - `submit_patient_intake_form()` z walidacją wymaganych zgód i pytań anamnestycznych.
- Zaimplementuj API i walidację payloadów:
  - intake (`anamnesis_payload`, `body_map_data`, podpis),
  - locale-aware słowniki pytań/zgód (DE/EN, neutralne kody w DB).
  - walidacja kontraktów JSON przez **Pydantic v2** (`schema_version` obowiązkowe).
- Dodaj testy przejść stanu `queue_entry` i `patient_intake_form` (pozytywne + negatywne).

## Etap 4: Faza 2 PRD (Panel lekarza + publikacja)

- Zaimplementuj dokument medyczny i wersjonowanie:
  - `save_draft_document_version()`,
  - `publish_document_version()` z `transaction.atomic` + `select_for_update` + idempotencja (`publish_request_id` i/lub in-progress guard).
- Zaimplementuj US-019 (szablony lekarza DE/EN):
  - CRUD szablonów lekarza (`create/update/activate/deactivate`),
  - rozróżnienie uprawnień dla szablonów globalnych (klinika) i prywatnych (per lekarz),
  - użycie szablonu bazowego w endpointach `generate-text` i zapis `generated_text`/`edited_text`.
- Wprowadź kontrakt `medical_payload` v1 (global + lesions, `generated_text`/`edited_text`, template context).
- Wdroż walidację `medical_payload` przez **Pydantic v2** (wersjonowanie schematu + kompatybilność wsteczna).
- Dodaj logikę republish (edycja opublikowanego dokumentu -> nowa wersja, ta sama ścieżka HiDrive, opcjonalny SMS).
- Pokryj testami scenariusze wyścigów (podwójne kliknięcie publish, retry publish).

## Etap 5: Outbox + Django Tasks + integracje

- Zbuduj przetwarzanie outbox przez Django Tasks (cykliczne enqueue):
  - sekwencja `GENERATE_PDF -> HIDRIVE_UPLOAD -> SMS_SEND`,
  - lockowanie `FOR UPDATE SKIP LOCKED`, retry/backoff, `DEAD_LETTER`.
- Faza 1-2: adapter HiDrive mock zgodny z docelowym kontraktem.
- Faza 3: adapter API HiDrive + import dzienny `.xlsx/.csv` (manual + harmonogram), w tym importer awaryjny.
- Dodaj retencję 30 dni: usuń lokalny PDF tylko gdy `hidrive_sent=true && sms_sent=true` + audit event.

## Etap 6: Observability, alerting i runbooki

- Dodaj metryki OTel/Prometheus wymagane przez PRD:
  - outbox (`pending_count`, `failed_count`, `dead_letter_count`, `oldest_pending_age_seconds`, latency p95/p99),
  - integracje (success ratio/error rate),
  - import (`row_error_rate`, processing time),
  - dokumenty (publish->hidrive/sms delay).
- Przygotuj dashboardy (recepcja i utrzymanie) i reguły alertów z progami PRD.
- Dla outbox/import/integracji dodaj runbooki operacyjne do repo.
- Dodaj audit trail zdarzeń domenowych i operacyjnych jako obowiązkowy kontrakt:
  - `MEDICAL_TEXT_EDITED`, `DOCUMENT_PUBLISHED`, `DOCUMENT_REPUBLISHED`, `RETENTION_FILE_DELETED`,
  - spójne metadane (`actor`, `timestamp`, `entity_id`, `reason`) i testy integralności logowania.

## Etap 7: Hardening i gotowość produkcyjna

- Security hardening: env-only secrets, secure cookies/HTTPS/HSTS (prod), minimalizacja PII w logach.
- Auth/session hardening (US-001):
  - timeout sesji po bezczynności, rotacja/odświeżanie sesji i właściwe ustawienia cookie (`Secure`, `HttpOnly`, `SameSite`),
  - testy negatywne dla wygasłych sesji i niedozwolonego dostępu między rolami.
- Testy E2E krytycznych flow:
  - manual intake -> publish -> outbox complete,
  - republish,
  - import z błędnymi wierszami,
  - token latest-wins.
- Performance sanity:
  - p95 ładowania formularza,
  - p95 czasu ścieżki publish->HiDrive->SMS.
- DoD release:
  - migracje odtwarzalne,
  - test suite green,
  - alerty i dashboardy aktywne,
  - runbooki dostępne dla dyżuru.

## Kluczowe pliki do utworzenia/rozszerzenia

- Konfiguracja i entrypointy:
  - `[cogitomedica/settings.py](C:/Users/piotr/Programming/cogitomedica/cogitomedica/settings.py)`
  - `[cogitomedica/urls.py](C:/Users/piotr/Programming/cogitomedica/cogitomedica/urls.py)`
- Specyfikacje i kontrakty:
  - `[/.ai/prd.md](C:/Users/piotr/Programming/cogitomedica/.ai/prd.md)`
  - `[/.ai/db-plan.md](C:/Users/piotr/Programming/cogitomedica/.ai/db-plan.md)`
- Nowe moduły aplikacyjne (do utworzenia):
  - `apps/users/`*, `apps/reception/`*, `apps/intake/*`, `apps/medical/*`, `apps/outbox/*`, `apps/integrations/*`, `apps/operations/*`.

## Proponowana kolejność realizacji (sprintowo)

- Sprint 0: Etap 1 + skeleton Etapu 2.
- Sprint 1: dokończenie Etapu 2 + Etap 3 (MVP recepcja/tablet).
- Sprint 2: Etap 4 + core Etapu 5 (publish pipeline na mockach).
- Sprint 3: Etap 5 (HiDrive API + import Faza 3) + Etap 6.
- Sprint 4: Etap 7 + stabilizacja + release readiness.

