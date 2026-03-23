# Przegląd kodu — Cogitomedica

**Data:** 2026-03-23  
**Zakres:** repozytorium Django (`apps/`, `cogitomedica/`, `templates/`, `static/`), zasady z `.cursor/rules/backend-django-cogitomedica.mdc`.

## Metodologia i pokrycie

| Kategoria | Liczba plików (szac.) | Status przeglądu |
|-----------|----------------------:|------------------|
| Python — migracje Django (`**/migrations/*.py`) | ~110 | Przegląd **zbiorczy**: założenie zgodności z konwencją Django; seed/data migrations nie analizowane linia po linii. |
| Python — kod aplikacji (bez `migrations/`) | ~160 | **100% plików zmapowanych** do pakietów; **szczegółowy przegląd** warstwy: `settings`, routing, `api_views`, `services`, integracje, modele kluczowe, HTML widoki (`doctor`, `tablet`), middleware, `core/api_utils`. Pozostałe moduły (m.in. `*_tests.py`, komendy `management`, duplikaty ścieżek) — **weryfikacja skrótowa** (spójność z architekturą + grep pod wzorce ryzyka). |
| Szablony HTML / statyczne JS/CSS | ~60 | **Próbkowanie** szablonów odpowiedzialnych za auth, PDF, panel lekarza/tablet; brak audytu każdego szablonu admin/Unfold pod XSS. |
| **Łącznie plików `.py` w repo** | ~270 | **Objętość świadoma:** całe drzewo modułów; **głębokie czytanie** szacowane na **~35–45%** linii kodu Python (koncentracja na ścieżkach krytycznych). |

**Uczciwy % „całości”:** przy definicji „100% = każda linia każdego pliku” — **nieukończone**. Przy definicji „100% = brak nieznanych obszarów repo + decyzje dla każdego pakietu” — **ukończone** dla struktury backendu; **ustalenia akcyjne** dotyczą wyłącznie miejsc zweryfikowanych w kodzie (poniżej).

---

## Rejestr plików — warstwa krytyczna (przegląd szczegółowy)

Następujące pliki zostały **przeczytane i ocenione** pod kątem logiki, bezpieczeństwa i zgodności z regułami projektu:

- `cogitomedica/settings.py`
- `cogitomedica/urls.py`, `cogitomedica/api_urls.py`
- `cogitomedica/doctor_views.py`, `cogitomedica/tablet_views.py`
- `apps/core/api_utils.py`, `apps/core/middleware.py`
- `apps/users/api_views.py` (fragment), `apps/users/models.py`
- `apps/operations/api_views.py`
- `apps/outbox/api_views.py`, `apps/outbox/services.py` (fragment)
- `apps/medical/services.py` (fragment — publikacja, draft, kontrola dostępu)
- `apps/intake/api_views.py` (fragment), `apps/intake/services.py` (`get_intake_form_context` i kontekst)
- `apps/patient_results/api_views.py` (fragment), `apps/patient_results/services.py` (fragment — OTP)
- `apps/reception/xlsx_import.py` (nagłówek, walidacja — fragment)

Pozostałe pliki `.py` w `apps/*` i `cogitomedica/*` są **uwzględnione w przeglądzie repozytorium** jako część tej samej bazy kodu; nie każdy ma osobny opis w tym dokumencie.

---

## Ustalenia wymagające działania (tylko istotne)

### 1. [Bezpieczeństwo — wysokie] Brak scope’u placówki (`clinic_site`) przy dostępie do intake (API + tablet HTML)

**Problem:** `get_intake_form_context()` (`apps/intake/services.py`) ładuje formularz po samym `intake_form_id`, z opcjonalnym `tablet_restrict_to_today` dla roli TABLET. **Nie weryfikuje**, czy kolejka/formularz należy do placówki przypisanej do użytkownika (`get_scoped_clinic_site_ids`) ani czy urządzenie tabletu (`get_tablet_scope_clinic_site_ids`) obejmuje ten `clinic_site_id`.

**Skutek:** Użytkownik RECEPTION z kontem (lub TABLET znający UUID) może teoretycznie odczytać/modyfikować dane intake innej placówki, jeśli zna lub wycieknie `intake_form_id`. To **IDOR / naruszenie izolacji danych** między placówkami. Moduły `reception` (kolejki, pacjenci) i `intake/document_services` stosują `get_scoped_clinic_site_ids` — **intake API jest niespójny** z tym modelem.

**Sugestia:** Przekazywać do serwisu (lub warstwy wywołującej) listę dozwolonych `clinic_site_id` (albo `None` tylko dla ADMIN); po załadowaniu `PatientIntakeForm` porównać `queue_entry.daily_queue.clinic_site_id` i przy braku zgodności zwracać 404/`ObjectDoesNotExist`. To samo dla wszystkich mutacji (PATCH/POST) na tym samym `intake_form_id` w `apps/intake/api_views.py`.

---

### 2. [Bezpieczeństwo — średnie] Walidatory haseł Django wyłączone

**Problem:** W `cogitomedica/settings.py` sekcja `AUTH_PASSWORD_VALIDATORS` jest w całości zakomentowana.

**Skutek:** Brak wymuszenia długości/złożoności haseł dla kont staff — słabe hasła w produkcji.

**Sugestia:** Włączyć standardowy zestaw walidatorów Django (lub dostosowany) dla środowiska produkcyjnego.

---

### 3. [Bezpieczeństwo — średnie] `PATIENT_RESULTS_OTP_PEPPER` domyślnie pusty

**Problem:** `apps/patient_results/services.py` — `_hash_otp` użyje pustego peppera, jeśli zmienna środowiskowa nie jest ustawiona.

**Skutek:** Hashe OTP są słabsze wobec ataków offline na wyciek bazy.

**Sugestia:** W `ENVIRONMENT == "prod"` wymuszać niepusty `PATIENT_RESULTS_OTP_PEPPER` (podobnie jak `SECRET_KEY` / HiDrive), lub odrzucać start bez skonfigurowanego peppera.

---

### 4. [Wydajność / zgodność z architekturą — średnie] Ciężkie przetwarzanie outbox w żądaniu HTTP

**Problem:** `operations_outbox_process_view` (`apps/outbox/api_views.py`) wywołuje `process_outbox_events()` **synchronicznie** w odpowiedzi HTTP (generacja PDF, upload HiDrive, SMS w zależności od zdarzeń).

**Skutek:** Ryzyko timeoutów proxy/workera, blokowania wątków i naruszenia zasady projektu: *„Operacje I/O-bound nie mogą blokować cyklu request/response; deleguj do Django 6 Tasks”*.

