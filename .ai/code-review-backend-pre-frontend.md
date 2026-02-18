# Code review – backend API (przed frontendem)

Przegląd wykonany przed rozpoczęciem prac nad frontendem. Zakres: API (JSON), auth, obsługa błędów, spójność, bezpieczeństwo, testy.

---

## 1. Architektura i routing

- **api_urls.py** – jedna płaska lista `path()`; wszystkie endpointy pod `/api/v1/` (prefix w głównym urls). Czytelne, nazwy `name="..."` spójne (kebab-case).
- **Reception** – widoki w `api_views_split/` (patients, queues, dictionaries, devices), agregowane w `apps/reception/api_views.py` i re-eksportowane do `api_urls`. Brak cyklicznych importów.
- **Brak wersjonowania w samych widokach** – wersja tylko w URL; przy ewentualnym v2 można dodać namespace lub osobny moduł.

**Sugestia:** Dla bardzo dużego wzrostu liczby endpointów rozważyć grupowanie po prefixie (np. `path("reception/", include(...))`), na ten moment nie jest to konieczne.

---

## 2. Uwierzytelnienie i autoryzacja

- **require_auth** (dekorator w `apps/core/api_utils.py`) – konsekwentnie używany na wszystkich chronionych endpointach. Zwraca 401 + `{"error": "Authentication required."}`.
- **Publiczne:** `auth/login`, `auth/logout`, `observability/health`, `observability/metrics` – bez auth (zgodne z założeniami).
- **Rola** – `require_user_role(request, allowed_roles={...})` używane tam, gdzie potrzebne:
  - Staff users: tylko `ADMIN`
  - Medical (dokumenty, szablony): `DOCTOR`, `ADMIN`
  - Reception, intake, outbox – tylko `require_auth`, bez sprawdzania roli (każdy zalogowany ma dostęp do list pacjentów/kolejek/outbox itd.). Jeśli docelowo reception ma być tylko dla określonej roli, warto dodać `require_user_role` (np. RECEPTION / ADMIN).
- **Actor mismatch** – medical sprawdza `body.created_by_user_id == request.user.id` (i analogicznie dla draft/publish/templates). Spójne zabezpieczenie przed podszywaniem się pod innego użytkownika.

**Uwaga:** Endpointy operacyjne (`operations/outbox/process`, `operations/retention/run`) są dostępne dla **dowolnego zalogowanego** użytkownika. Jeśli mają być tylko dla admina/crona, dodać `require_user_role(..., allowed_roles={"ADMIN"})` (lub wyłączyć auth i zabezpieczyć np. wewnętrzną siecią / API key).

---

## 3. Obsługa błędów i spójność odpowiedzi

- **json_error(message, status)** – używane wszędzie do `{"error": "<message>"}`. Spójny format.
- **Walidacja Pydantic** – przy `ValidationError` zwracany jest `{"error": "Validation error.", "details": exc.errors()}` i 400. Spójne we wszystkich modułach.
- **404** – `ObjectDoesNotExist` → `json_error("... not found.", status=404)`. Wyjątek: **outbox** używa `OutboxEvent.DoesNotExist` zamiast `ObjectDoesNotExist`. Zachowanie to samo; dla jednolitości można łapać `ObjectDoesNotExist` (Django mapuje `Model.DoesNotExist` na nie).
- **Kody HTTP:**
  - 400 – zły payload, walidacja domenowa (DomainError w większości miejsc).
  - 401 – brak/nieprawidłowe logowanie.
  - 403 – brak uprawnień (role, actor mismatch).
  - 404 – brak zasobu.
  - 409 – konflikt (np. duplicate username, idempotency, StateTransitionError).
  - 422 – używane w reception przy merge (SourceNotTemporaryError, TargetNotConfirmedError) – sensowne „unprocessable entity”.

**Niespójność (niski priorytet):** W **medical** w dwóch miejscach `DomainError` z template’ów zwracany jest jako **403** (create_template ok. 219, update_template ok. 269). Zazwyczaj błędy domenowe (np. „template name already exists”) to raczej 400. Warto ujednolicić na 400, chyba że celowo traktujecie je jako „forbidden”.

---

## 4. Konwencje API

