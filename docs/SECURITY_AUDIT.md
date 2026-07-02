# Audyt bezpieczeństwa – CogitoMedica

Data: 2025-03 (aktualizacja: 2026-07 — rola `Accounting`, raport księgowości admin HTML)  
Zakres: Czy pacjent może uzyskać dostęp do panelu lekarza, administracji lub rejestracji; luki w systemie.

## Podsumowanie

- **Panel lekarza (`/doctor/`)** (HTML) oraz **REST API v1** pod ścieżkami `medical-documents` / powiązanych: wymagają logowania i roli **DOCTOR**, **ADMIN** albo **MANAGER** (dekoratory `require_user_role` w `apps.medical.api_views` — spójnie z serwisem i panelem HTML).
- **Administracja (`/admin/`)**: chroniona – Django admin wymaga `is_staff`; widoki własne (reception-dashboard, intake-documents) używają `@staff_member_required` i roli RECEPTION/ADMIN.
- **Rejestracja / tablet (`/tablet/`)**: chronione – wymaga roli TABLET, RECEPTION lub ADMIN.
- **API v1**: endpointy wewnętrzne wymagają uwierzytelnienia i odpowiedniej roli (require_auth + require_user_role). Portal wyników pacjenta (request-otp, verify-otp, documents, download) jest oddzielony – sesja pacjenta (patient_results_patient_id) nie daje dostępu do żadnego panelu staff.

## Wprowadzone poprawki

### 1. Endpoint health (`/api/v1/observability/health`)

- **Było**: Dla każdego (również anonimowego) zwracana była pełna odpowiedź z `checks: { db, hidrive, sms }`, co ujawniało stan wewnętrznych zależności.
- **Jest**: Dla anonimowego użytkownika zwracany jest tylko `{"status": "ok"}` lub `{"status": "error"}` (bez `checks`). Kod HTTP 200/503 nadal odzwierciedla stan bazy (dla load balancera/Docker). Pełna odpowiedź z `checks` tylko dla: Bearer `PROMETHEUS_METRICS_TOKEN` lub zalogowanego użytkownika z rolą ADMIN.

### 2. Dokumentacja API (`/api/schema/`, `/api/docs/swagger/`, `/api/docs/redoc/`)

- **Było**: Dostępna bez logowania – możliwość enumeracji endpointów i parametrów.
- **Jest**: Widoki opakowane w `staff_member_required` – dostęp tylko dla użytkowników z `is_staff=True` (przekierowanie do logowania admina).

### 3. Metryki (`/api/v1/observability/metrics`)

- Bez zmian w zachowaniu: nadal wymagany Bearer token lub sesja ADMIN (już wcześniej chronione).

## Integralność danych – blokada edycji Befund

- Dla dokumentów w stanie **DRAFT** stosowana jest **aplikacyjna blokada** na rekordzie `medical_document` (`locked_by_user`, `locked_at`), aby ograniczyć równoległe nadpisywanie szkicu przez dwóch lekarzy. Blokada wygasa po **6 godzinach** (bez osobnego schedulera) i jest zwalniana przy **publikacji** oraz **best-effort** przy zamknięciu karty (żądanie `POST /api/v1/medical-documents/{id}/unlock`). **Admin** i **Manager** mogą zapisywać szkic mimo blokady innego użytkownika (PUT …/draft); **publikacja** Befund (`POST …/publish`) jest wyłącznie dla roli **DOCTOR**.

## Weryfikacja zabezpieczeń

### Panel lekarza (`cogitomedica/doctor_views.py`)

- Logowanie: `doctor_login_view` – użytkownicy z `user.is_doctor`, `user.is_admin_role` lub `user.is_manager` mogą się zalogować (kolejka Befund w `apps.medical.services` traktuje admina i managera jak pełen nadzór przy dostępie do listy / dokumentu w panelu HTML).
- Wszystkie widoki chronione: `@login_required(login_url="doctor-login")` oraz na początku widoku `if not _doctor_role_ok(request): return redirect("doctor-login")`.
- **RBAC kolejki lekarza:** wspólny dostęp do pracy roboczej (brak dokumentu, `DRAFT`, rewizja `has_pending_revision`); opublikowany wynik bez rewizji widoczny tylko dla lekarza, który go opublikował (`published_by_user` na wersji przy `published_version_no`). Próba dostępu do cudzego UUID → **404** (nie 403), żeby nie ujawniać istnienia rekordu.
- **Audyt odmowy:** `check_doctor_document_access` / `check_doctor_queue_entry_access` zapisują `MEDICAL_DOCUMENT_ACCESS_DENIED` / `QUEUE_ENTRY_ACCESS_DENIED` w `AuditEvent` przed zwróceniem 404 (metadata m.in. `denial_reason`, opcjonalnie `client_ip`).
- **Publikacja Befund:** `POST …/medical-documents/{id}/publish` — wyłącznie rola **DOCTOR** (admin/manager nie publikują w imieniu lekarza).
- Pacjent (model `Patient`) nie ma konta w `StaffUser` – nie może zalogować się do panelu lekarza.