**Sugestia:** Enqueue pojedynczego zadania tła (Django Tasks) z limitem batcha zamiast wykonywać cały batch w widoku; HTTP zwraca `202` po **zakolejkowaniu**, z identyfikatorem zadania lub tylko potwierdzeniem (zgodnie z istniejącym wzorcem operacji).

---

### 5. [Wydajność / odporność — niskie–średnie] Brak limitu rozmiaru body w `read_json_body`

**Problem:** `apps/core/api_utils.py` — `request.body.decode()` bez limitu rozmiaru.

**Skutek:** Potencjalne zużycie pamięci przy złośliwie dużym JSON (DoS).

**Sugestia:** Odrzucać żądania powyżej rozsądnego progu (np. 256 KB–1 MB) przed `decode`, lub użyć strumienia / `CONTENT_LENGTH` z walidacją.

---

### 6. [Utrzymanie / higiena konfiguracji — niskie] `CSRF_TRUSTED_ORIGINS` i tunel dev

**Problem:** W `settings.py` na stałe wpisany host ngrok; middleware dodaje dynamicznie origin dla `trycloudflare.com`.

**Skutek:** Ryzyko commitowania środowiskowych URL do repo; mutacja `settings.CSRF_TRUSTED_ORIGINS` w runtime może być myląca przy wielu workerach (rzadkie edge case).

**Sugestia:** Przenieść dev-tunele wyłącznie do `.env` / listy z zmiennej środowiskowej; unikać hardcodów domen w repozytorium.

---

## Pozytywne obserwacje (krótko)

- **Publikacja medyczna:** unikalność `publish_request_id` i obsługa konfliktów idempotencji w `apps/medical/services.py` są spójne z wymaganiami domenowymi.
- **Outbox:** `process_outbox_events` używa transakcji i `select_for_update(skip_locked=True)` — sensowny wzorzec konkurencji.
- **Uwierzytelnianie API:** `auth_login_view` ma rate limit; **Sentry** filtruje nagłówki wrażliwe.
- **Metryki:** `observability_metrics_view` wymaga Bearer tokena lub roli ADMIN — dobra separacja od publicznego health.
- **Portal pacjenta:** OTP z rate limitami i anti-enumeration (`request_otp`) — dobry kierunek.

---

## Testy

W repo występują rozbudowane pliki `api_tests.py` / `tests.py` w wielu aplikacjach — **nie przeprowadzono** w tej sesji oceny pokrycia ani uruchamiania pytest. **Sugestia:** Dodać testy regresyjne dla scope placówki przy intake po wdrożeniu poprawki z ustalenia #1.

---

## Podsumowanie % (jasne definicje)

| Metryka | Wartość |
|--------|--------|
| Pliki `.py` zidentyfikowane w repo | ~270 |
| Kod aplikacji poza migracjami — uwzględnione w przeglądzie strukturalnym | ~160 plików (**100%** nazw pakietów/plików w mapie) |
| Migracje | ~110 plików — **przegląd zbiorczy**, nie 100% linii |
| Szablony / statyczne | ~60 — **próbkowanie** |
| **Szacunek linii kodu Python przeczytanych z uwagą** | **~35–45%** (priorytet: ścieżki API, serwisy, settings) |

---

## Iteracja 1 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23  
**Zakres:** punkt startowy systematycznego pokrycia 100% plików źródłowych; **25 plików na iterację** z notatkami poniżej.

### Środowisko Docker (repo)

- `docker-compose.yml`: serwis `web` uruchamia `python manage.py runserver 0.0.0.0:8000` — typowy **dev**. `OTEL_EXPORTER_OTLP_ENDPOINT` wskazuje na `otel-collector:4318` (sieć compose); zgodne z komentarzem w `cogitomedica/telemetry.py`.
- `Dockerfile`: Python 3.13-slim, zależności systemowe pod WeasyPrint/cairo — spójne z generowaniem PDF.
- **Uwaga operacyjna:** domyślne hasło Postgresa w compose (`1234` jako fallback) jest wyłącznie do lokalnego dev — w produkcji musi pochodzić wyłącznie z `.env` / sekretów.

### Lista plików — iteracja 1 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `manage.py` | Wywołuje `setup_telemetry()` przed `execute_from_command_line`; błędy OTEL połykane (`except Exception: pass`) — start aplikacji nie padnie, ale brak logów przy złej konfiguracji. |
| 2 | `passenger_wsgi.py` | **Hosting (nie ścieżka Docker z compose):** `get_wsgi_application()` wołane **przy każdym żądaniu** — kosztowne; standardowo powinno być jedno `application = get_wsgi_application()` na poziomie modułu. Transformacja `PATH_INFO` (utf-8 → iso-8859-1) jest nietypowa — ryzyko złych ścieżek przy niektórych znakach. |
| 3 | `cogitomedica/wsgi.py` | `setup_telemetry()` + `application` — poprawny wzorzec dla WSGI (Gunicorn/uWSGI). |
| 4 | `cogitomedica/asgi.py` | **Brak** `setup_telemetry()` — przy wdrożeniu na ASGI (uvicorn/daphne) ślady OTEL z instrumentacji Django mogą nie wystartować tak jak przy WSGI/manage. |
| 5 | `cogitomedica/telemetry.py` | OTLP HTTP, BatchSpanProcessor, instrumentacje Django/requests/psycopg — zgodne z docker-compose (`otel-collector`). |
| 6 | `cogitomedica/admin_callbacks.py` | Callbacki Unfold — tylko etykieta środowiska; OK. |
| 7 | `cogitomedica/doctor_urls.py` | Routing panelu lekarza; bez dodatkowej ochrony poza widokami — OK. |
| 8 | `cogitomedica/tablet_urls.py` | `app_name = "tablet"` — spójne z namespace w szablonach. |
| 9 | `cogitomedica/openapi_schemas.py` (wstęp + konwersja Pydantic) | Konwersja `$defs` → `components`; testy w `cogitomedica/tests.py` pokrywają regresje refów. |
| 10 | `cogitomedica/tests.py` | Testy schematu OpenAPI — wartościowe dla kontraktów API. |
| 11 | `cogitomedica/api_tests.py` | Dokumentacja API chroniona `staff` — zgodne z `urls.py`. |
| 12 | `apps/core/views.py` | `ratelimited_view` — JSON 429; OK dla API. |
| 13 | `apps/core/exceptions.py` | Wyjątki domenowe — czytelny podział. |
| 14 | `apps/core/models.py` | `TranslationValue.clean`: bleach + walidacja placeholderów — dobry poziom sanityzacji treści admina. |
| 15 | `apps/core/signals.py` | `bump_translation_version` przy save/delete — spójne z cache invalidation. |
| 16 | `apps/core/context_processors.py` | Tłumaczenia przycisków admina — tylko dla `path` zaczynającego się od `/admin/`. |
| 17 | `apps/core/http_utils.py` | `X-Forwarded-For` — pierwszy hop; **za reverse proxy w Dockerze** ustaw poprawnie nagłówek na brzegu (inaczej możliwe fałszowanie IP w audit, jeśli port aplikacji jest wystawiony bez proxy). |
| 18 | `apps/core/translation_service.py` (fragment) | Cache `i18n:data:…`, `bump_translation_version` w transakcji — OK. |
| 19 | `apps/core/apps.py` | Import `signals` w `ready()` — standard. |
| 20 | `apps/users/auth_backends.py` | Rola ADMIN → `has_perm`/`has_module_perms` zawsze True — świadoma eskalacja uprawnień Django admin; wymaga poprawnych grup w DB. |
| 21 | `apps/users/services.py` | **Patrz ustalenie #7.** |
| 22 | `apps/users/forms.py` | Tworzenie użytkownika — pola minimalne; reszta w adminie. |
| 23 | `apps/users/admin.py` | Filtrowanie listy po `role` w GET; `save_model` wymusza `is_staff` dla admina — sensowne. |
| 24 | `apps/users/apps.py` | Pusty `ready` — OK. |
| 25 | `apps/__init__.py` | Tylko docstring pakietu. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w tej iteracji | **25** |
| Szacowana liczba wszystkich `*.py` w repo | **~270** |
| **Udział tej iteracji w plikach .py** | **~9,3%** |
| Skumulowanie po iteracji 1 | **25 / ~270** |

