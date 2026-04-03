# Plan podniesienia code coverage powyżej 82%

Plan oparty na `coverage.txt` (łącznie **8066** instrukcji, **2303** niepokryte, **~71%** pokrycia; w `pyproject.toml` jest już `fail_under = 82`). Aby przejść z ~71% do **>82%**, trzeba pokryć rzędu **~850 dodatkowych instrukcji** (przy niezmienionym zakresie pomiaru).

---

## 1. Analiza luk (Gap Analysis)

### Stan ogólny

- **Cel CI:** `tool.coverage.report.fail_under = 82` w `pyproject.toml`.
- **Źródło:** `apps` + `cogitomedica` (bez migracji, `tests.py`, `api_tests.py`, `test_*.py`).

### Moduły o największej liczbie niepokrytych linii (największy wpływ na %)

| Obszar | Przykładowe pliki | Uwagi |
|--------|-------------------|--------|
| Usługi intake/medical | `apps/intake/services.py` (~133 miss), `apps/medical/services.py` (~93) | Logika workflow, walidacje, integracje domenowe |
| Widoki API | `apps/intake/api_views.py`, `apps/medical/api_views.py`, `apps/reception/api_views_split/*.py`, `apps/operations/api_views.py` | Duże bloki gałęzi (HTTP, uprawnienia, błędy) |
| Import XLSX | `apps/reception/xlsx_import.py` (~114 miss) | Parsowanie, edge cases plików |
| Widoki HTML (tablet/lekarz) | `cogitomedica/tablet_views.py`, `cogitomedica/doctor_views.py` | Niski %, dużo instrukcji |
| Wyniki pacjenta | `apps/patient_results/views.py`, `apps/patient_results/document_services.py` | Portal / PDF / lista dokumentów |
| Anonimizacja | `apps/reception/anonymization.py` (~33% pokrycia) | RODO, transakcje, pliki |

### Pliki z **0%** (łatwe „paczki” instrukcji przy mockach)

- `apps/operations/management/commands/enqueue_tasks.py`, `run_periodic_tasks.py`
- `apps/outbox/management/commands/reset_hidrive_outbox_events.py`
- `apps/outbox/tasks.py`, `apps/reception/tasks.py`
- `cogitomedica/telemetry.py`, `cogitomedica/admin_callbacks.py`, `cogitomedica/wsgi.py`, `cogitomedica/asgi.py`
- `cogitomedica/formats/pl/formats.py`

**Wysokie ryzyko biznesowe (testować wcześniej):** `intake/services.py`, `medical/services.py`, `reception/anonymization.py`, `patient_results/document_services.py` (integralność danych, retencja, pobieranie PDF), API reception (kolejki, słowniki, pacjenci).

---

## 2. Strategia i priorytetyzacja

### Etap 1 — Krytyczna logika biznesowa (najwyższy ROI)

- Rozszerzyć testy dla **`apps/intake/services.py`** i **`apps/medical/services.py`** (funkcje czyste tam, gdzie da się wywołać bez pełnego UI).
- **`apps/reception/anonymization.py`** — scenariusze z danymi w DB + mock usuwania plików (`_try_delete_file` / ścieżki).
- **`apps/patient_results/document_services.py`** — `list_*`, `resolve_*`, `get_patient_pdf_path` (ścieżki: brak wersji, retention, path traversal, plik nie istnieje).

### Etap 2 — Quick wins na pokrycie

- **Management commands / tasks** z **0%**: wywołać `call_command` / zaimportować moduł z **`unittest.mock.patch`** na `.enqueue()` lub task backend — szybko dodaje setki instrukcji przy małej liczbie testów.
- **`apps/reception/xlsx_import.py`** — kilka deterministycznych plików XLSX (poprawny, zły nagłówek, puste wiersze) → duży przyrost %.

### Etap 3 — API i integracje

- **`api_tests.py`** (wzór jak w `cogitomedica/api_tests.py`): endpointy z `Client` + `force_login` + `assign_group_to_test_user` dla `intake`, `medical`, `reception` (szczególnie `queues`, `dictionaries`, `patients`).
- Uzupełnić **`apps/operations/api_views.py`** oraz **`apps/outbox/api_views.py`** tam, gdzie brakuje gałęzi błędów.

### Etap 4 — Widoki HTML i reszta

- `cogitomedica/tablet_views.py`, `doctor_views.py`, `apps/intake/views.py`, `apps/patient_results/views.py` — testy żądań (Django `Client`) z minimalnym setup kolejki/pacjenta.
- Admin (`apps/medical/admin.py`, `apps/reception/admin.py`) — tylko jeśli nadal brakuje %; niższy priorytet vs domena, chyba że CI wymusza.

**Quick wins (najszybszy wzrost %):** commands/tasks 0%, `document_services.py`, wybrane ścieżki w `xlsx_import.py`, potem duże `services.py` / `api_views`.

---

