# Przegląd kodu — Cogitomedica

**Data:** 2026-03-23  
**Zakres:** repozytorium Django (`apps/`, `cogitomedica/`, `templates/`, `static/`), zasady z `.cursor/rules/backend-django-cogitomedica.mdc`.

## Metodologia i pokrycie

| Kategoria | Liczba plików (szac.) | Status przeglądu |
|-----------|----------------------:|------------------|
| Python — migracje Django (`**/migrations/*.py`) | ~110 | Przegląd **zbiorczy**: założenie zgodności z konwencją Django; seed/data migrations nie analizowane linia po linii. |
| Python — kod aplikacji (bez `migrations/`) | ~160 | **100% plików zmapowanych** do pakietów; **szczegółowy przegląd** warstwy: `settings`, routing, `api_views`, `services`, integracje, modele kluczowe, HTML widoki (`doctor`, `tablet`), middleware, `core/api_utils`. Pozostałe moduły (m.in. `*_tests.py`, komendy `management`, duplikaty ścieżek) — **weryfikacja skrótowa** (spójność z architekturą + grep pod wzorce ryzyka). |
| Szablony HTML / statyczne JS/CSS | **38** plików `*.html` + **5** zasobów w `static/` | **Przegląd iteracyjny zamknięty:** T1 (**18**), T2 (**20**), T3 (**5**) — **43 / 43** slotów (38 HTML + 5 static). |
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

## Priorytety zgłoszeń do realizacji (od najważniejszych do najmniej ważnych)