Szablony HTML / statyczne — **nie** w iteracji 1; zaplanować po dokończeniu plików `.py` lub naprzemiennie wg ustalenia zespołu.

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 1)

### 7. [Logika / bezpieczeństwo — średnie] `create_staff_user` / `update_staff_user` bez gwarancji przypisania grupy

**Problem:** W `apps/users/services.py`, jeśli `Group` o nazwie `Doctor`, `Reception`, itd. **nie istnieje** w bazie (`Group.objects.filter(name=group_name).first()` zwraca `None`), użytkownik jest tworzony lub aktualizowany **bez żadnej roli** — brak wyjątku, brak roli w UI/API.

**Sugestia:** Po migracji `0006_create_roles_groups` grupy powinny istnieć; w kodzie: **`get_or_create` grupy albo `raise DomainError`** gdy grupa nie istnieje, żeby nie tworzyć „pustych” kont.

---

### 8. [Wydajność — średnie, jeśli używany] `passenger_wsgi.py` woła `get_wsgi_application()` w każdym requeście

**Problem:** Podwójna inicjalizacja Django na każde żądanie.

**Sugestia:** Refactor do wzorca jak w `cogitomedica/wsgi.py` (jeden modułowy `application`). W **Dockerze z `docker-compose`** ten plik zwykle **nie** jest używany — priorytet naprawy niski, chyba że produkcja = Passenger.

---

### 9. [Obserwowalność — niskie] Brak `setup_telemetry()` w `asgi.py`

**Problem:** Przejście na serwer ASGI bez zmiany entrypointu pozbawi aplikację automatycznej instrumentacji OTEL startującej z WSGI.

**Sugestia:** Dodać ten sam blok `try/setup_telemetry` co w `wsgi.py` przed `get_asgi_application()`, albo dokumentować, że produkcja musi ustawiać OTEL przez inny hook.

---

## Iteracja 2 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23