### Tablet (`cogitomedica/tablet_views.py`)

- Logowanie: tylko `user.is_tablet`, `user.is_reception` lub `user.is_admin_role`.
- Widoki chronione: `@login_required(login_url="tablet:login")` oraz `_tablet_role_ok(request)`.
- **Scope kolejek:** jeśli w sesji jest `tablet_device_id` (ustawiane przy logowaniu z `android_id`), zakres kolejek wynika z przypisania urządzenia do placówki (`TabletDevice.clinic_site_id`). Tablet widzi wyłącznie kolejki swojej placówki; bez przypisania – pusta lista i komunikat. Przypisania dokonuje się w panelu admin (TabletDevice) lub przez API PATCH `/api/v1/tablet-devices/{id}`.

### Admin i widoki pod `/admin/`

- `path("admin/", admin.site.urls)` – standardowa ochrona Django (wymaga `is_staff`).
- `reception_dashboard_view`: `@staff_member_required`.
- `intake_documents_list_view`, `intake_document_detail_view`: `@staff_member_required` oraz `_is_reception_or_admin(request)` (redirect do admin:index przy braku roli).
- **Raport księgowości** (`accounting_report_dashboard_view`, `accounting_report_export_csv_view`, `accounting_report_export_xlsx_view` w `apps/operations/views.py`): `@staff_member_required` oraz `accounting_report_access_ok` — dozwolone role **ACCOUNTING**, **ADMIN**, **MANAGER**; inne role staff → **403**. Grupa Accounting **nie** ma uprawnień Django ModelAdmin (migracja `users/0020`); konto Accounting nie otwiera list pacjentów (`admin:reception_patient_changelist` → 403). Zakres placówek: Accounting/Admin — wszystkie; Manager — `get_scoped_clinic_site_ids`. Eksport zapisuje audyt `ACCOUNTING_REPORT_EXPORT` (metadane bez PHI).

### API v1 (`cogitomedica/api_urls.py`, aplikacje)

- Endpointy staff: używają `@require_auth` i `require_user_role(request, allowed_roles={...})` (DOCTOR, ADMIN, RECEPTION, TABLET, ewent. **MANAGER** przy operacjach recepcji/importu/monitoringu — w zależności od endpointu).
- Portal wyników pacjenta:
  - `patient-results/request-otp`, `verify-otp`: publiczne z rozsądnym rate limitem i CAPTCHA (Turnstile).
  - `patient-results/documents`, `patient-results/documents/<id>/download`: dostęp tylko gdy w sesji jest `patient_results_patient_id` (ustawiane po poprawnym verify_otp). Pobieranie PDF sprawdza, że `version_id` należy do tego pacjenta (`get_patient_pdf_version(version_id, patient_id)`).

### Sesje

- Sesja pacjenta (portal wyników): tylko `patient_results_patient_id`. Brak `request.user` (AnonymousUser).
- Sesja staff: `request.user` z rolami (groups). Oddzielny flow logowania (admin, doctor, tablet).
- Ustawienia: `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, w prod `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.

## Zalecenia dla Dockera / produkcji

1. **ALLOWED_HOSTS** – w produkcji ustawić jawnie (np. w .env), bez polegania na domyślnych wartości dev.
2. **PROMETHEUS_METRICS_TOKEN** – ustawić w środowisku dla health/metrics (np. w docker-compose), żeby monitoring mógł odpytywać bez sesji użytkownika.
3. **Rate limiting** – request-otp i verify-otp mają limit (ip, 10/m i 15/m); auth/login 5/m. RatelimitMiddleware włączone.
4. **CORS** – `CORS_ALLOWED_ORIGINS` w prod ustawić tylko na zaufane fronty; `CORS_ALLOW_CREDENTIALS = True` – zachować ostrożność przy dodawaniu nowych originów.

## Brak wykrytych luk

- Pacjent nie może wejść na panel lekarza, admina ani rejestracji/tabletu (brak konta staff, osobne ścieżki logowania i sprawdzanie ról).
- Konto **Accounting** ma dostęp wyłącznie do raportu księgowości w adminie — nie do pacjentów ani API medycznego.
- API staff jest chronione rolami; dokumenty pacjenta w portalu wyników są filtrowane po `patient_id` z sesji.
- Health nie ujawnia już wewnętrznych checks anonimowo; docs/schema tylko dla staff.