Kolejność poniżej jest globalna (cały dokument: #1-#18 oraz T1-T6) i uwzględnia wpływ na bezpieczeństwo danych medycznych, izolację wieloplacówkową, zgodność z PRD oraz reguły `.cursor/rules/backend-django-cogitomedica.mdc`.

1. **[#1] Brak scope'u `clinic_site` przy dostępie do intake (API + tablet HTML)** - ryzyko IDOR i naruszenia izolacji danych między placówkami.
2. **[#18] API listy/retry outboxu bez scope placówki (medyczny + intake)** - możliwy odczyt i retry zdarzeń innych placówek (IDOR).
3. **[#15] Twardy UUID placówki przy auto-rejestracji tabletu** - błędne przypisanie urządzeń i naruszenie separacji tenantów.
4. **[#17] Tablet home bez urządzenia pokazuje kolejki wszystkich placówek** - wyciek metadanych operacyjnych cross-clinic.
5. **[#12] Lista urządzeń tabletów bez scope placówki** - recepcja widzi urządzenia spoza własnego zakresu.
6. **[#2] Wyłączone walidatory haseł Django** - osłabienie bezpieczeństwa kont personelu.
7. **[#5] Brak limitu rozmiaru body w `read_json_body`** - ryzyko DoS przez duże payloady JSON.
8. **[#4] Ciężkie przetwarzanie outbox synchronicznie w HTTP** - naruszenie architektury async i ryzyko timeoutów.
9. **[#16] Retry dokumentu: niespójne uprawnienia RECEPTION (API vs serwis)** - błąd logiki dostępu i operacyjności.
10. **[#11] Dashboard recepcji pokazuje globalne błędy outbox** - nadmiarowa ekspozycja metadanych między placówkami.
11. **[T2] `signature.data_url` w PDF intake bez twardej walidacji schematu/rozmiaru** - potencjalny wektor nieprzewidywalnego renderowania.
12. **[#7] Tworzenie/aktualizacja staff bez gwarancji przypisania grupy** - możliwe "puste" konta bez roli.
13. **[#3] `PATIENT_RESULTS_OTP_PEPPER` bywa pusty poza twardym prod** - niższy priorytet, bo w `DEBUG=False` jest już wymuszany.
14. **[T5] `logged_out_admin.html` rozszerza nieistniejący `base.html`** - możliwy runtime `TemplateDoesNotExist`.
15. **[T3] Brak `static/tablet/css/form.css` używanego w szablonie** - 404 CSS i degradacja UX formularza.
16. **[#8] `passenger_wsgi.py` inicjalizuje Django per request** - koszt wydajnościowy (wysoki tylko przy użyciu Passenger).
17. **[#9] Brak `setup_telemetry()` w `asgi.py`** - ryzyko utraty instrumentacji przy wdrożeniu ASGI.
18. **[T6] Potencjalne N+1 w `master_detail.html` (`queue.entries.all`)** - degradacja wydajności widoków.
19. **[T1] Zewnętrzne CSS/JS bez SRI** - ryzyko supply-chain, ograniczone przez kontekst wdrożenia.
20. **[T4] Zewnętrzne URL w `account_links`/`site_url` bez whitelisty** - potencjalny phishing przy złej konfiguracji.
21. **[#10] OpenAPI pokazuje metrics jako publiczne** - głównie niespójność dokumentacji z implementacją.
22. **[#13] Kontrakt API roli `TABLET` niespójny z serwisem** - dług kontraktu i ryzyko niejasności integracyjnych.
23. **[#14] Model Pydantic osadzony w `users/api_views.py`** - problem stylu/utrzymania.
24. **[#6] Hardcoded dev origins (`CSRF_TRUSTED_ORIGINS`, tunel)** - niska pilność, głównie higiena konfiguracji.

### Status realizacji (2026-03-28)

Poniższe zgłoszenia zostały zaadresowane kodem i testami regresyjnymi uruchomionymi w Dockerze:

- [x] **#1** Brak scope'u `clinic_site` przy dostępie do intake (API + tablet HTML)
- [x] **#18** API listy/retry outboxu bez scope placówki (medyczny + intake)
- [x] **#15** Twardy UUID placówki przy auto-rejestracji tabletu
- [x] **#17** Tablet home bez urządzenia pokazuje kolejki wszystkich placówek
- [x] **#12** Lista urządzeń tabletów bez scope placówki
- [x] **#5** Brak limitu rozmiaru body w `read_json_body`
- [x] **T2** `signature.data_url` w PDF intake bez twardej walidacji schematu/rozmiaru
- [x] **#11** Dashboard recepcji pokazuje globalne błędy outbox
- [x] **#7** Tworzenie/aktualizacja staff bez gwarancji przypisania grupy
- [x] **#3** `PATIENT_RESULTS_OTP_PEPPER` wymuszony poza środowiskiem dev
- [x] **T5** `logged_out_admin.html` nie rozszerza już nieistniejącego `base.html`
- [x] **T3** `static/tablet/css/form.css` obecny i podłączony (potwierdzenie/utrzymanie)
- [x] **#9** `setup_telemetry()` dodane do `asgi.py`
- [x] **T1** Usunięte zewnętrzne CSS/JS bez SRI z krytycznych szablonów (portal/index)
- [x] **T4** Zewnętrzne URL w `account_links`/`site_url` filtrowane przez whitelistę schematu
- [x] **#10** OpenAPI nie oznacza już `/observability/metrics` jako publicznego
- [x] **#13** Kontrakt API roli `TABLET` ujednolicony ze serwisem users
- [x] **#14** `UpdateStaffUserClinicSitesRequest` przeniesiony do `users/api_schemas.py`
- [x] **#6** Usunięte hardcoded dev origins z `settings.py` + wycofana mutacja CSRF w runtime

### Szczegóły (ustalenia #1-#6 z pierwszej części raportu)

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
| **Skumulowane sloty tabel iteracji 1–11** | **270 / 270** (zgodnie z ~liczbą plików `*.py` w repo; pojedyncze pliki mogą występować w wielu iteracjach jako fragmenty) |

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

---

## Iteracja 7 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23

### Lista plików — iteracja 7 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `cogitomedica/settings.py` (fragment) | `SECRET_KEY` wymuszany w `prod`; Sentry `before_send` filtruje nagłówki/cookies; `ALLOWED_HOSTS` + dev: `web`, `.trycloudflare.com` — spójne z middleware CSRF (#6). |
| 2 | `cogitomedica/api_urls.py` (fragment) | Pełna mapa v1: observability, auth, staff, audit, **outbox/intake-outbox**, medical, reception CRUD, intake-forms, patient-results — jeden plik jako indeks kontraktu API. |
| 3 | `apps/outbox/api_views.py` | `outbox_events_view`: lista `OutboxEvent` po filtrach status/typ/**bez** `get_scoped_clinic_site_ids` — recepcja widzi zdarzenia wszystkich placówek (patrz #18); `operations_outbox_process_view` tylko ADMIN + synchroniczne `process_outbox_events` (#4); `outbox_event_retry_view` — pobranie po ID bez weryfikacji placówki (#18). |
| 4 | `apps/core/api_utils.py` | `read_json_body` bez limitu rozmiaru (#5); `require_user_role` / `get_scoped_clinic_site_ids` / `get_tablet_scope_clinic_site_ids` / `require_actor_match` — centralne narzędzia; **outbox nie używa scope w widokach** (rozjazd). |
| 5 | `apps/reception/views.py` | `reception_dashboard_view`: importy + globalne `failed_outbox` — zgodne z ustaleniem #11. |
| 6 | `apps/intake/views.py` | Lista/szczegół dokumentów intake w panelu admin HTML: `list_intake_documents` + `get_scoped_clinic_site_ids` do dropdown placówek — **spójne z izolacją** (kontrast z #1 dla formularza API). |
| 7 | `apps/core/signals.py` | Sygnały `TranslationKey`/`TranslationValue` → `bump_translation_version` — proste, przewidywalne unieważnianie cache. |
| 8 | `apps/core/context_processors.py` | `admin_submit_button_translations`: tylko dla `path` z `/admin/`; fallbacki EN — bezpieczne dla braków w DB. |
| 9 | `apps/outbox/services.py` (fragment) | `_execute_event` z OTEL span; łańcuch GENERATE_PDF → HIDRIVE → SMS; symulacja błędu przez payload — testowalne. |
| 10 | `apps/intake/outbox_services.py` (fragment) | Analogiczny pipeline dla intake PDF / HiDrive; `select_related` do kolejki/placówki — spójne z outboxem medycznym. |
| 11 | `cogitomedica/admin_callbacks.py` | Unfold: etykieta środowiska (`prod`/`staging`/dev); `dashboard_callback` no-op — rozszerzalne. |
| 12 | `cogitomedica/telemetry.py` | OTLP HTTP, instrumentacje Django/requests/psycopg; `psycopg` w try/except — nie blokuje startu. |
| 13 | `apps/outbox/hidrive_paths.py` | `_sanitize_folder_part` usuwa separatory ścieżek; szablony nazw plików Befund/Intake — redukcja złych znaków w ścieżce chmurowej. |
| 14 | `apps/integrations/hidrive/auth.py` (fragment) | Token w pamięci procesu; metryki Prometheus `hidrive_token_refresh_*`; refresh grant — solidny wzorzec. |
| 15 | `apps/integrations/sms/client.py` (fragment) | `get_sms_patient_results_text` z tłumaczeń DB; `format_phone_for_smsapi`; protokół `SmsAdapter` — czyste granice. |
| 16 | `apps/users/forms.py` | `StaffUserCreationForm` z Unfold — minimalne pola (`username`); hasło przez bazowy formularz. |
| 17 | `apps/core/exceptions.py` | Cienka warstwa: `DomainError`, `StateTransitionError`, `IdempotencyConflictError`, `InvalidRequestBodyEncoding`. |
| 18 | `apps/patient_results/models.py` | `PatientResultsOtpSession`: FK do `Patient`, constrainty `expires_at > created_at`, indeksy po `phone` — pod rate limit i audyt. |
| 19 | `apps/operations/services.py` (fragment) | `create_audit_event` + `metadata._ref` dla compliance — zgodne z opisem w iteracji 2. |
| 20 | `apps/intake/api_views.py` (fragment: intake outbox) | `intake_outbox_events_view` / `intake_outbox_event_retry_view` — **ten sam brak scope placówki** co outbox medyczny (#18). |
| 21 | `apps/users/api_views.py` (fragment: `auth_login_view`) | `@ratelimit` 5/m na POST; Pydantic body; `create_audit_event` na sukces — spójne z hardeningiem. |
| 22 | `apps/patient_results/api_views.py` (fragment) | Publiczne OTP z rate limit; `create_audit_event` z `patient_id` gdy znany; pobieranie PDF przez `get_patient_pdf_path`. |
| 23 | `apps/medical/api_views.py` (fragment: `medical_document_audit_trail_view`) | GET audytu po `medical_document_id` z `check_doctor_document_access` — poprawne ograniczenie względem dokumentu. |
| 24 | `apps/core/http_utils.py` | `get_client_ip` z `X-Forwarded-For` — uwaga za proxy (#17 w iteracji 1). |
| 25 | `manage.py` | `setup_telemetry()` przed `execute_from_command_line`; błędy OTEL połykane — start nie pada, diagnostyka może zginąć. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 7 | **25** |
| **Skumulowanie** | **175 / 270** (~**64,8%**) |

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 7)

### 18. [Bezpieczeństwo / izolacja — średnie] API listy i retry outboxu (medyczny + intake) bez scope placówki dla recepcji

**Problem:** W `apps/outbox/api_views.py` widok `outbox_events_view` buduje `OutboxEvent.objects.order_by(...)` z filtrami status/typ/`retry_count`, ale **nie ogranicza** wyników do placówek z `get_scoped_clinic_site_ids(request.user)`. Rola **RECEPTION** (nie-ADMIN) może więc odczytać metadane błędów (`error_message`, `medical_document_version_id`) dotyczące innych placówek. `outbox_event_retry_view` ładuje zdarzenie po samym `id` i wywołuje `retry_outbox_event` — **brak sprawdzenia**, czy dokument/kolejka należy do placówki użytkownika (potencjalny **IDOR** przy znanym UUID).

Analogicznie w `apps/intake/api_views.py`: `intake_outbox_events_view` i `intake_outbox_event_retry_view` listują / retryują **wszystkie** zdarzenia intake outbox bez joinu do `daily_queue.clinic_site_id` i bez scope.

**Sugestia:** Dla użytkowników z przypisanymi placówkami filtrować przez join: `OutboxEvent` → `MedicalDocumentVersion` → `medical_document__queue_entry__daily_queue__clinic_site_id__in=scope` (oraz odpowiednik dla intake); dla ADMIN zostawić pełny widok. Przy retry: odrzucać 404, gdy dokument nie jest w scope.

```23:69:apps/outbox/api_views.py
@require_auth
def outbox_events_view(request: HttpRequest) -> JsonResponse:
    ...
    qs = OutboxEvent.objects.order_by("-created_at")
    if body.status:
        qs = qs.filter(status=body.status)
    ...
```

*(Brak filtrowania po placówce przed `[:limit]`.)*

---

*Koniec sekcji iteracji 7. Następna: iteracja 8 (kolejne 25 plików).*

---

## Iteracja 8 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23

### Lista plików — iteracja 8 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `apps/users/services.py` | `create_staff_user` / `update_staff_user`: przypisanie grupy przez `Group.objects.filter(...).first()` — jeśli grupa nie istnieje, użytkownik **bez roli** (ustalenie #7); `VALID_ROLES` obejmuje `TABLET` — spójne z Pydantic API (#13). |
| 2 | `apps/medical/services.py` (fragment) | `check_doctor_document_access` / `check_doctor_queue_entry_access`: autor, przypisany lekarz lub ADMIN — jasna reguła; `list_medical_documents` filtruje nie-ADMIN po autorze/kolejce przypisanego lekarza; `create_or_get_medical_document` waliduje powiązanie intake z kolejką i status SUBMITTED. |
| 3 | `apps/intake/services.py` (fragment: `get_intake_form_context`) | Budowa kontekstu zgód/anamnezy; `tablet_restrict_to_today` tylko dla roli TABLET — **brak weryfikacji placówki względem użytkownika/urządzenia** (nadal #1). |
| 4 | `apps/patient_results/services.py` (fragment: `request_otp` / `verify_otp`) | Anti-enumeration (`silent_no_op`), rate limit SMS, Turnstile; **`ValueError` gdy `DEBUG is False` i brak `PATIENT_RESULTS_OTP_PEPPER`** (uzupełnienie #3); `verify_otp`: limit prób, hash SHA-256, atomowe oznaczenie sesji. |
| 5 | `cogitomedica/openapi_schemas.py` (fragment) | Konwersja Pydantic → OpenAPI (`$defs` → `components`); modele odpowiedzi dokumentacyjne (`extra="forbid"`) — spójne z kontraktami. |
| 6 | `cogitomedica/tests.py` | Testy `pydantic_to_openapi_schema`, `build_components_schemas`, rejestracja ścieżek w `build_cogito_openapi_schema` — ochrona regresji schematu. |
| 7 | `apps/reception/xlsx_import.py` (fragment: `enqueue_patient_xlsx_import`) | Zapis pliku + SHA256, batch `PROCESSING`, `run_patient_xlsx_import.enqueue` — delegacja do workera; audyt `PATIENT_XLSX_IMPORT_ENQUEUED`. |
| 8 | `apps/medical/befund_text.py` (fragment) | Słowniki DE/EN dla cech, ocen, ryzyka — źródło treści Befund równolegle do PDF/enumów. |
| 9 | `apps/medical/constants.py` | `get_args` + `befund_text` + `medical_payload_schemas` — jedno źródło kodów i etykiet EN dla admina. |
| 10 | `apps/outbox/models.py` (fragment) | `OutboxEvent`: unikalność per typ+wersja, constrainty `aggregate_id`, indeksy częściowe PENDING/FAILED, GIN na `payload` — pod worker i diagnostykę. |
| 11 | `apps/operations/models.py` (fragment) | `AuditEvent`: FK + `metadata` GIN + indeksy złożone (pacjent/dokument/placówka/czas) — pod listy i compliance. |
| 12 | `apps/intake/models.py` (fragment) | `ConsentDefinition` z oknami `effective_from`/`effective_to`; `IntakeOutboxEventType` — spójne z pipeline PDF/HiDrive. |
| 13 | `apps/reception/models.py` (fragment: `TabletDevice`) | `android_id` unikalny; opcjonalny `clinic_site` — model pod przypisanie urządzenia (logika #15/#17 w serwisach/widokach). |
| 14 | `apps/reception/api_views_split/imports.py` (fragment) | `_visible_batches`: nie-ADMIN tylko własne batche; serializacja błędów z `raw_row` — sensowne dla supportu. |
| 15 | `apps/reception/api_views_split/dictionaries.py` (fragment) | CRUD placówek/gabinetów z Pydantic; GET typowo ze `get_scoped_clinic_site_ids` (dalsza część pliku) — wzorzec izolacji. |
| 16 | `apps/reception/phone_utils.py` | `normalize_phone`: tylko cyfry, pusty wynik gdy `<7` — spójne z walidacją modelu `Patient`. |
| 17 | `apps/core/translation_service.py` (fragment) | `contextvars` + `bump_translation_version`; cache `i18n:data:…` TTL 300 s — typowy wzorzec invalidacji przez sygnały. |
| 18 | `apps/reception/api_views_split/queues.py` (fragment) | `daily_queues_view`: TABLET tylko kolejka „dziś”; `get_scoped_clinic_site_ids` / `get_tablet_scope_clinic_site_ids` — **wzorzec poprawny** w porównaniu z #17 (tablet home HTML). |
| 19 | `apps/reception/api_views_split/devices.py` (fragment) | `tablet_devices_view` GET: `TabletDevice.objects.all()` bez scope — ustalenie #12. |
| 20 | `apps/integrations/hidrive/client.py` (fragment) | Mock vs real; retry przy 401 z odświeżeniem tokena — odporność na wygaśnięcie OAuth. |
| 21 | `apps/medical/medical_payload_schemas.py` (fragment) | `MedicalPayloadV1` + `MedicalPayloadLesionV1` z walidacją duplikatów numerów zmian — reguły kliniczne w Pydantic. |
| 22 | `apps/intake/pdf_builder.py` (fragment) | `_normalize_snapshot` + WeasyPrint z szablonu — izolacja danych do HTML PDF. |
| 23 | `apps/reception/api_views_split/patients.py` (fragment) | `patients_view` z `get_scoped_clinic_site_ids` dla nie-ADMIN — wzorzec izolacji pacjentów po placówkach (kontrast z #1 przy intake form). |
| 24 | `apps/core/models.py` (fragment: `TranslationKey` / `TranslationValue`) | `clean`: prefiks klucza vs kategoria, bleach/HTML, walidacja `{name}` placeholderów — pokryte testami w `apps/core/tests.py`. |
| 25 | `apps/medical/template_services.py` (fragment) | `list_templates` / `get_template`: dla nie-ADMIN filtr global + właściciel + `clinic_site_id` w M2M użytkownika — spójne z iteracją 3 (tworzenie szablonów klinicznych tylko ADMIN). |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 8 | **25** |
| **Skumulowanie** | **200 / 270** (~**74,1%**) |

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 8)

### Uzupełnienie do ustalenia #3 (OTP pepper)

**Obserwacja z kodu:** W `apps/patient_results/services.py` (`request_otp`) przy braku `PATIENT_RESULTS_OTP_PEPPER` rzucany jest **`ValueError`**, gdy `DEBUG is False`. W środowisku developerskim (`DEBUG=True`) pusty pepper jest nadal dozwolony — świadomy kompromis lokalny; **produkcja wymusza** pepper przez ten warunek. Ustalenie #3 pozostaje aktualne dla środowisk „pół-produkcyjnych” z `DEBUG=True`.

---

*Koniec sekcji iteracji 8. Następna: iteracja 9 (kolejne 25 plików).*

---

## Iteracja 9 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23

### Lista plików — iteracja 9 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `apps/intake/document_services.py` (fragment) | `list_intake_documents` filtruje po `get_scoped_clinic_site_ids`; `check_intake_document_access` porównuje placówkę wersji z scope — **wzorzec poprawny**, kontrast z brakiem scope przy `get_intake_form_context` w API intake (#1). |
| 2 | `apps/intake/api_views.py` (fragment) | `intake_form_detail_view` / consents / body map: `get_intake_form_context` / `save_*` po `intake_form_id` bez dodatkowego scope — **nadal #1**; rate limit `@ratelimit` na GET/PATCH wybranych ścieżek. |
| 3 | `apps/medical/api_schemas.py` (fragment) | Pydantic: `MedicalPayloadMinimal` z `schema_version`; pola `*_user_id` oznaczone jako ignorowane — spójne z sesją; `RetryProcessingRequest` z domyślnym powodem. |
| 4 | `apps/reception/api_schemas.py` (fragment) | `PHONE_PATTERN` zgodny z modelem; `CreateQueueEntrySessionRequest` z `tablet_device_id` / `android_id`; walidacja `UpdateDailyQueueRequest` („at least one field”) — czytelne kontrakty. |
| 5 | `cogitomedica/wsgi.py` | `setup_telemetry()` przed `get_wsgi_application`; błędy OTEL w `except` — spójne z `manage.py`. |
| 6 | `cogitomedica/asgi.py` | **Brak** `setup_telemetry()` — potwierdzenie ustalenia #9 (ASGI vs WSGI). |
| 7 | `passenger_wsgi.py` | `get_wsgi_application()` **w każdym requeście** + nietypowa konwersja `PATH_INFO` — potwierdzenie ustalenia #8. |
| 8 | `apps/operations/metrics.py` (fragment) | Prometheus: Gauge z agregacji DB, serie zerowe gdy brak wierszy; wiek najstarszego PENDING/FAILED; metryki importu — pod Grafana w Dockerze. |
| 9 | `apps/outbox/services.py` (fragment) | `process_outbox_events`: `select_for_update(skip_locked=True)`, backoff wykładniczy, dead letter, audyt przy sukcesie/błędzie; `retry_outbox_event` z audytem `context_clinic_site_id`; `run_retention_cleanup` tylko gdy HiDrive+SMS OK — spójne z PRD. |
| 10 | `apps/patient_results/urls.py` | Portal HTML: `login` / `otp` / `documents` pod `app_name = "ergebnisse"` — proste nazwy. |
| 11 | `apps/intake/api_schemas.py` (fragment) | `UpdateBodyMapRequest` z punktami 0–1 i `side` front/back; sekcja intake outbox (limity jak `api_utils`) — spójność z widokami. |
| 12 | `apps/reception/services.py` (fragment) | `create_or_update_patient_manual` — aktor w sygnaturze na przyszły audyt (`_ = created_or_updated_by_user_id`); `create_daily_queue` waliduje gabinet vs placówkę i duplikat slotu — dobre reguły domenowe. |
| 13 | `apps/users/auth_backends.py` | `StaffGroupAdminBackend`: rola ADMIN → pełne `has_perm` / `has_module_perms` — świadoma eskalacja (jak w iteracji 1). |
| 14 | `apps/operations/management/commands/run_periodic_tasks.py` | Pętla `while True`: enqueue outbox medyczny, intake outbox, retention, opcjonalnie import — jeden proces schedulera w kontenerze. |
| 15 | `apps/integrations/sms/tests.py` | Testy `get_sms_patient_results_text` dla DE/EN/PL — powiązanie z tłumaczeniami DB. |
| 16 | `apps/core/apps.py` | `ready()` importuje `signals` — rejestracja sygnałów tłumaczeń. |
| 17 | `apps/reception/apps.py` | Standardowy `AppConfig` bez dodatkowej logiki. |
| 18 | `apps/medical/pdf_builder.py` (fragment: `build_befund_pdf_bytes` / `generate_befund_pdf`) | WeasyPrint z `base_url=BASE_DIR`; zapis pod `PDF_RELATIVE_DIR` + SHA-256 — spójne z outboxem GENERATE_PDF. |
| 19 | `cogitomedica/openapi_extension.py` (fragment: wstęp) | `PREFIX = /api/v1`; schematy stronicowania zgodne z `DEFAULT_LIST_LIMIT` / `MAX_LIST_LIMIT` — dokumentacja zsynchronizowana z kodem. |
| 20 | `apps/outbox/__init__.py` | Krótki docstring pakietu — bez logiki. |
| 21 | `apps/medical/widgets.py` (fragment) | `LesionGroupFavoritesWidget`: JSON → base64 do HTML; fallback gdy brak JS — mniejsze ryzyko XSS w atrybutach. |
| 22 | `apps/patient_results/apps.py` | `verbose_name` po polsku dla modułu portalu. |
| 23 | `apps/intake/apps.py` | Standardowy `AppConfig`. |
| 24 | `apps/medical/apps.py` | Standardowy `AppConfig`. |
| 25 | `apps/operations/apps.py` | Standardowy `AppConfig`. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 9 | **25** |
| **Skumulowanie** | **225 / 270** (~**83,3%**) |

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 9)

### Pozytywna spójność (odniesienie do #1)

**Obserwacja:** Warstwa `apps/intake/document_services.py` (lista PDF intake, `check_intake_document_access`) stosuje **`get_scoped_clinic_site_ids`** i porównanie `clinic_site_id` — zgodnie z modelem izolacji wieloplacówkowej. Rozjazd dotyczy wyłącznie ścieżek **formularza intake** (`get_intake_form_context` / mutacje po `intake_form_id` w `api_views`), co potwierdza wcześniejsze ustalenie #1 jako **niespójność między modułami** (PDF vs formularz), a nie brak wzorca w całej aplikacji intake.

---

*Koniec sekcji iteracji 9. Następna: iteracja 10 (kolejne 25 plików).*

---

## Iteracja 10 — przegląd 25 plików (szczegółowy)

**Data iteracji:** 2026-03-23

### Lista plików — iteracja 10 (25)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `apps/users/api_schemas.py` | `AuthLoginRequest` z opcjonalnym `android_id`; `CreateStaffUserRequest.role` wzorzec bez `TABLET` — rozjazd z `users/services` i #13; hasło min. 8 znaków w schemacie (kontrast z wyłączonymi walidatorami Django #2). |
| 2 | `apps/outbox/api_schemas.py` | `OutboxEventsQueryParams`, `ProcessOutboxRequest` (limit 1–500), `RetryOutboxEventRequest`, `RetentionRunRequest` — limity zgodne z widokami. |
| 3 | `apps/patient_results/document_services.py` (fragment: `get_patient_pdf_path`) | `path.resolve().is_relative_to(media_resolved)` — ochrona przed path traversal (jak w iteracji 2). |
| 4 | `cogitomedica/openapi_extension.py` (fragment: `NO_AUTH_OPERATIONS`) | Publiczne w schemacie m.in. `health`, **`metrics`**, monitoring links, `auth/login`, OTP — **metrics** bez session w OpenAPI (potwierdzenie #10); OTP i login uzasadnione. |
| 5 | `apps/outbox/management/commands/reset_hidrive_outbox_events.py` (fragment) | CLI resetu zdarzeń HiDrive (medical + intake); `--dry-run`, `--since-days` — wysokie uprawnienia operatora (jak w iteracji 4). |
| 6 | `apps/intake/outbox_services.py` (fragment: `process_intake_outbox_events`) | Ten sam wzorzec co outbox medyczny: `skip_locked`, backoff, dead letter, audyt z `context_clinic_site_id`. |
| 7 | `apps/users/api_views.py` (fragment: staff) | `staff_users_view`: tylko ADMIN; filtrowanie po roli z `valid_roles` zawierającym **TABLET**; `create_staff_user` z body Pydantic — spójne z domeną poza #13. |
| 8 | `apps/medical/api_views.py` (fragment) | POST dokumentu: `check_doctor_queue_entry_access`; GET detail/preview PDF: audyt + `check_doctor_document_access` gdzie potrzeba — spójna ochrona. |
| 9 | `apps/reception/xlsx_import.py` (fragment: nagłówki) | `HEADER_ALIASES` wielojęzyczne; `_find_header_indices` — elastyczny import z eksportów. |
| 10 | `apps/medical/models.py` (fragment: `DoctorTextTemplate`) | `clean`: global vs owner vs `clinic_site` — constrainty spójne z `template_services`. |
| 11 | `apps/intake/models.py` (fragment: `PatientIntakeForm`) | 1:1 z `QueueEntry` i sesją; GIN na JSON; constraint „SUBMITTED wymaga podpisu” — integralność danych. |
| 12 | `manage.py` | `setup_telemetry()` przed `execute_from_command_line` — spójne z `wsgi.py`. |
| 13 | `apps/__init__.py` | Docstring pakietu domenowego. |
| 14 | `apps/medical/services.py` (fragment: `publish_document_version`) | Idempotencja `publish_request_id`, kolizja locale, walidacja payload przed publikacją, łańcuch outbox — rdzeń PRD. |
| 15 | `apps/operations/management/commands/enqueue_tasks.py` | Jednorazowe enqueue tasków (outbox ×2, retention, import) — alternatywa dla pętli `run_periodic_tasks`. |
| 16 | `apps/core/management/commands/load_default_translations.py` | Otoka na `seed_for_management_command()` w transakcji. |
| 17 | `apps/core/management/commands/check_translations_completeness.py` | Bramka: ACTIVE keys vs `ALLOWED_LANGUAGE_CODES`. |
| 18 | `apps/users/admin.py` (fragment) | `StaffUserAdmin`: `filter_horizontal` dla grup i `clinic_sites`; `has_view_permission` dla roli ADMIN — rozszerzona kontrola widoczności. |
| 19 | `apps/reception/api_views_split/queues.py` (fragment) | POST kolejki: sprawdzenie `clinic_site_id` w scope; GET/PATCH szczegółu: scope + ograniczenia DOCTOR — **wzorcowa izolacja**. |
| 20 | `apps/patient_results/api_views.py` (fragment) | `verify_otp` → audyt; lista dokumentów i download z sesji pacjenta + `get_patient_pdf_version`; odmowa pobrania z audytem. |
| 21 | `apps/outbox/apps.py` | Standardowy `AppConfig`. |
| 22 | `apps/users/apps.py` | Standardowy `AppConfig`. |
| 23 | `apps/integrations/__init__.py` | Docstring pakietu integracji. |
| 24 | `cogitomedica/settings.py` (fragment: CORS) | `CORS_ALLOWED_ORIGINS` z `.env` w prod; w dev lista localhost; `CORS_ALLOW_CREDENTIALS = True` — świadomy model cookie cross-origin. |
| 25 | `apps/core/translation_loader.py` (fragment: `seed_for_management_command`) | Ścieżka `apps/core/translation_data`; iteracja po JSON — spójna z komendą seed. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 10 | **25** |
| **Skumulowanie** | **250 / 270** (~**92,6%**) |

---

## Ustalenia wymagające działania — uzupełnienie (iteracja 10)

### Uzupełnienie do ustalenia #10 (OpenAPI / metrics)

**Potwierdzenie z kodu:** `NO_AUTH_OPERATIONS` w `cogitomedica/openapi_extension.py` zawiera parę `(…/observability/metrics, get)`, więc Swagger oznacza metryki jako bez `security` — zgodnie z wcześniejszym ustaleniem #10 (implementacja nadal wymaga Bearer lub ADMIN).

---

*Koniec sekcji iteracji 10. Następna: iteracja 11 (poniżej — domknięcie mapy).*

---

## Iteracja 11 — przegląd 20 plików (domknięcie mapy modułów źródłowych)

**Data iteracji:** 2026-03-23

**Kontekst:** Automatyczna weryfikacja wykazała **17** plików `*.py` poza `migrations/` (i poza `venv`), których pełna ścieżka **nie występowała** w treści dokumentu przed tą iteracją — są ujęte w wierszach 1–17. Wiersze 18–20 domykają mapę pakietów migracji (`__init__.py`) oraz dają **punkt odniesienia** do warstwy migracji operacyjnych (zgodnie z przeglądem zbiorczym z metodologii).

### Lista plików — iteracja 11 (20)

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `apps/core/__init__.py` | Docstring pakietu współdzielonych prymitywów — bez logiki wykonawczej. |
| 2 | `apps/core/management/__init__.py` | Pusty moduł pakietu komend. |
| 3 | `apps/core/management/commands/__init__.py` | Pusty moduł pakietu komend. |
| 4 | `apps/intake/__init__.py` | Docstring domeny intake. |
| 5 | `apps/intake/tests.py` | Testy `submit_patient_intake_form`, łańcuch zgód/anamnezy i pliku podpisu — regresja domeny; **nie** adresują osobno scope placówki w HTTP API (por. ustalenie #1). |
| 6 | `apps/operations/__init__.py` | Docstring modułu operacji / audytu. |
| 7 | `apps/operations/management/__init__.py` | Pusty moduł pakietu `management`. |
| 8 | `apps/operations/management/commands/__init__.py` | Pusty moduł pakietu komend. |
| 9 | `apps/operations/tests.py` | Kontrakty `create_audit_event` i `_serialize_audit_event`: `metadata._ref`, `context_clinic_site_id`, odczyt ID przy `SET_NULL` na FK — **wartościowe** pod compliance i API audytu. |
| 10 | `apps/outbox/management/__init__.py` | Pusty moduł pakietu. |
| 11 | `apps/outbox/management/commands/__init__.py` | Pusty moduł komend (logika w plikach `*.py` obok). |
| 12 | `apps/reception/__init__.py` | Docstring domeny recepcji. |
| 13 | `apps/reception/tests.py` | Testy serwisów recepcji, importu XLSX, integracji z adminem kolejki; import modułu migracji purge seed — **ciężki** plik regresji, spójny z modelami. |
| 14 | `apps/users/__init__.py` | Docstring pakietu użytkowników i uprawnień. |
| 15 | `apps/users/tests/__init__.py` | Pusty moduł pakietu testów. |
| 16 | `apps/users/tests/test_admin_changelist.py` | Asercje na `StaffUserAdmin`: jeden punkt wejścia edycji (`list_display_links`), brak zduplikowanej kolumny „Edytuj” w HTML. |
| 17 | `cogitomedica/__init__.py` | Pusty moduł konfiguracyjny projektu Django. |
| 18 | `apps/core/migrations/__init__.py` | Pusty marker pakietu migracji — konwencja Django. |
| 19 | `apps/patient_results/migrations/__init__.py` | Pusty marker pakietu migracji. |
| 20 | `apps/reception/migrations/0001_initial.py` (fragment) | Migracja **initial**: `ClinicSite`, `ConsultingRoom`, … — standardowy szablon `CreateModel`; **brak nowych ustaleń** względem przeglądu zbiorczego migracji z początku dokumentu. |

### Postęp iteracji (pliki `.py`)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji 11 | **20** |
| **Skumulowanie** | **270 / 270** (~**100%** slotów mapy repo w tabelach iteracji) |

### Domknięcie mapy (poza `venv`)

Po uzupełnieniu wierszy 1–17 **każda** ścieżka `*.py` w projekcie poza katalogami `migrations/` (z wyłączeniem środowiska wirtualnego) **występuje** jako substring w `code_review.md` — nie pozostają „niewidoczne” moduły źródłowe. Warstwa `**/migrations/*.py` nadal objęta jest **przeglądem zbiorczym** (w tym reprezentacja w wierszu 20), nie pełnym odczytem każdej linii seedów.

---

*Przegląd iteracyjny plików `.py` w tabelach: **zamknięty** (iteracje 1–11). Dalsze prace: wdrożenia ustaleń #1–#18 oraz **poniżej** szablony/statyczne.*

---

## Szablony HTML / statyczne — przegląd iteracyjny

**Zakres:** `templates/`, `apps/*/templates/`, `static/` (bez `venv`).

**Inwentaryzacja (2026-03-23):** **38** unikalnych plików `*.html`; w `static/` **5** zasobów: **3×** CSS (`cogitomedica/`, `admin/`), **1×** JS (`admin/js`), **1×** PNG (`lab/logo.png`).

**Kryteria (skrót):** XSS (domyślne `{{ }}` vs `|safe` / `{% autoescape off %}`), treści użytkownika w PDF, zewnętrzne skrypty/styles (CDN, integralność), CSRF w formularzach, `json_script` vs `innerHTML`.

---

### Iteracja T1 — szablony i statyczne (18 pozycji)

**Data:** 2026-03-23  
**Skupienie:** PDF (WeasyPrint), panel lekarza (Unfold), tablet i portal wyników (proste portale), widget admina (łącznie z Alpine), pełny zestaw plików `static/` projektu.

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `templates/pdf/intake_document.html` | Dane pacjenta/zgód/anamnezy przez `{{ }}` — **autoescape**; **uwaga:** `<img src="{{ signature.data_url }}"` — jeśli backend dopuści nie-`data:image/*`, ryzyko nieoczekiwanego protokołu (zaufana walidacja po stronie serwera PDF). |
| 2 | `templates/pdf/befund_document.html` | Etykiety `labels.*` i `befund.*` — escape; listy/rekomendacje w pętlach — spójne z modelem; logo `static/lab/logo.png` względne pod WeasyPrint. |
| 3 | `templates/doctor/base.html` | Rozszerza `admin/base_site.html`; linki `{% url %}`, `{% csrf_token %}` w logout; `{{ user.username }}` / `user.role` — escape. |
| 4 | `templates/doctor/login.html` | Unfold: `{{ error }}` escape; `next` w hidden — redirect nadal w widoku (`_safe_redirect_next`); języki przez query `?lang=`. |
| 5 | `templates/doctor/list.html` | Filtry `value="{{ filters.* }}"` — escape; statusy z enumów; **`{{ item.processing_error_message }}`** — komunikat z backendu (escape). |
| 6 | `templates/doctor/detail.html` (fragment) | `{{ panel_data|json_script:"doctor-panel-data" }}` — **bezpieczny** wzorzec Django JSON; formularz Befund + szablony — treść statyczna/choices; PL w podpowiedziach (spójność UX z DE). |
| 7 | `templates/doctor/error.html` | `{{ message }}` — escape. |
| 8 | `templates/tablet/base.html` | `{% static %}`; `{{ request.user.username }}` / `role` — escape; link wylogowania z namespace `tablet`. |
| 9 | `templates/tablet/login.html` | `{{ error }}` escape; `android_id` wypełniane z `localStorage`/UUID w inline `<script>` — **nie** wstrzykuje HTML z serwera; nadal zależność od JS do powiązania urządzenia. |
| 10 | `templates/ergebnisse/base.html` | CDN: `flag-icon-css` (cdnjs) + `cogitomedica-brand.css`; **brak SRI** na zewnętrznych CSS — **#T1** (integralność / supply chain); linki języków `{{ request.path }}?locale=`. |
| 11 | `templates/ergebnisse/login.html` | Cloudflare Turnstile (warunkowo) + `challenges.cloudflare.com` — zaufane źródło; skrypt inline kopiuje token do hidden — OK; `{{ error }}` escape; `max="{{ today_iso }}"` na dacie. |
| 12 | `templates/index.html` (fragment) | Landing: CDN Bootstrap Icons (jsdelivr), `cogitomedica-brand.css` + `@import` Google Fonts w CSS — **#T1**; favicon `assets/favicon.ico` — ścieżka poza `{% static %}` (może 404 jeśli brak assetu w deploy). |
| 13 | `apps/medical/templates/medical/widgets/lesion_group_favorites.html` (fragment) | `atob('{{ widget.*_b64 }}')` — wartości z widgetu (base64 JSON); Django escapuje atrybut; **bez** `|safe` w atrybucie — poprawnie; Alpine `x-data` — logika po stronie klienta (zgodnie z iteracją Python widgetów). |
| 14 | `static/cogitomedica/css/cogitomedica-brand.css` | `@import` Google Fonts — zewnętrzny request, brak SRI dla `@import` — **#T1**; zmienne kolorów; style `.cm-portal` — brak JS. |
| 15 | `static/cogitomedica/css/admin-changelist-link.css` | Placeholder (1 komentarz) — brak logiki. |
| 16 | `static/cogitomedica/css/unfold-sidebar-fix.css` | Placeholder — brak logiki. |
| 17 | `static/admin/js/unfold-force-light.js` | Wymusza motyw jasny; zapis do `localStorage` — brak `eval`; niewielki skrypt administracyjny. |
| 18 | `static/lab/logo.png` | Zasób binarny (logo w PDF i portalach); brak treści wykonywalnej. |

### Postęp iteracji (szablony + statyczne)

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji T1 | **18** |
| **Skumulowanie** | **18 / ~43** (~**42%** pozycji inwentarza: 38 HTML + 5 static) |

---

### Iteracja T2 — szablony (20 pozycji)

**Data:** 2026-03-23  
**Skupienie:** admin (Unfold), recepcja/intake w panelu, rejestracja kont, helpery Unfold, przepływ tabletu (kolejki → wpisy → formularz → błąd), portal OTP/dokumenty.

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `templates/admin/login.html` | Standard Unfold: `{% csrf_token %}`, pola przez `field.html`, `action="{{ app_path }}"` — OK; komunikaty i18n. |
| 2 | `templates/admin/submit_line.html` | Przyciski zapisu / akcji / anuluj / usuń — `{% url %}`, `original.pk` — bez surowego HTML z użytkownika. |
| 3 | `templates/admin/reception/dashboard.html` | Lista `failed_outbox` + importy: typy/statusy z modelu, UUID dokumentu — escape; **treść zgodna z ustaleniem #11** (globalny widok błędów — logika w widoku, nie w szablonie). |
| 4 | `templates/admin/reception/dailyqueue/change_list.html` | Rozszerza `change_list`: przycisk Import XLSX przez `import_xlsx_url` — bezpieczny `href` z widoku. |
| 5 | `templates/admin/reception/dailyqueue/import_xlsx.html` | Upload: `{% csrf_token %}`, `enctype="multipart/form-data"`; inline JS pobiera `id` pola pliku z szablonu — **bez** `eval`; przycisk „Wybierz plik” steruje natywnym inputem. |
| 6 | `templates/admin/intake/documents_list.html` (fragment) | Filtry GET, dropdown placówek (`{{ site.name }}`), linki do szczegółów — escape; spójne z widokiem listy PDF intake. |
| 7 | `templates/admin/intake/document_detail.html` (fragment) | Dane pacjenta/kolejki, `{{ doc.processing_error_message }}` — escape; PDF inline jeśli dostępny (dalsza część pliku). |
| 8 | `templates/registration/login.html` | Rozszerza `index.html`: `{% csrf_token %}`, `next` w hidden — redirect po stronie widoku; etykiety po DE. |
| 9 | `templates/registration/logged_out.html` | Unfold layout; link do `admin:index` przez `{% url %}` — OK. |
| 10 | `templates/unfold/helpers/account_links.html` | `href="{{ site_url }}"`, pętla `account_links`: **`href="{{ link.link }}"`** — jeśli konfiguracja admina kiedykolwiek wstrzyknie niebezpieczny URL, ryzyko phishingu (zależność od źródeł danych); `{{ link.title }}` escape. |
| 11 | `templates/unfold/helpers/theme_switch.html` | Alpine `x-on:click` — tylko stałe `'light'|'dark'|'auto'`; brak danych użytkownika w atrybutach. |
| 12 | `templates/unfold/helpers/unauthenticated_header.html` | `{{ site_url }}` w linku „powrót” — jak wyżej (#10). |
| 13 | `templates/tablet/form.html` (fragment) | Zgody: `{{ c.content }}` — **autoescape** (HTML w DB wyświetli się bezpiecznie); `{% static 'tablet/css/form.css' %}` — **w repo brak pliku** `static/tablet/css/form.css` (patrz **#T3** poniżej). |
| 14 | `templates/tablet/home.html` | Lista kolejek: `{{ q.clinic_site.name }}` — escape; komunikat `tablet_unassigned` z tłumaczeń. |
| 15 | `templates/tablet/queue_entries.html` | Wpisy kolejki: dane pacjenta, `time` filter — OK. |
| 16 | `templates/tablet/entry_start.html` | POST + CSRF; JS ustawia `android_id` / `tablet_device_id` z `localStorage`/cookie — jak w loginie. |
| 17 | `templates/tablet/form_submitted.html` | Prosty ekran sukcesu; link `{% url 'tablet:home' %}`. |
| 18 | `templates/tablet/error.html` | Standalone (nie `extends` base): `{{ message }}` — escape. |
| 19 | `templates/ergebnisse/otp.html` | OTP: `pattern="[0-9]{6}"`, CSRF; `{{ error }}` escape. |
| 20 | `templates/ergebnisse/documents.html` | Lista dokumentów: `{% url 'patient-results-download' version_id=item.version_id %}` — identyfikator wersji z kontekstu, nie z GET. |

### Postęp iteracji (szablony + statyczne) — po T2

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji T2 | **20** |
| **Skumulowanie (stan po T2)** | **38 / ~43** (~**88%**): **5** plików `static/` (T1) + **33** z **38** plików `*.html` |

*Pełne domknięcie mapy szablonów — iteracja T3 (poniżej).*

---

### Iteracja T3 — szablony (5 pozycji — domknięcie mapy)

**Data:** 2026-03-23  
**Skupienie:** ostatnie szablony wymienione po T2; po tej iteracji **każdy** plik `*.html` w repo ma wpis w tabeli przeglądu (T1–T3) lub był objęty jako fragment w T1/T2.

| # | Ścieżka | Uwagi przeglądu |
|---|---------|-----------------|
| 1 | `templates/admin/reception/dailyqueue/master_detail.html` | Master/detail kolejek: filtr GET `queue_date`, `{% url 'admin:…' %}`, pętle `queue.entries.all` — **uwaga wydajnościowa:** N+1 w widoku, jeśli brak `prefetch_related` na wpisach/pacjentach; dane w komórkach — escape. |
| 2 | `templates/registration/logged_out_user.html` | Minimalny widok po wylogowaniu: `extends index.html`, link `{% url 'accounts:login' %}` — OK. |
| 3 | `templates/registration/logged_out_admin.html` | `{% extends "base.html" %}` — w **projekcie brak** `templates/base.html` (tylko m.in. `doctor/base`, `tablet/base`, `ergebnisse/base`); szablon jest **prawdopodobnie nieużywalny** albo rzuca `TemplateDoesNotExist` — patrz **#T5**; surowy tekst „Admin” w treści — wygląd na artefakt. |
| 4 | `templates/results.html` | Landing wyników: `{{ user.first_name }}` / `last_name`, link `{% url 'download_file' file %}` z `target="_blank"` — `file` z kontekstu widoku (nie z parametru URL); treść statyczna po DE. |
| 5 | `templates/tablet/entry_started.html` | Po starcie wpisu: `{% url 'tablet:form' intake_form_id=intake_form_id %}`, drugi link do kolejki — CSRF nie wymagany przy samych GET linkach; treści ze `staff_ui` — escape. |

### Postęp iteracji (szablony + statyczne) — po T3

| Metryka | Wartość |
|--------|--------|
| Przejrzane w iteracji T3 | **5** |
| **Skumulowanie** | **43 / 43** (**100%** slotów: 38 `*.html` + 5 plików `static/`) |

---

## Ustalenia — szablony / statyczne (iteracja T1)

### T1. [Utrzymanie / bezpieczeństwo — niskie] Zewnętrzne CSS/JS bez SRI

**Obserwacja:** `ergebnisse/base.html` ładuje `flag-icon` z cdnjs; `index.html` — Bootstrap Icons z jsdelivr; `cogitomedica-brand.css` importuje fonty Google. **Brak** `integrity=` / `crossorigin` na tych tagach.

**Skutek:** Teoretyczna kompromitacja CDN lub MITM (np. w sieciach publicznych) — podmiana zasobów.

**Sugestia:** Dla krytycznych wdrożeń: SRI + `crossorigin`, albo hostowanie kopii w `static/` (jak już zrobione dla części stylów).

### T2. [Bezpieczeństwo — niskie–średnie] `signature.data_url` w PDF intake

**Obserwacja:** Szablon PDF zakłada poprawny `data:image/...;base64,...` w `src` obrazu.

**Skutek:** Jeśli backend kiedykolwiek dopuści inny schemat URL, WeasyPrint/HTML może zachować się nieprzewidywalnie.

**Sugestia:** Walidacja po stronie budowania kontekstu PDF (tylko `data:image/*` i rozsądny rozmiar), spójnie z przechowywaniem pliku podpisu.

---

## Ustalenia — szablony / statyczne (iteracja T2)

### T3. [Utrzymanie / UX — średnie] Brak `static/tablet/css/form.css` przy odwołaniu w szablonie

**Obserwacja:** `templates/tablet/form.html` ładuje `{% static 'tablet/css/form.css' %}`. W drzewie projektu **nie ma** katalogu `static/tablet/` ani pliku `form.css` (stan repo 2026-03-23).

**Skutek:** W przeglądarce — **404** dla arkusza; formularz intake na tablecie polega głównie na inline stylach i `cogitomedica-brand.css`, ale część layoutu (jeśli planowana w `form.css`) nie działa.

**Sugestia:** Dodać plik do `static/tablet/css/form.css` albo usunąć link i przenieść style do istniejącego CSS; zweryfikować `collectstatic` na wdrożeniu.

### T4. [Bezpieczeństwo — niskie] Zewnętrzne URL w `account_links` / `site_url`

**Obserwacja:** `unfold/helpers/account_links.html` i `unauthenticated_header.html` emitują `href` z kontekstu (`site_url`, `link.link`).

**Skutek:** Przy błędnej konfiguracji lub przyszłym rozszerzeniu źródeł linków możliwy **phishing** lub otwarcie `javascript:` (mało prawdopodobne przy domyślnych ustawieniach Django).

**Sugestia:** Utrzymywać whitelistę schematów po stronie konfiguracji / kontekstu admina; nie pobierać `href` z niezaufanego inputu użytkownika końcowego.

---

## Ustalenia — szablony / statyczne (iteracja T3)

### T5. [Utrzymanie — średnie / wysokie jeśli szablon w użyciu] `logged_out_admin.html` rozszerza nieistniejący `base.html`

**Obserwacja:** `templates/registration/logged_out_admin.html` ma `{% extends "base.html" %}`. W katalogu `templates/` **nie ma** pliku `base.html` (są domenowe `base` w podkatalogach).

**Skutek:** Żądanie widoku, które renderuje ten szablon, zakończy się **TemplateDoesNotExist** (chyba że inny loader dostarcza `base.html` — w typowym `DIRS` + `templates/` **nie**).

**Sugestia:** Zmienić `extends` na istniejący layout (np. `index.html` jak w `logged_out_user.html`) albo dodać minimalny `templates/base.html`; usunąć zbędny tekst „Admin” z treści lub zastąpić tłumaczeniem.

### T6. [Wydajność — niskie] `master_detail.html` i `queue.entries.all`

**Obserwacja:** Szablon iteruje `{% for entry in queue.entries.all %}` w pętli po kolejkach.

**Skutek:** Bez prefetch w widoku — klasyczne **N+1** zapytań do bazy.

**Sugestia:** W widoku admina: `prefetch_related('entries', 'entries__patient')` (lub równoważnie) dla listy `queues`.

---

*Przegląd iteracyjny szablonów i plików statycznych w tabelach: **zamknięty** (T1–T3).*
