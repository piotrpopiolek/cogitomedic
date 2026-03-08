---
name: Uproszczenie Patient
overview: Usunięcie statusów/alertów tożsamości i pól źródła z modelu `Patient`, likwidacja flow merge oraz przejście na złożoną unikalność pacjenta przy zachowaniu opcjonalnego, nadal unikalnego `doctolib_patient_id`. Plan obejmuje model Django, migracje bazy, API/OpenAPI, admin, testy, seedy i dokumentację projektową.
todos:
  - id: map-schema-change
    content: Zaprojektować końcowy kształt modelu Patient i kontraktów API po usunięciu statusów, alertów, external_source i merge.
    status: completed
  - id: prepare-db-migration
    content: "Przygotować plan migracji DB: usunięcie kolumn/constraintów oraz dodanie złożonej unikalności pacjenta z kontrolą duplikatów danych."
    status: completed
  - id: update-runtime-code
    content: Zaktualizować model, serwisy, admin, widoki i OpenAPI tak, aby nie używały TEMPORARY/CONFIRMED, alertów ani merge.
    status: completed
  - id: refresh-tests-docs
    content: Zaktualizować testy, seedy i dokumentację, aby odzwierciedlały nową semantykę Patient.
    status: completed
isProject: false
---

# Plan uproszczenia modelu Patient

## Zakres zmiany

- Uprościć model `Patient` w [C:\Users\piotr\Programming\cogitomedica\apps\reception\models.py](C:\Users\piotr\Programming\cogitomedica\apps\reception\models.py):
  - zostawić `doctolib_patient_id` jako pole opcjonalne i nadal unikalne,
  - usunąć `identity_status`, `identity_alert_created_at`, `identity_resolution_due_at`, `external_source`, `external_source_id`,
  - dodać nową regułę unikalności pacjenta: `(first_name, last_name, phone, date_of_birth)`.
- Usunąć cały flow merge pacjentów oparty o `TEMPORARY/CONFIRMED`:
  - endpoint `POST /patients/{id}/merge`,
  - serwis `merge_temporary_patient_into_confirmed()` i wyjątki z nim związane w [C:\Users\piotr\Programming\cogitomedica\apps\reception\services.py](C:\Users\piotr\Programming\cogitomedica\apps\reception\services.py),
  - odpowiednie wpisy w OpenAPI i dokumentacji.

## Kod aplikacji

- Przebudować model i logikę zapisu pacjenta w [C:\Users\piotr\Programming\cogitomedica\apps\reception\models.py](C:\Users\piotr\Programming\cogitomedica\apps\reception\models.py):
  - usunąć `PatientIdentityStatus`, `PatientExternalSource`, indeks po `identity_status`, constrainty `patient_external_unique`, `patient_identity_status_valid`, `patient_temp_identity_requires_alert`, `patient_identity_due_after_alert`,
  - usunąć override `save()` wyliczający status i daty alertów,
  - dodać `UniqueConstraint` dla `first_name`, `last_name`, `phone`, `date_of_birth`.
- Uprościć serwis tworzenia/aktualizacji pacjenta w [C:\Users\piotr\Programming\cogitomedica\apps\reception\services.py](C:\Users\piotr\Programming\cogitomedica\apps\reception\services.py):
  - `create_or_update_patient_manual()` ma już tylko zapisywać dane pacjenta i `doctolib_patient_id`, bez logiki `TEMPORARY`, alertów i ich domykania,
  - usunąć `_build_patient_identity_alert_window()`, `MergedPatientsResult`, `merge_temporary_patient_into_confirmed()`, `SourceNotTemporaryError`, `TargetNotConfirmedError`, `InvalidSourceActionError` jeśli po usunięciu merge nie będą już potrzebne.
- Uprościć admin w [C:\Users\piotr\Programming\cogitomedica\apps\reception\admin.py](C:\Users\piotr\Programming\cogitomedica\apps\reception\admin.py):
  - usunąć `PatientAdminForm` i helper `_ensure_patient_temp_identity_alert()` jeśli po zmianie nie będą nic wnosiły,
  - z `list_display`, `list_filter`, `search_fields` usunąć zależności od `identity_status` i `external_source`,
  - usunąć audit `PATIENT_IDENTITY_ALERT_SET`, bo alerty przestają istnieć.
- Zaktualizować ścieżki API w [C:\Users\piotr\Programming\cogitomedica\apps\reception\api_views_split\patients.py](C:\Users\piotr\Programming\cogitomedica\apps\reception\api_views_split\patients.py):
  - `_serialize_patient()` ma przestać zwracać usuwane pola,
  - `GET /patients` ma przestać przyjmować filtr `identity_status`,
  - `POST /patients` i `PATCH /patients/{id}` mają przestać przyjmować/zwracać pola alertów i `external_source*`,
  - usunąć widok `patient_merge_view` i powiązane importy,
  - zachować obsługę konfliktów unikalności, ale zaktualizować oczekiwane źródła konfliktu: nowa unikalność złożona plus nadal unikalny `doctolib_patient_id`.
- Zaktualizować request models w [C:\Users\piotr\Programming\cogitomedica\apps\reception\api_schemas.py](C:\Users\piotr\Programming\cogitomedica\apps\reception\api_schemas.py):
  - usunąć `external_source`, `external_source_id`, `MergePatientRequest`,
  - zostawić `doctolib_patient_id` jako opcjonalne,
  - uprościć kontrakty create/update pacjenta.