- **Metody** – GET dla odczytu, POST do tworzenia, PUT/PATCH do aktualizacji, DELETE do usuwania/deaktywacji. Spójne.
- **Method not allowed** – widoki zwracają 405 i `json_error("Method not allowed.", status=405)` gdy metoda nieobsługiwana. Spójne.
- **Body** – `read_json_body(request)` + `model_validate()`; przy pustym body używane jest `or "{}"`, więc brak body nie powoduje crashu.
- **Query params** – paginacja (page, page_size) i filtry (is_active, search, limit) parsowane przez helpers z `api_utils`: `parse_positive_int`, `parse_list_limit`, `parse_bool_query`. W razie niepoprawnej wartości część widoków łapie `ValueError` i zwraca 400 – OK.
- **Listy** – format `{"items": [...], "pagination": {...}}` (gdzie jest paginacja) lub `{"items": [...]}` z samym limitem. Staff users i patients mają pełną paginację (page, page_size, total); daily-queues, clinic-sites itd. tylko limit – można to w przyszłości ujednolicić pod frontend (np. zawsze page + page_size gdy potrzebne).
- **CSRF** – `@csrf_exempt` na endpointach zmieniających stan (POST/PUT/PATCH/DELETE), bo API jest używane z JSON (session auth bez formularzy). To standardowe przy API opartym na sesji i JSON.

---

## 5. Moduły – krótkie uwagi

### 5.1 Core (`api_utils`, `exceptions`)

- **api_utils** – skupia: `json_error`, `read_json_body`, `parse_bool_query`, `parse_positive_int`, `parse_list_limit`, `require_authenticated_user`, `require_user_role`, `require_auth`. Stałe `DEFAULT_LIST_LIMIT`, `MAX_LIST_LIMIT`. Brak zależności od innych appów – OK.
- **parse_bool_query(value: str)** – przy `value is None` (np. z `request.GET.get("is_active")`) wywołanie `value.strip()` rzuciłoby błąd. Obecnie wszędzie jest warunek `if is_active_raw is not None` przed wywołaniem – OK. Opcjonalnie można rozszerzyć sygnaturę na `str | None` i na początku zwracać `None`, żeby uprościć widoki.
- **exceptions** – `DomainError`, `StateTransitionError`, `IdempotencyConflictError` – używane w serwisach; w widokach mapowane na 400/409. Spójne.

### 5.2 Users

- Login/logout/me – czytelne; session expiry w odpowiedzi logowania – przydatne dla frontendu.
- Staff users – pełny CRUD, soft delete (deactivate). Paginacja i filtry (role, is_active, search) – spójne z resztą API.

### 5.3 Intake

- Anamnesis (PUT) i submit (POST) – wymagają auth; błędy 404/409/400 obsłużone. Brak osobnego sprawdzenia roli – każdy zalogowany może wysłać formularz; jeśli ma być ograniczenie (np. tylko reception), można dodać `require_user_role`.

### 5.4 Medical

- Dokumenty: create, draft (PUT), publish (POST). Szablony: list (GET z query), create (POST), update (PATCH). Wszystko za `require_auth` + rola DOCTOR/ADMIN oraz weryfikacja `actor_user_id`/created_by/updated_by vs `request.user.id` – dobre.
- **medical_documents_view** – obsługuje tylko POST (tworzenie). Brak GET listy dokumentów – jeśli front będzie potrzebował listy (np. po queue_entry_id / patient_id), trzeba dodać endpoint (np. GET z query).

### 5.5 Outbox

- Lista eventów (GET), process (POST), retry (POST), retention (POST). Walidacja przez Pydantic, błędy 400/404/409. Użycie `OutboxEvent.DoesNotExist` – jak wyżej; można ujednolicić na `ObjectDoesNotExist` dla spójności z resztą projektu.

### 5.6 Reception (api_views_split)

- **patients** – GET (lista z paginacją i filtrami), POST, GET/PATCH/DELETE detail, contact-history (GET), merge (POST). Obsługa DomainError, StateTransitionError, InvalidSourceActionError itd. z odpowiednimi kodami – spójna.
- **queues** – daily queues i queue entries, sesje tabletu; `parse_list_limit` i `parse_positive_int` z try/except ValueError – OK.
- **dictionaries** – clinic sites, consulting rooms; wzorzec jak wyżej.
- **devices** – tablet devices, heartbeat (POST bez body) – OK.
- W **patients** w `patient_merge_view` są dwa osobne `except DomainError` i `except InvalidSourceActionError` – oba zwracają 400; kod jest czytelny, duplikacja minimalna.