### Lista plików — iteracja 2 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `cogitomedica/openapi_extension.py` (wstęp + `NO_AUTH_OPERATIONS`, `COGITO_PATHS`) | Schemat OpenAPI budowany ręcznie; spójny z `api_urls`. **Uwaga:** `NO_AUTH_OPERATIONS` zawiera `GET /api/v1/observability/metrics`, podczas gdy `observability_metrics_view` wymaga Bearer `PROMETHEUS_METRICS_TOKEN` lub sesji ADMIN — **rozjazd dokumentacji Swagger z rzeczywistym auth** (patrz ustalenie #10). Opisy monitoringu (Grafana/Prometheus) wskazują `localhost` i w treści **login/hasło domyślne** — tylko dev, ale trafia do wygenerowanego JSON schematu. |
| 2 | `apps/core/translation_loader.py` (fragment) | Ładowanie JSON z `translation_data`; walidacja kategorii klucza; OK dla seedów. |
| 3 | `apps/integrations/hidrive/auth.py` | OAuth refresh w pamięci procesu; metryki Prometheus; obsługa błędów tokena — solidnie. |
| 4 | `apps/integrations/hidrive/client.py` | Upload z retry przy 401; mock adapter; ścieżki znormalizowane — OK. |
| 5 | `apps/integrations/sms/client.py` | Mock vs SMSAPI; `get_sms_adapter()` bez cache (świadomie „fresh after restart”) — OK. |
| 6 | `apps/intake/views.py` | Lista/szczegół dokumentów intake w admin HTML — **`get_scoped_clinic_site_ids` przez `list_intake_documents` / `check_intake_document_access`** — spójne z modelem izolacji (odróżnienie od surowego intake form API). |
| 7 | `apps/intake/document_views.py` | API JSON + PDF inline z `Cache-Control: no-store` — dobre dla danych wrażliwych. |
| 8 | `apps/intake/tasks.py` | `@task` Django → `process_intake_outbox_events` — zgodne z kierunkiem „ciężka praca poza requestem”. |
| 9 | `apps/intake/outbox_services.py` (fragment) | Ten sam wzorzec co outbox medyczny: `select_for_update`, kolejne kroki HiDrive — OK. |
| 10 | `apps/operations/services.py` | `create_audit_event` + `metadata._ref` dla compliance po `SET_NULL` — przemyślane. |
| 11 | `apps/operations/models.py` | `AuditEvent` + GIN na `metadata`; constrainty — OK pod kątem zapytań i JSON. |
| 12 | `apps/outbox/models.py` | Unikalność zdarzenia per typ i wersja; constrainty `aggregate_id` — spójne z PRD outbox. |
| 13 | `apps/outbox/tasks.py` | `process_outbox_events`, `run_retention_cleanup` jako taski — OK; **retention** ma stałe `older_than_days=30` w tasku — warto wiedzieć przy zmianie polityki. |
| 14 | `apps/outbox/hidrive_paths.py` | Sanitacja fragmentów folderu (usuwanie `/`, `\`); nazewnictwo pacjenta — rozsądne. |
| 15 | `apps/patient_results/models.py` | OTP session z constrainte `expires_at > created_at` — OK. |
| 16 | `apps/patient_results/views.py` | HTML portalu: sesja na telefon/DOB, potem OTP; **redirect** z `reverse('ergebnisse:…')` vs sama nazwa URL — w gałęzi `locale == "de"` używane `redirect("ergebnisse:otp")` itd. (Django rozwiązuje nazwę) — do weryfikacji testem E2E. |
| 17 | `apps/patient_results/document_services.py` | `get_patient_pdf_path`: **`path.resolve().is_relative_to(media_resolved)`** — ochrona przed path traversal poza `MEDIA_ROOT` — dobra. |
| 18 | `apps/reception/views.py` | Dashboard recepcji: **globalne** `failed_outbox` (ostatnie 20 bez filtra placówki) — patrz ustalenie #11. |
| 19 | `apps/reception/phone_utils.py` | `normalize_phone` — cyfry tylko, min. 7 — spójne z lookupami. |
| 20 | `apps/reception/tasks.py` | `run_daily_import` placeholder; `run_patient_xlsx_import` deleguje do `process_patient_xlsx_import_batch` — OK jako worker entrypoint. |
| 21 | `apps/integrations/__init__.py` | Docstring pakietu. |
| 22 | `apps/integrations/apps.py` | `IntegrationsConfig` — standard. |
| 23 | `apps/integrations/hidrive/__init__.py` | Pusty moduł pakietu. |
| 24 | `apps/integrations/sms/__init__.py` | Re-eksport `get_sms_adapter`, `SmsAdapter`. |
| 25 | `apps/patient_results/__init__.py` | Docstring pakietu portalu wyników. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 2 | **25** |
| **Skumulowanie** | **50 / ~270** (~**18,5%**) |

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 2)

### 10. [Dokumentacja API / niskie] `GET /observability/metrics` w OpenAPI bez zabezpieczenia, endpoint wymaga auth

**Problem:** W `cogitomedica/openapi_extension.py` zestaw `NO_AUTH_OPERATIONS` zawiera parę `(…/observability/metrics, get)`, więc Swagger może traktować metryki jako publiczne. Implementacja (`apps/operations/api_views.py`) zwraca **401** bez Bearer tokena lub roli ADMIN.

**Sugestia:** Usunąć metrics z `NO_AUTH_OPERATIONS` i dodać `security` (Bearer / session) w definicji operacji w `COGITO_PATHS`, zgodnie z rzeczywistością.

---

### 11. [Prywatność operacyjna / niskie] Dashboard recepcji — globalna lista błędów outbox

**Problem:** `apps/reception/views.py` — `failed_outbox` to ostatnie rekordy **bez filtrowania po `clinic_site`** / roli recepcji. Przy wielu placówkach użytkownik recepcji może zobaczyć identyfikatory/nagłówki błędów dotyczące innych placówek.

**Sugestia:** Ograniczyć zapytanie do eventów powiązanych z dokumentami/kolejkami w zakresie `get_scoped_clinic_site_ids(request.user)` (lub analogicznie przez join do `MedicalDocumentVersion` / kolejki), albo wyłączyć ten widget dla roli innej niż ADMIN.

---

*Koniec sekcji iteracji 2. Następna: iteracja 3 (kolejne 25 plików).*

---

## Iteracja 3 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23

### Lista plików — iteracja 3 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `apps/medical/constants.py` | Jedno źródło wyborów z `Literal` (Pydantic) + etykiety EN z `befund_text` — spójne z zasadą DRY/SRP. |
| 2 | `apps/medical/apps.py` | Standardowy `AppConfig`. |
| 3 | `apps/medical/api_schemas.py` | Pydantic: `MedicalPayloadMinimal` wymusza `schema_version`; pola `*_user_id` w body oznaczone jako ignorowane na rzecz sesji — dokumentować w kliencie, żeby nie polegać na body. |
| 4 | `apps/medical/widgets.py` | `LesionGroupFavoritesWidget`: JSON do HTML przez base64 — zmniejsza ryzyko XSS w atrybutach; fallback parsowania listy — OK. |
| 5 | `apps/medical/models.py` (fragment) | `MedicalDocument` / `MedicalDocumentVersion`: constrainty na publikację (`publish_request_id`, `publish_locale`, `published_at`) — zgodne z idempotencją i audytem. |
| 6 | `apps/medical/medical_payload_schemas.py` (fragment) | `MedicalPayloadV1` z `schema_version: Literal[1]`; walidacja pustych `lesions` vs `CONTROL_NEEDED` — logika kliniczna w warstwie schematu. |
| 7 | `apps/medical/pdf_builder.py` (fragment) | WeasyPrint + etykiety PDF z DB (`get_translation_map`); mapowanie kodów → klucze UI — czytelne. |
| 8 | `apps/medical/api_views.py` (fragment) | Lista/dokument medyczny: `require_user_role` DOCTOR/ADMIN; POST tworzenia dokumentu wywołuje `check_doctor_queue_entry_access` — spójne z HTML `doctor_views`. |
| 9 | `apps/medical/template_services.py` (fragment) | `list_templates` / `get_template`: filtrowanie po global / owner / `clinic_site`; **tylko ADMIN** może tworzyć szablony kliniczne (`clinic_site_id`) — jawnie zakodowane. |
| 10 | `apps/medical/befund_text.py` (fragment) | Słowniki DE/EN dla kodów Befund — źródło dla PDF i stałych. |
| 11 | `apps/medical/admin.py` (fragment) | Formularz szablonów z `LesionGroupFavoritesWidget` + walidacja Pydantic presetów w `clean_*` — obrona przed złym JSON w adminie. |
| 12 | `apps/reception/api_views.py` | Agregator re-eksportów z `api_views_split` — czytelny podział modułów. |
| 13 | `apps/reception/api_views_split/__init__.py` | Docstring pakietu. |
| 14 | `apps/reception/services.py` (fragment) | `create_clinic_site` / `update_clinic_site` z `select_for_update` i walidacją gabinetu vs placówka — poprawne granice domenowe. |
| 15 | `apps/reception/api_views_split/patients.py` (fragment) | `patients_view`: **`get_scoped_clinic_site_ids`** dla nie-ADMIN — filtrowanie pacjentów po powiązaniu z placówką lub kolejką — **wzorzec zgodny z PRD izolacji**. |
| 16 | `apps/reception/api_views_split/queues.py` (fragment) | `daily_queues_view`: TABLET tylko „dziś”; `get_tablet_scope_clinic_site_ids` + fallback na scope użytkownika; DOCTOR widzi kolejki z `assigned_doctor_id` — spójne. |
| 17 | `apps/reception/api_views_split/devices.py` | **GET `/tablet-devices`:** `TabletDevice.objects.all()` **bez** filtrowania po `get_scoped_clinic_site_ids` — recepcjonista może zobaczyć urządzenia wszystkich placówek (patrz ustalenie #12). |
| 18 | `apps/reception/api_views_split/imports.py` | `_visible_batches`: ADMIN widzi wszystko; inni tylko własne batche (`created_by_user`) — rozsądne. |
| 19 | `apps/reception/api_views_split/dictionaries.py` (fragment) | CRUD placówek/gabinetów; GET list zwykle ze scope (dalsza część pliku — spójna z `get_scoped_clinic_site_ids`). |
| 20 | `apps/reception/api_schemas.py` (fragment) | `PHONE_PATTERN` zgodny z modelem `Patient`; Pydantic dla kolejek/tabletów — OK. |
| 21 | `apps/reception/models.py` (fragment) | `Patient` + enumy kolejek/importów; `normalize_phone` używany w modelu/sygnale (w dalszej części pliku). |
| 22 | `apps/intake/api_schemas.py` | Walidacja body mapy (0–1), intake outbox `limit` 1–100 — spójne z `api_utils`. |
| 23 | `apps/intake/models.py` (fragment) | Definicje zgód, statusów PDF, outbox intake — bogate constrainty w DB. |
| 24 | `apps/intake/api_views.py` (fragment) | PUT consents / POST signature / PUT anamnesis — **brak dodatkowego scope placówki w widoku** (serwisy `save_*` po samym ID); **nadal dotyczy wcześniejsze ustalenie #1 (IDOR intake)**. |
| 25 | `apps/patient_results/api_views.py` | Publiczne OTP + rate limit; pobieranie PDF z `get_patient_pdf_path` (guard ścieżki); audit eventy — OK. Ryzyko: `UUID(result.patient_id or "")` przy `success` bez `patient_id` rzuci wyjątkiem — mało prawdopodobne przy poprawnym `verify_otp`. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 3 | **25** |
| **Skumulowanie** | **75 / ~270** (~**27,8%**) |

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 3)

### 12. [Bezpieczeństwo — średnie] Lista urządzeń tabletów bez scope placówki

**Problem:** `tablet_devices_view` (`apps/reception/api_views_split/devices.py`) dla GET buduje zapytanie `TabletDevice.objects.all()` z filtrami `is_active` / `search`, ale **nie ogranicza** do placówek przypisanych do użytkownika RECEPTION (ani nie ukrywa urządzeń innych placówek przed recepcją).

**Sugestia:** Dla roli RECEPTION (i opcjonalnie DOCTOR jeśli kiedyś mają dostęp) zastosować ten sam wzorzec co przy kolejkach: filtrowanie po `clinic_site_id__in=get_scoped_clinic_site_ids(user)`; ADMIN bez zmian.

---

*Koniec sekcji iteracji 3.*

---

## Iteracja 4 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23

### Lista plików — iteracja 4 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `apps/users/api_views.py` (fragment: staff list/create/detail, clinic_sites) | CRUD staff wyłącznie ADMIN; `create_staff_user` / `update_staff_user` — spójne z serwisem. **Uwaga na utrzymanie:** klasa Pydantic `UpdateStaffUserClinicSitesRequest` i import `BaseModel` dopiero **na końcu pliku** (po widokach) — narusza konwencję importów na górze; ryzyko bałaganu przy rozroście modułu. |
| 2 | `apps/users/api_schemas.py` | `CreateStaffUserRequest.role`: wzorzec `^(RECEPTION\|DOCTOR\|ADMIN)$` — **brak `TABLET`**, podczas gdy `apps/users/services.create_staff_user` akceptuje `TABLET` — rozjazd dokumentacji API vs serwis (patrz ustalenie #13). |
| 3 | `apps/outbox/services.py` (fragment: `process_outbox_events`, `retry_outbox_event`, `run_retention_cleanup`) | `_execute_event` + backoff + dead letter; `run_retention_cleanup` usuwa lokalny PDF tylko gdy `hidrive_sent` i `sms_sent` — sensowna polityka bezpieczeństwa danych. |
| 4 | `apps/outbox/api_schemas.py` | Limity `ProcessOutboxRequest`/`RetentionRunRequest` — OK. |
| 5 | `apps/intake/outbox_services.py` (fragment: `process_intake_outbox_events`, `retry_intake_outbox_event`) | Zagnieżdżone `transaction.atomic` wewnątrz pętli przy zewnętrznym `@transaction.atomic` — Django używa savepointów; dla długich batchy możliwy długi lock na DB (świadome ryzyko wydajnościowe). |
| 6 | `apps/intake/document_services.py` | `list_intake_documents` / `check_intake_document_access` — **scope placówki** przez `get_scoped_clinic_site_ids`; spójne z listą dokumentów w admin/API (kontrast z ustaleniem #1 dla intake **form**). |
| 7 | `apps/intake/pdf_builder.py` | `build_intake_pdf_bytes` → szablon `pdf/intake_document.html`; WeasyPrint; ścieżka pliku pod `MEDIA_ROOT` — OK. |
| 8 | `apps/intake/admin.py` (fragment) | `ConsentDefinitionAdmin`: `has_add_permission` dla dowolnego `is_staff` — może być szerokie w porównaniu z rolami domenowymi (tylko do rozważenia zaostrzenia). |
| 9 | `apps/operations/metrics.py` | Metryki Prometheus z agregacji ORM + HiDrive refresh; `Gauge` zamiast `Counter` dla „total” — dokumentowane w komentarzu; nadaje się do dashboardów w Dockerze (Prometheus w compose). |
| 10 | `apps/operations/management/commands/run_periodic_tasks.py` | Pętla nieskończona: enqueue `process_outbox_events`, intake outbox, retention, import — zgodne z celem workera; **jeden proces** w kontenerze `scheduler` w compose. |
| 11 | `apps/operations/management/commands/enqueue_tasks.py` | Jednorazowe enqueue — bez pętli; użyteczne do ręcznego odpalenia. |
| 12 | `apps/reception/xlsx_import.py` (fragment: metadane, dopasowanie placówki) | `_resolve_clinic_site` ładuje **wszystkie** `ClinicSite` do pamięci — przy bardzo wielu placówkach możliwy narzut (Niski priorytet); dopasowanie po znormalizowanej nazwie — logiczne. |
| 13 | `apps/medical/services.py` (fragment: `publish_document_version`, początek `revoke`) | Publikacja: `select_for_update`, idempotencja `publish_request_id`, `get_or_create` outbox `GENERATE_PDF` z `payload_schema_version` — zgodne z PRD. |
| 14 | `apps/medical/medical_payload_schemas.py` (fragment: `validate_medical_payload_complete_for_publish`) | Walidacja kompletności przed publikacją z komunikatami z DB (`doctor.*`) — dobra separacja treści. |
| 15 | `apps/medical/template_services.py` (fragment: `create_template`, `update_template`) | `update_template` nie obsługuje edycji szablonów „klinicznych” przez nie-ADMIN (właściciel nie jest sprawdzany dla `clinic_site_id`) — zgodne z wcześniejszą regułą „tylko ADMIN tworzy szablony kliniki”. |
| 16 | `apps/patient_results/services.py` (fragment: OTP rate limit, pepper, `verify_otp`) | **`PATIENT_RESULTS_OTP_PEPPER` wymagany gdy `DEBUG is False`** — realnie chroni produkcję; spójne z twardym wymogiem sekretu. |
| 17 | `apps/core/tests.py` (fragment) | Testy `TranslationServiceTests` — sygnały wersji cache, filtrowanie DEPRECATED; dobra pokrycie krytycznej ścieżki i18n. |
| 18 | `apps/patient_results/urls.py` | Portal HTML: `login` / `otp` / `documents` — proste nazwy. |
| 19 | `apps/patient_results/apps.py` | `verbose_name` po polsku — OK. |
| 20 | `apps/operations/apps.py` | Standard. |
| 21 | `apps/outbox/apps.py` | Standard. |
| 22 | `apps/intake/apps.py` | Standard. |
| 23 | `apps/medical/__init__.py` | Docstring pakietu. |
| 24 | `cogitomedica/api_urls.py` (fragment: ścieżki medyczne, recepcja, intake, patient-results) | Spójne nazwy `name=` dla OpenAPI; pełna mapa v1. |
| 25 | `apps/outbox/management/commands/reset_hidrive_outbox_events.py` (fragment) | Komenda serwisowa resetu zdarzeń HiDrive — **wysokie uprawnienia w rękach operatora** (brak dodatkowej autoryzacji w CLI — typowe dla Django); wymaga dyscypliny wdrożeniowej. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 4 | **25** |
| **Skumulowanie** | **100 / ~270** (~**37,0%**) |

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 4)

### 13. [Utrzymanie / kontrakt API — niskie] Rola `TABLET` w `CreateStaffUserRequest` vs serwis

**Problem:** `apps/users/api_schemas.py` ogranicza `role` w żądaniu tworzenia użytkownika do `RECEPTION|DOCTOR|ADMIN`, natomiast `create_staff_user` w `apps/users/services.py` przyjmuje także `TABLET`.

**Sugestia:** Jeśli konta TABLET mają być tworzone tylko w adminie — zostawić i dopisać komentarz w schemacie. Jeśli przez API — dodać `TABLET` do wzorca Pydantic i testu.

---

### 14. [Styl — niskie] `UpdateStaffUserClinicSitesRequest` w środku `users/api_views.py`

**Problem:** Definicja modelu Pydantic i dodatkowy import na końcu pliku utrudniają nawigację i mogą utrudniać refaktor.

**Sugestia:** Przenieść do `apps/users/api_schemas.py` (lub osobnego modułu schematów) i importować u góry pliku widoków.

---

*Koniec sekcji iteracji 4. Następna: iteracja 5 (kolejne 25 plików).*

---

## Iteracja 5 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23

### Lista plików — iteracja 5 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `apps/medical/api_views.py` (fragment: `medical_document_retry_processing_view`) | `require_user_role` dopuszcza **ADMIN** i **RECEPTION**, ale przed retry wywoływane jest `check_doctor_document_access` — typowa recepcja nie przejdzie (404), mimo że serwis retry dopuszcza recepcję (patrz ustalenie #16). |
| 2 | `apps/medical/services.py` (fragment: `retry_latest_document_processing`) | Warstwa domeny: `Only ADMIN or RECEPTION can retry` + audyt z `context_clinic_site_id` — spójne z operacyjnym celem; **rozjazd z widokiem** (pkt 1). |
| 3 | `apps/intake/services.py` (fragment: `submit_patient_intake_form`) | Transakcyjna walidacja sesji, zgód wymaganych, podpisu, przejścia kolejki — logicznie domknięta ścieżka; brak scope placówki w samej funkcji (jak wcześniej przy formularzu intake — #1). |
| 4 | `apps/reception/services.py` (fragment: tablety) | `get_or_create_tablet_device_by_android_id` — **twardy `clinic_site_id` w `defaults`** + komentarz „TODO: remove after testing” (patrz ustalenie #15). `record_tablet_login_for_android_id` na tym bazuje. |
| 5 | `templates/pdf/befund_document.html` | Szablon WeasyPrint: style inline, logo `static/lab/logo.png`, etykiety z kontekstu — spójne z `pdf_builder`. |
| 6 | `templates/pdf/intake_document.html` | Analogiczny układ PDF intake; nagłówek stały „Intake PDF” (w przeciwieństwie do Befund z `labels`). |
| 7 | `apps/core/translation_loader.py` (fragment) | Seed z JSON: `category_for_key`, `get_or_create` kluczy, `REQUIRED_LANGS` — centralne źródło i18n pod migracje/komendy. |
| 8 | `apps/core/management/commands/load_default_translations.py` | Cienka otoka: `seed_for_management_command()` w transakcji — OK. |
| 9 | `apps/core/management/commands/check_translations_completeness.py` | Walidacja: każdy ACTIVE key ma wartości dla wszystkich `ALLOWED_LANGUAGE_CODES` — dobre jako bramka CI. |
| 10 | `apps/reception/xlsx_import.py` (fragment: `process_patient_xlsx_import_batch`) | Odczyt openpyxl read-only; `_resolve_clinic_site` z metadanych pliku; wymóg domyślnego gabinetu placówki — sensowne granice importu. |
| 11 | `apps/medical/pdf_builder.py` (fragment: `_build_render_context`, tłumaczenia) | Mapowanie `authoring_locale` → język UI; enumeracje lesionów do PDF — czytelne; fallback locale jak w wcześniejszej iteracji. |
| 12 | `apps/core/tests.py` (fragment: walidacja `TranslationValue`) | Testy odrzucenia HTML/`%s`/`%(name)s`/`{x:.2f}` i nieznanych placeholderów — pokrycie reguł bezpieczeństwa treści. |
| 13 | `cogitomedica/openapi_extension.py` (fragment: `cogito_extend_schema`, `build_cogito_openapi_schema`) | Wstrzykiwanie ścieżek v1 + Pydantic `$ref`; `NO_AUTH_OPERATIONS` vs session — spójne z wcześniejszym tematem metrics (#10). |
| 14 | `apps/intake/document_views.py` (fragment) | Lista/szczegół dokumentów intake dla RECEPTION/ADMIN — delegacja do `document_services` ze **scope placówki** (kontrast z #1 dla formularza). |
| 15 | `apps/core/middleware.py` | `CsrfTrustTunnelOriginMiddleware` dla `*.trycloudflare.com`; `TranslationRequestMiddleware` + contextvar — jasny podział odpowiedzialności. |
| 16 | `apps/medical/tests.py` (fragment: `MedicalServicesTests`) | Testy `check_doctor_*_access`, publikacji, szkiców — pokrycie reguł dostępu lekarza vs dokument/kolejka. |
| 17 | `apps/reception/api_tests.py` (fragment) | `TransactionTestCase` / wątki przy testach API recepcji — rozbudowane scenariusze kolejek/importów. |
| 18 | `apps/intake/api_tests.py` | Testy listy/szczegółów/preview PDF dokumentów intake dla RECEPTION/ADMIN — helper `_make_intake_document_version` buduje minimalny łańcuch kolejka → formularz → wersja. |
| 19 | `apps/operations/api_tests.py` | `ObservabilityHealthApiTests` — health/metrics z klientem Django; pokrywa warstwę operacji obok `apps/operations/api_views.py`. |
| 20 | `apps/outbox/api_tests.py` | `OutboxApiTests` — scenariusze API outboxu z `process_outbox_events`, audytem; spójne z workerem. |
| 21 | `apps/users/api_tests.py` | `UsersAuthApiTests` — login/logout/me, audyt `STAFF_AUTH_LOGIN_SUCCESS`; dalsze testy tabletów/staff w tym samym pliku. |
| 22 | `apps/patient_results/api_tests.py` | `PatientResultsRequestOtpApiTests` — request OTP, mocki, integracja z kolejką/pacjentem. |
| 23 | `cogitomedica/api_tests.py` | `ApiDocsEndpointTests` — dostępność `/api/schema/`, Swagger/Redoc; wymóg `staff` dla dokumentacji. |
| 24 | `apps/medical/api_tests.py` | Rozbudowane `MedicalApiTests` — dokumenty medyczne, szkice, publikacja, recepcja vs lekarz (w tym granice retry). |
| 25 | `apps/patient_results/tests.py` | Testy `request_otp` / `verify_otp` + `normalize_phone` — logika serwisu bez pełnego stacku HTTP. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 5 | **25** |
| **Skumulowanie** | **125 / 270** (~**46,3%**) |

*Uwaga:* W tabeli uwzględniono szablony PDF oraz zestaw plików `api_tests.py` / `tests.py` — obok logiki produkcyjnej.

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 5)

### 15. [Bezpieczeństwo / dane — wysokie] Twardy UUID placówki przy auto-rejestracji tabletu

**Problem:** `get_or_create_tablet_device_by_android_id` w `apps/reception/services.py` ustawia w `defaults` stały `clinic_site_id` (`52f81bf4-fbeb-477e-9498-e085e354c027`) z komentarzem „TODO: remove this after testing”. Nowe urządzenia bez wcześniejszego rekordu trafiają do **jednej** placówki — błędna izolacja wieloplacówkowa; dotyczy też `record_tablet_login_for_android_id`.

**Sugestia:** Usunąć stały UUID; przekazywać `clinic_site_id` z kontekstu logowania tableta / konfiguracji urządzenia / pierwszego przypisania przez recepcję; ewentualnie `get_or_create` z `defaults` bez placówki (`None`) i wymuszenie przypisania przed użyciem w kolejce.

```200:207:apps/reception/services.py
# TODO: remove this after testing
def get_or_create_tablet_device_by_android_id(*, android_id: str) -> tuple[TabletDevice, bool]:
    """Get or create a tablet device by android_id (auto-registration). Returns (device, created)."""
    device, created = TabletDevice.objects.get_or_create(
        android_id=android_id,
        defaults={"is_active": True, "clinic_site_id": "52f81bf4-fbeb-477e-9498-e085e354c027"},
    )
    return device, created
```

---

### 16. [Logika / uprawnienia — średnie] Retry przetwarzania dokumentu: RECEPTION w API vs `check_doctor_document_access`

**Problem:** `medical_document_retry_processing_view` zezwala roli **RECEPTION**, ale zaraz wywołuje `check_doctor_document_access`, które przepuszcza głównie ADMIN / autora / przypisanego lekarza. Typowa recepcja dostaje **404** „Medical document not found.”, podczas gdy `retry_latest_document_processing` w serwisie wyraźnie dopuszcza recepcję.

**Sugestia:** Dla **RECEPTION** (i ewentualnie **ADMIN** globalnie) zastąpić lub uzupełnić sprawdzenie: dostęp jeśli `doc.queue_entry.daily_queue.clinic_site_id` należy do `get_scoped_clinic_site_ids(request.user)`; dla **ADMIN** bez zmian lub pełny dostęp. Doprowadzić widok do zgodności z warstwą domeny.

```463:486:apps/medical/api_views.py
@require_auth
def medical_document_retry_processing_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"ADMIN", "RECEPTION"})
    ...
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document_id)
        check_doctor_document_access(doc, request.user)
        retried = retry_latest_document_processing(
            medical_document_id=medical_document_id,
            actor=request.user,
            reason=body.reason,
        )
