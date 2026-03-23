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

*Koniec raportu.*