- Zaktualizować OpenAPI w [C:\Users\piotr\Programming\cogitomedica\cogitomedica\openapi_extension.py](C:\Users\piotr\Programming\cogitomedica\cogitomedica\openapi_extension.py):
  - usunąć query param `identity_status` oraz opis/ścieżkę merge,
  - odświeżyć opisy pacjenta tak, by nie obiecywały `identity_alert`, `TEMPORARY/CONFIRMED` ani `external_source*`.

## Baza danych i migracje

- Przygotować nową migrację w `apps/reception/migrations/` usuwającą kolumny `identity_status`, `identity_alert_created_at`, `identity_resolution_due_at`, `external_source`, `external_source_id` oraz stare constrainty/indeksy.
- W tej samej migracji dodać nowy constraint lub unikalny indeks dla `(first_name, last_name, phone, date_of_birth)` oraz zachować unikalność `doctolib_patient_id`.
- Przed dodaniem nowej unikalności uwzględnić ryzyko danych historycznych:
  - sprawdzić, czy istnieją duplikaty pacjentów po `(first_name, last_name, phone, date_of_birth)`,
  - jeśli tak, przewidzieć w planie wdrożeniowym preflight check albo osobny cleanup danych przed migracją produkcyjną.
- Usunąć lub zrewidować stare migracje seedujące i tłumaczeniowe, które odnoszą się do usuwanych pól, w szczególności:
  - [C:\Users\piotr\Programming\cogitomedica\apps\core\migrations\0008_seed_all_fields_and_login_translations.py](C:\Users\piotr\Programming\cogitomedica\apps\core\migrations\0008_seed_all_fields_and_login_translations.py),
  - [C:\Users\piotr\Programming\cogitomedica\apps\core\migrations\0009_update_real_field_translations.py](C:\Users\piotr\Programming\cogitomedica\apps\core\migrations\0009_update_real_field_translations.py),
  - seedy recepcyjne używające `doctolib_patient_id` jako lookup key pozostają, ale trzeba sprawdzić, czy żaden nie opiera się już na usuwanych polach.

## Skutki uboczne i zależności

- Zachować kompatybilność ścieżek archiwizacji w [C:\Users\piotr\Programming\cogitomedica\apps\outbox\hidrive_paths.py](C:\Users\piotr\Programming\cogitomedica\apps\outbox\hidrive_paths.py):
  - obecna logika folderu po `doctolib_patient_id` lub `patient.id` może zostać bez zmian, bo `doctolib_patient_id` zostaje.
- Zrewidować miejsca, gdzie testy lub fixture setup zakładają tymczasowość pacjenta albo zwracane pola API, zwłaszcza w:
  - [C:\Users\piotr\Programming\cogitomedica\apps\reception\tests.py](C:\Users\piotr\Programming\cogitomedica\apps\reception\tests.py),
  - [C:\Users\piotr\Programming\cogitomedica\apps\reception\api_tests.py](C:\Users\piotr\Programming\cogitomedica\apps\reception\api_tests.py),
  - oraz testach innych modułów, które tylko tworzą pacjenta z `doctolib_patient_id` jako fixture.
- Sprawdzić, czy gdziekolwiek komunikaty biznesowe lub dokumentacja operacyjna nadal odwołują się do `TEMPORARY`, `CONFIRMED`, `identity_alert_closed`, `SOURCE_NOT_TEMPORARY`, `TARGET_NOT_CONFIRMED`.

## Testy i weryfikacja

- Zastąpić testy statusów/alertów testami nowej unikalności złożonej i nadal unikalnego `doctolib_patient_id`.
- Usunąć testy merge oraz odpowiednio uprościć testy API tworzenia/edycji pacjenta.
- Dodać testy negatywne dla konfliktu na `(first_name, last_name, phone, date_of_birth)` oraz osobno dla konfliktu `doctolib_patient_id`.
- Po wdrożeniu zmian uruchomić zestaw testów obejmujący `reception`, `intake`, `medical`, `outbox`, `operations`, bo wszystkie te obszary tworzą lub serializują `Patient`.

## Dokumentacja do aktualizacji

- Zaktualizować założenia w:
  - [C:\Users\piotr\Programming\cogitomedicaai\prd.md](C:\Users\piotr\Programming\cogitomedica.ai\prd.md),
  - [C:\Users\piotr\Programming\cogitomedicaai\db-plan.md](C:\Users\piotr\Programming\cogitomedica.ai\db-plan.md),
  - [C:\Users\piotr\Programming\cogitomedicaai\api-plan.md](C:\Users\piotr\Programming\cogitomedica.ai\api-plan.md),
  - [C:\Users\piotr\Programming\cogitomedicaai\api-plan-pl.md](C:\Users\piotr\Programming\cogitomedica.ai\api-plan-pl.md).
- Usunąć z dokumentów opis tymczasowej tożsamości, alertów administracyjnych i merge `TEMPORARY -> CONFIRMED`.
- Opisać nową regułę spójności: pacjent jest unikalny po `first_name + last_name + phone + date_of_birth`, a `doctolib_patient_id` pozostaje opcjonalnym, nadal unikalnym identyfikatorem pomocniczym.