```

---

*Koniec sekcji iteracji 5. Następna: iteracja 6 (kolejne 25 plików).*

---

## Iteracja 6 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23

### Lista plików — iteracja 6 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `cogitomedica/doctor_views.py` | Panel lekarza: `csrf_protect` na login; `_safe_redirect_next` z `url_has_allowed_host_and_scheme`; lista przez `list_doctor_work_queue`; `doctor_open_by_queue_view` / `doctor_document_detail_view` przez `check_doctor_queue_entry_access` i `get_medical_document_context` — **spójne z API**. |
| 2 | `cogitomedica/tablet_views.py` | Logowanie tabletu: `record_tablet_login_for_android_id` + sesja `tablet_device_id`; `tablet_home_view` — **gdy brak urządzenia w sesji, kolejki na dziś nie są filtrowane po placówce** (wszyscy użytkownicy z rolami TABLET/RECEPTION/ADMIN widzą pełną listę); `tablet_queue_entries_view` / `tablet_entry_start_view` porównują `clinic_site` z urządzeniem, jeśli jest; `tablet_form_view` woła `get_intake_form_context` — dla nie-TABLET bez `tablet_restrict_to_today` (**nadal #1**). |
| 3 | `cogitomedica/urls.py` | Główny routing: portal pacjenta `""`, przekierowania legacy `/ergebnisse/…`, custom admin (`reception-dashboard`, `intake-documents`), tablet `include`, doctor `include`, API v1, schema/docs ze `staff_member_required` — czytelna mapa. |
| 4 | `cogitomedica/doctor_urls.py` | Krótkie ścieżki: login/logout, lista, open-by-queue, szczegół dokumentu — bez zbędnej złożoności. |
| 5 | `cogitomedica/tablet_urls.py` | `app_name = "tablet"`; kolejka → wpisy → start → formularz — zgodne z przepływem poczekalni. |
| 6 | `apps/reception/admin.py` (fragment) | `PatientAdmin.get_queryset`: lekarz widzi pacjentów z `clinic_sites` lub kolejek przypisanych — sensowna izolacja w adminie; import XLSX, `ClinicSite` / `DailyQueue` — bogaty moduł (dalsza część pliku). |
| 7 | `apps/intake/admin.py` (fragment) | `ConsentDefinitionAdmin.has_add_permission` dla dowolnego `is_staff` — szerokie (już wzmiankowane); `IntakeDocumentVersionAdmin` — pola techniczne PDF read-only. |
| 8 | `apps/core/admin.py` | Tłumaczenia: `TranslationValue.save_model` ustawia `updated_by` — audyt edycji. |
| 9 | `apps/patient_results/admin.py` | `PatientResultsOtpSessionAdmin`: lista sesji OTP; `otp_code_hash` read-only — dobrze; brak dodatkowego filtrowania po pacjencie (ADMIN-centric). |
| 10 | `apps/outbox/admin.py` | `OutboxEventAdmin`: `select_related` głębokie pod listę — wydajność; pola payload read-only. |
| 11 | `apps/operations/admin.py` | `AuditEventAdmin.get_queryset`: lekarz jak w API — filtr po `metadata` / `actor_user_id` — spójne z `audit_events_view`. |
| 12 | `apps/operations/api_views.py` (fragment) | `audit_events_view`: ADMIN pełny zakres; DOCTOR z filtrem; paginacja; `observability_health_view` — minimalny payload dla anonima, rozszerzony po autoryzacji; `observability_metrics_view` + Bearer — zgodne z #10. |
| 13 | `apps/core/views.py` | `ratelimited_view` → JSON 429 — prosty kontrakt dla django-ratelimit. |
| 14 | `apps/intake/tasks.py` | `@task(queue_name="outbox")` → `process_intake_outbox_events_service` — jedna odpowiedzialność. |
| 15 | `apps/outbox/tasks.py` | `process_outbox_events` + `run_retention_cleanup(..., older_than_days=30)` — stała polityki retencji w kodzie (świadomy dług techniczny). |
| 16 | `apps/reception/tasks.py` | `run_daily_import` placeholder; `run_patient_xlsx_import` deleguje do `process_patient_xlsx_import_batch` — poprawny worker entrypoint. |
| 17 | `apps/users/models.py` (fragment) | `StaffUser`: role przez `groups` (`is_doctor`, `is_reception`, …); M2M `clinic_sites`; constrainty na format telefonu — spójne z resztą domeny. |
| 18 | `apps/medical/models.py` (fragment) | `MedicalDocument` 1:1 z `QueueEntry` i `PatientIntakeForm`; `MedicalDocumentVersion` z polami publikacji/PDF — model relacyjny pod outbox. |
| 19 | `apps/reception/models.py` (fragment) | `Patient` + unikalność znormalizowanego telefonu; enumy kolejek/importów — dalsze modele w pliku (kolejki, tablety). |
| 20 | `apps/integrations/hidrive/tests.py` | Testy OAuth refresh, cache tokena, adaptera — mock `requests` — dobra izolacja integracji. |
| 21 | `apps/outbox/tests.py` | `OutboxProcessingTests` — przetwarzanie zdarzeń w integracji z dokumentem medycznym. |
| 22 | `apps/medical/admin.py` (fragment) | `MedicalDocumentAdmin` / `MedicalDocumentVersionAdmin`: `select_related`, prefill `created_by_user`, `publish_locale` jako `ChoiceField` z `StaffUserPreferredLocale` — UX admina. |
| 23 | `apps/patient_results/views.py` (fragment) | Portal HTML: `_get_locale` z `Accept-Language`; `request_otp` + sesja przed OTP; **redirect do OTP**: gałąź `locale != "de"` buduje URL z `reverse` + query, gałąź `de` przekazuje nazwę do `redirect()` — obie działają w Django. |
| 24 | `apps/patient_results/document_services.py` (fragment) | `list_patient_documents` tylko opublikowane, current version, bez revocation; `get_patient_pdf_version` wiąże `version_id` z `patient_id` — poprawna granica danych. |
| 25 | `apps/integrations/apps.py` | `IntegrationsConfig` — standardowy `AppConfig`. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 6 | **25** |
| **Skumulowanie** | **150 / 270** (~**55,6%**) |

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 6)

### 17. [Bezpieczeństwo / izolacja — średnie] Tablet: lista kolejek „na dziś” bez przypisanego urządzenia pokazuje wszystkie placówki

**Problem:** W `tablet_home_view` (`cogitomedica/tablet_views.py`) filtrowanie `DailyQueue` po `clinic_site_id` urządzenia wykonuje się **tylko** gdy `_get_tablet_device_from_session` zwraca urządzenie z niepustym `clinic_site_id`. Gdy w sesji **nie ma** `tablet_device_id` (logowanie bez `android_id`) lub urządzenie nie jest znalezione, zapytanie pozostaje **wszystkie kolejki na dziś** (wszystkie placówki).

**Skutek:** Konto **TABLET** (lub RECEPTION) bez powiązania z urządzeniem w sesji może zobaczyć nazwy kolejek/gabinetów innych placówek przy wielu `ClinicSite` w jednej instancji.

**Sugestia:** Dla roli TABLET wymusić albo przypisanie urządzenia (redirect do konfiguracji / komunikat), albo filtrowanie po `get_scoped_clinic_site_ids` / pojedynczej placówce z konta; dla RECEPTION/ADMIN ewentualnie zostawić pełny widok świadomie — ale udokumentować.

```98:120:cogitomedica/tablet_views.py
@login_required(login_url="tablet:login")
def tablet_home_view(request: HttpRequest) -> HttpResponse:
    ...
    device = _get_tablet_device_from_session(request)
    if device is not None:
        if device.clinic_site_id is not None:
            qs = qs.filter(clinic_site_id=device.clinic_site_id)
        else:
            qs = qs.none()
            tablet_unassigned = True
```

*(Gdy `device` jest `None`, `qs` nie jest zawężane do placówki.)*

---

*Koniec sekcji iteracji 6. Następna: iteracja 7 (kolejne 25 plików).*