## 3. Propozycje przypadków testowych (skrót)

Dla każdego modułu: **2–5** propozycji; typ: **Unit** (bez HTTP / mocki) vs **Integration** (DB + ewentualnie HTTP).

| Moduł | Propozycje TC | Typ |
|--------|----------------|-----|
| `intake/services.py` | (1) Submit form — brak wymaganej zgody → wyjątek. (2) Brak anamnezy wymaganej. (3) Podpis — rozmiar/format (`InvalidSignatureError`). (4) Ścieżka happy path już częściowo w `tests.py` — dodać gałęzie z `Missing` w raporcie coverage. | Unit / Integration (TestCase) |
| `medical/services.py` | (1) Tworzenie/aktualizacja dokumentu — stany niedozwolone. (2) Publikacja — warunki PDF/status. (3) Funkcje czyste z `medical_payload_schemas` jeśli wywoływane stąd. | Integration |
| `intake/api_views.py` | (1) GET/POST bez uprawnień → 403/302. (2) Walidacja payloadu (400). (3) Sukces z fixture użytkownika Reception. | Integration (API) |
| `medical/api_views.py` | Analogicznie: brak uprawnień, 404 dla nieistniejącego zasobu, poprawna odpowiedź dla roli medycznej. | Integration (API) |
| `reception/api_views_split/queues.py` | (1) Lista kolejki dla dnia. (2) Zmiana statusu wpisu — niedozwolony przejście. (3) Filtry query params. | Integration (API) |
| `reception/xlsx_import.py` | (1) Poprawny arkusz → oczekiwana liczba wierszy. (2) Brak wymaganej kolumny. (3) Nieprawidłowy typ komórki. (4) Pusty plik / pierwszy wiersz nagłówka. | Unit (funkcje parsujące) + Integration |
| `reception/anonymization.py` | (1) Pacjent bez formularza — pusty consent summary. (2) Z formularzem i zgodami — struktura JSON. (3) Usuwanie podpisów — mock `_try_delete_file`. (4) Kolejka nie terminalna → `DomainError` (jeśli dotyczy). | Integration |
| `patient_results/document_services.py` | (1) `list_patient_documents` — tylko `current_version_no`. (2) `resolve_patient_befund_download` — not_found / retention_expired / ok. (3) `get_patient_pdf_path` — względna ścieżka pod `MEDIA_ROOT`, brak pliku, path traversal poza MEDIA. | Unit + Integration |
| `patient_results/views.py` | (1) Lista dokumentów zalogowanego pacjenta. (2) Pobranie PDF — 404/410 zgodnie z serwisem. | Integration |
| `operations/management/commands/*` | (1) `enqueue_tasks` — `retention_only` vs pełna ścieżka vs `--skip-import` (mock `.enqueue()`). (2) `run_periodic_tasks` — wywołanie `handle`. | Unit (command) |
| `outbox/tasks.py`, `reception/tasks.py` | Import modułu + wywołanie funkcji task z mockiem backendu (jeśli wymagane przez framework). | Integration |
| `cogitomedica/telemetry.py` | (1) Inicjalizacja przy wybranych ustawieniach (mock exporter). (2) No-op gdy wyłączone. | Unit |
| `tablet_views.py` / `doctor_views.py` | (1) GET strony po zalogowaniu roli. (2) Redirect dla anonima. | Integration |
| `apps/core/api_utils.py` | Gałęzie błędów walidacji / paginacji wskazane w `Missing` (linie z raportu). | Unit |

---

## 4. Wymagania technologiczne

### Stack (z repozytorium)

- **Python 3.13**, **Django**, **pytest** (`pytest.ini`: `DJANGO_SETTINGS_MODULE=cogitomedica.settings`).
- Testy w **`tests.py`**, **`api_tests.py`**, oraz **`test_*.py`** (już używane).
- **Coverage:** `[tool.coverage.run]` / `[tool.coverage.report]` w `pyproject.toml`.

### Rekomendacje narzędzi

| Potrzeba | Propozycja |
|----------|------------|
| Mockowanie I/O, tasków, zewnętrznych klientów | **`unittest.mock`** (`patch`, `MagicMock`) — spójne z istniejącymi `TestCase` |
| API HTTP | **`django.test.Client`** (jak w `cogitomedica/api_tests.py`) |
| Dane testowe | Istniejące modele ORM + ewentualnie **`model_bakery`** / **`factory_boy`** (tylko jeśli zespół chce skrócić boilerplate — dziś w kodzie jest ręczne `create`) |
| Pliki (PDF, XLSX) | **`tempfile.TemporaryDirectory`**, **`override_settings(MEDIA_ROOT=...)`** |
| Izolacja czasu | **`django.utils.timezone`** + **`freezegun`** (opcjonalnie, jeśli pojawią się flaky testy dat) |

### Struktura