### 5.7 Operations (observability)

- Health (GET) – sprawdza DB i liczbę pending/ failed outbox; zwraca JSON z `status` i `checks`. Metryki (GET) – zwracają `text/plain` (Prometheus). Brak auth – poprawne dla health/metrics. Przy metodzie != GET zwracany jest `json_error(..., 405)` – spójne z resztą API.

---

## 6. Bezpieczeństwo i konfiguracja

- **settings.py** – `SECRET_KEY` z env (z fallbackiem w dev); `ENVIRONMENT`, `DEBUG`, `ALLOWED_HOSTS` z env. W produkcji: `SECURE_SSL_REDIRECT`, cookie secure/HSTS, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_AGE`. Sentry z `before_send` filtrującym nagłówki i pola (hasła, tokeny) – dobre.
- **ALLOWED_HOSTS** – przy pustym `ALLOWED_HOSTS` w env wynik to `[]`, co może powodować odrzucanie requestów. W dev warto mieć np. `ALLOWED_HOSTS=localhost,127.0.0.1` lub udokumentować to w README.
- **CORS** – brak konfiguracji CORS w settings. Przy frontendzie na innej domenie/porcie będzie trzeba dodać `django-cors-headers` (lub odpowiedniki) i skonfigurować dozwolone origins. Na ten moment API jest przygotowane pod ten sam origin (np. Django templates) lub proxy.

---

## 7. Testy

- **users** – auth flow (login, me, logout), niepoprawne logowanie, staff users (CRUD, 401 bez auth, 403 bez roli ADMIN). `force_login` używane przy chronionych endpointach – poprawne.
- **medical** – wymagane auth, flow create → draft → publish, szablony, 404. Użycie `force_login` – OK.
- **outbox, reception, intake, operations** – testy jednostkowe/serwisowe i API gdzie są – sensowne. Brak w tym przeglądzie pełnego audytu pokrycia; ogólna jakość testów API jest dobra.

**Sugestia:** Dla frontendu przydatne będą testy integracyjne kluczowych ścieżek (np. reception: utworzenie kolejki → wpis → sesja tabletu → intake submit) oraz ewentualnie kontraktowe (np. OpenAPI/Spectacular) – jeśli jeszcze nie ma.

---

## 8. Podsumowanie rekomendacji

| Priorytet | Rekomendacja |
|-----------|--------------|
| **Wysoki** | **CORS** – dodać i skonfigurować CORS przed frontendem na innej domenie/porcie. |
| **Średni** | **Operacje outbox/retention** – rozważyć ograniczenie do roli ADMIN (lub osobny mechanizm auth), jeśli nie mają być dostępne dla każdego zalogowanego. |
| **Średni** | **ALLOWED_HOSTS** – udokumentować lub ustawić domyślne wartości w dev (np. w .env.example). |
| **Niski** | **Medical DomainError** – w create_template/update_template zwracać 400 zamiast 403 dla błędów walidacji domenowej (zostawić 403 tylko przy rzeczywistym braku uprawnień). |
| **Niski** | **Outbox** – łapać `ObjectDoesNotExist` zamiast `OutboxEvent.DoesNotExist` dla spójności z resztą kodu. |
| **Opcjonalny** | **parse_bool_query** – przyjmować `str \| None` i zwracać `None` przy `None`, żeby uprościć widoki (usunąć `if ... is not None` przed wywołaniem). |
| **Opcjonalny** | **Medical** – jeśli front będzie potrzebował listy dokumentów medycznych (np. po patient/queue_entry), dodać endpoint GET `medical-documents` z filtrami. |

---

## 9. Werdykt

Backend API jest **spójny, czytelny i gotowy na integrację z frontendem**. Auth (require_auth + role + actor check) jest konsekwentnie zastosowane, format błędów i sukcesu ujednolicony, reception podzielone logicznie na pliki. Przed uruchomieniem frontu warto załatwić CORS i (w zależności od wymagań) ograniczenie dostępu do operacji outbox/retention oraz doprecyzować ALLOWED_HOSTS w dev. Reszta to ulepszenia jakościowe i spójnościowe, które można wpleść w dalsze iteracje.