- Trzymać **testy jednostkowe** przy czystych funkcjach (np. fragmenty `xlsx_import`, walidatory) w osobnych klasach w `tests.py` lub `test_<module>.py`.
- **Testy API** konsekwentnie w `api_tests.py` per aplikacja (spójnie z projektem).
- Rozważyć wspólny **`conftest.py`** z fixture użytkownika + `assign_group_to_test_user` — redukcja duplikacji (opcjonalnie, nie blokuje celu %).

---

## 5. Tabela priorytetowa

| Nazwa pliku/modułu | Obecny stan (szacunkowo) | Proponowane testy | Priorytet |
|--------------------|--------------------------|-------------------|-----------|
| `apps/intake/services.py` | ~64% (~133 miss) | Walidacje zgód/anamnezy/podpisu; dodatkowe gałęzie submitu; obsługa błędów domenowych | **Wysoki** |
| `apps/medical/services.py` | ~63% (~93 miss) | Publikacja PDF/stany dokumentu; ścieżki błędów z raportu `Missing` | **Wysoki** |
| `apps/reception/anonymization.py` | ~33% (~49 miss) | Consent summary (z/bez formularza); usuwanie plików (mock); pełny przepływ anonimizacji | **Wysoki** |
| `apps/patient_results/document_services.py` | ~41% (~27 miss) | Lista wersji; `resolve_*` (not_found/retention/ok); `get_patient_pdf_path` + path traversal | **Wysoki** |
| `apps/reception/xlsx_import.py` | ~70% (~114 miss) | Poprawny import; błędne nagłówki; typy danych; puste wiersze; gałęzie z `Missing` | **Wysoki** |
| `apps/intake/api_views.py` | ~59% (~97 miss) | Uprawnienia; 400/404; happy path dla roli Reception | **Wysoki** |
| `apps/medical/api_views.py` | ~59% (~130 miss) | Jak wyżej dla roli medycznej; zasoby nieistniejące | **Wysoki** |
| `apps/reception/api_views_split/queues.py` | ~60% (~100 miss) | Lista/zmiana statusu/filtry; błędne przejścia stanów | **Wysoki** |
| `apps/reception/api_views_split/dictionaries.py` | ~63% (~69 miss) | CRUD/słowniki — sukces i błędy walidacji | **Średni** |
| `apps/reception/api_views_split/patients.py` | ~63% (~60 miss) | Wyszukiwanie/aktualizacja pacjenta; ograniczenia dostępu | **Średni** |
| `apps/operations/api_views.py` | ~42% (~59 miss) | Endpointy operacji + autoryzacja | **Średni** |
| `apps/outbox/api_views.py` | ~68% (~35 miss) | Listowanie/zdarzenia — gałęzie błędów | **Średni** |
| `apps/intake/views.py` | ~28% (~47 miss) | Widoki HTML intake — login, podstawowe GET/POST | **Średni** |
| `apps/patient_results/views.py` | ~17% (~73 miss) | Portal wyników — lista i download | **Średni** |
| `cogitomedica/tablet_views.py` | ~38% (~121 miss) | Tablet UI — autoryzacja i kluczowe ekrany | **Średni** |
| `cogitomedica/doctor_views.py` | ~33% (~80 miss) | Panel lekarza — te same wzorce | **Średni** |
| `apps/operations/management/commands/*.py` | 0% (~71 łącznie) | `call_command` + mock `.enqueue()` / zależności tasków | **Wysoki** (quick win) |
| `apps/outbox/tasks.py`, `apps/reception/tasks.py` | 0% | Wywołanie z mockiem backendu zadań | **Wysoki** (quick win) |
| `apps/outbox/management/commands/reset_hidrive_outbox_events.py` | 0% (~59) | Dry-run / potwierdzenie (z mockiem HiDrive jeśli potrzeba) | **Średni** |
| `cogitomedica/telemetry.py` | 0% (~29) | Włącz/wyłącz; mock konfiguracji OTEL | **Średni** (quick win) |
| `cogitomedica/wsgi.py`, `asgi.py`, `admin_callbacks.py`, `formats/pl/formats.py` | 0% / niski % | Minimalne testy importu/entrypoint (lub wykluczenie z coverage — decyzja zespołu) | **Niski** |
| `apps/medical/admin.py`, `apps/reception/admin.py` | ~59–66% | Kluczowe akcje admina używane w produkcji | **Niski** |
| `apps/core/api_utils.py` | ~75% (~36 miss) | Gałęzie obsługi błędów i paginacji | **Średni** |

---

## Podsumowanie

Najpierw **komendy/zadania 0%** oraz **`patient_results/document_services`** i **`reception/anonymization`** / **`xlsx_import`** dają szybki skok procentowy; równolegle **intake/medical `services` + `api_views`** domykają ryzyko i większość brakujących ~850 instrukcji. Po osiągnięciu ~80% dodać **widoki tablet/doctor/patient_results** oraz resztę API reception, żeby stabilnie utrzymać **>82%** przy `fail_under`.
