# Plan podniesienia jakości testów i pokrycia kodu

## Zasada nadrzędna

**Jakość testów > procent pokrycia.** Celem nie jest osiągnięcie liczby 82%, lecz zbudowanie suite'u testów, który faktycznie łapie regresje, chroni krytyczną logikę biznesową i nie spowalnia developmentu. Procent pokrycia jest efektem ubocznym, nie celem.

---

## 0. Stan wyjściowy

- **8066** instrukcji, **2303** niepokryte, **~71%** pokrycia instrukcji.
- `fail_under = 82` w `pyproject.toml` — obecnie nieosiągalne, gate jest de facto wyłączony.
- **304** testy, **~6k linii** kodu testowego, **zero** plików `conftest.py`, **zero** fabryk.
- Testy oparte wyłącznie na `django.test.TestCase` z ręcznym `setUp` i `objects.create(...)`.
- Brak branch coverage — mierzone jest tylko pokrycie instrukcji.
- Brak diff-coverage — nowy kod może wchodzić do `main` bez testów.

---

## Faza 0 — Infrastruktura testowa (warunek konieczny)

Bez tej fazy każdy napisany test mnoży dług techniczny zamiast go spłacać.

### 0.1. Wykluczenie boilerplate z pomiaru

Pliki, które nie zawierają logiki biznesowej, zawyżają deficyt i motywują do pisania bezwartościowych testów.

Dodać do `[tool.coverage.run].omit`:

```toml
"cogitomedica/wsgi.py",
"cogitomedica/asgi.py",
"cogitomedica/formats/pl/formats.py",
"cogitomedica/admin_callbacks.py",
```

**Efekt:** ~33 instrukcje znikają z raportu, pokrycie rośnie do ~72% bez jednego nowego testu. Ważniejsze: eliminuje pokusę pisania bezwartościowych testów importu.

### 0.2. Włączenie branch coverage

Dodać do `pyproject.toml`:

```toml
[tool.coverage.run]
branch = true
```

**Dlaczego:** Pokrycie instrukcji nie wykrywa nieosiągniętych gałęzi `if/else`, `try/except`, `and/or`. Branch coverage to minimum, które nadaje metryce jakąkolwiek wartość diagnostyczną. Po włączeniu globalne % spadnie o kilka punktów — to jest informacja, nie problem.

### 0.3. Inkrementalne podnoszenie `fail_under`

Zmienić `fail_under` na **aktualną wartość + 1pp** i podnosić z każdym sprintem:

| Sprint | `fail_under` (branch) | Uwagi |
|--------|-----------------------|-------|
| Bieżący | Ustawić na aktualny % po włączeniu branch coverage | Bazeline — CI musi przechodzić od dziś |
| +1 | +2pp | Po fazie 1 |
| +2 | +2pp | Po fazie 2 |
| +3 | +2pp | Po fazie 3 |
| Docelowo | 80% branch | Rewizja po 4 sprintach |

**Dlaczego:** Skok 71% → 82% to abstrakcyjny cel bez planu dojścia. Inkrementalne podnoszenie daje mechanizm egzekucji — CI czerwone = blokada merge'a.

### 0.4. Diff-coverage jako gate na nowy kod

Dodać do CI:

```yaml
- name: Diff coverage
  run: |
    pip install diff-cover
    diff-cover coverage.xml --compare-branch=origin/main --fail-under=90
```

**Dlaczego:** Globalna metryka nie zapobiega dodawaniu nowego, nieobjętego kodu. Diff-cover wymusza, że każdy nowy PR ma ≥90% pokrycia gałęzi. To jedyne narzędzie, które chroni przed regresją pokrycia w czasie.

### 0.5. Wspólny `conftest.py` z fixture'ami

Stworzyć `conftest.py` w katalogu głównym z fixture'ami, które dziś są powielane w `setUp` wielu klas:

```python
import pytest
from django.test import Client
from apps.core.api_utils import assign_group_to_test_user
from apps.users.models import StaffUser


@pytest.fixture
def staff_user(db):
    return StaffUser.objects.create_user(
        username="testuser", password="testpass"
    )


@pytest.fixture
def reception_user(staff_user):
    assign_group_to_test_user(staff_user, "Reception")
    return staff_user


@pytest.fixture
def doctor_user(staff_user):
    assign_group_to_test_user(staff_user, "Doctor")
    return staff_user


@pytest.fixture
def admin_user(staff_user):
    assign_group_to_test_user(staff_user, "Admin")
    return staff_user


@pytest.fixture
def tablet_user(staff_user):
    assign_group_to_test_user(staff_user, "Tablet")
    return staff_user


@pytest.fixture
def auth_client(staff_user):
    client = Client()
    client.force_login(staff_user)
    return client


@pytest.fixture
def tmp_media(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    return tmp_path / "media"
```

**Dlaczego:** Dziś **304 testy** powielają boilerplate tworzenia użytkowników. Bez tego fundamentu każdy nowy test to kopia-wklej istniejącego `setUp`, a refaktoryzacja modelu `StaffUser` wymaga zmian w dziesiątkach plików.

### 0.6. Instalacja `model_bakery` do generacji danych

Dodać do `requirements-dev.txt`:

```
model_bakery
```

**Dlaczego:** Ręczne `Patient.objects.create(first_name=..., last_name=..., ...)` w każdym teście:
- wymaga znajomości wymaganych pól modelu,
- łamie się przy dodaniu nowego wymaganego pola,
- zmusza do wypełniania pól nieistotnych dla testu.

`baker.make(Patient)` automatycznie generuje minimalne poprawne instancje. Istniejące testy nie wymagają migracji — `model_bakery` jest addytywny.

### 0.7. Instalacja `freezegun` do izolacji czasu

Dodać do `requirements-dev.txt`:

```
freezegun
```

**Dlaczego:** `timezone.now()` jest używane w co najmniej 6 kluczowych modułach (`anonymization.py`, `services.py`, `xlsx_import.py`). Testy zależne od aktualnego czasu są źródłem flaky failures (przełom dnia/miesiąca/roku). Nie jest "opcjonalny" — jest wymagany.

---

## Faza 1 — Logika krytyczna biznesowo (najwyższe ryzyko)

Priorytetyzacja wg **ryzyka biznesowego**, nie liczby niepokrytych linii.

### 1.1. `apps/reception/anonymization.py` (~33%, 49 miss)

**Ryzyko:** RODO compliance. Błąd = kara finansowa, nie bug.

**Specyfika testowania:** Moduł ma celowo nieatomatowy design — faza 2 (usuwanie plików) działa poza `transaction.atomic`. Testy muszą pokryć scenariusze częściowej awarii.

| Przypadek testowy | Typ | Weryfikacja |
|-------------------|-----|-------------|
| Pacjent z aktywnymi (nieterminalnymi) wpisami w kolejce → blokada | Integration | `DomainError` raised, żadne dane nie zmienione |
| Pełny happy path: pacjent z formularzami, zgodami, podpisami, dokumentami | Integration | Dane zanonimizowane, sentinele poprawne, audit event created |
| `_extract_consent_summary` — pacjent bez formularza | Integration | Pusta lista/dict |
| `_extract_consent_summary` — z formularzem i zgodami | Integration | Struktura JSON zgodna z oczekiwaniami |
| Awaria `_try_delete_file` w fazie 2 (mock rzuca wyjątek po N wywołaniach) | Integration | Faza 1 committed, faza 3 NIE wykonana, stan bazy spójny |
| Idempotentność — ponowne uruchomienie na częściowo zanonimizowanym pacjencie | Integration | Brak wyjątku, stan końcowy poprawny |

**Mockowanie:** `patch('apps.reception.anonymization._try_delete_file')`, `freeze_time`.

### 1.2. `apps/patient_results/document_services.py` (~41%, 27 miss)

**Ryzyko:** Pacjent pobiera cudzy PDF lub PDF po retention — naruszenie prywatności.

| Przypadek testowy | Typ | Weryfikacja |
|-------------------|-----|-------------|
| `list_patient_documents` — filtrowanie do `current_version_no` | Integration | Stare wersje niewidoczne |
| `resolve_patient_befund_download` — dokument nie istnieje | Integration | `not_found` result |
| `resolve_patient_befund_download` — retention expired | Integration | `expired` result |
| `resolve_patient_befund_download` — revoked version | Integration | Odrzucone |
| `resolve_patient_befund_download` — happy path | Integration | Poprawny path + metadata |
| `get_patient_pdf_path` — path traversal (ścieżka poza `MEDIA_ROOT`) | Unit | `ValueError` / odmowa |
| `get_patient_pdf_path` — plik nie istnieje na dysku | Unit | Odpowiedni błąd / None |

**Mockowanie:** `tmp_media` fixture, `baker.make(MedicalDocumentVersion, ...)`.

### 1.3. `apps/intake/services.py` (~64%, 133 miss)

**Ryzyko:** Integralność danych pacjenta, podpisy, zgody.

**Podejście:** Wydzielić testy pure functions (niski koszt) od testów integracyjnych (wyższy koszt, wyższe ROI).

**Pure functions (unit tests, bez DB):**

| Funkcja | Przypadki |
|---------|-----------|
| `_humanize_code` | Kilka wariantów string input |
| `_localized_text` | Brakujący klucz, istniejący klucz |
| `_extract_answered_question_codes` | Pusty payload, wypełniony payload |

**Funkcje z DB (integration tests):**

| Przypadek testowy | Weryfikacja |
|-------------------|-------------|
| `submit_patient_intake_form` — brak wymaganej zgody | `RequiredConsentMissingError` raised |
| `submit_patient_intake_form` — brak wymaganej anamnezy | Odpowiedni wyjątek |
| `save_intake_signature` — za duży plik | `InvalidSignatureError` |
| `save_intake_signature` — nieprawidłowy format data URL | `InvalidSignatureError` |
| `submit_patient_intake_form` — happy path (idempotentność przy ponownym wywołaniu) | Brak duplikatu, status queue entry zmieniony |
| `get_intake_form_context` — formularz z wieloma zgodami i pytaniami anamnezy | Poprawna struktura kontekstu |

**Mockowanie:** `tmp_media` (podpisy na dysku), `freeze_time`, `patch('apps.intake.services.create_audit_event')`.

### 1.4. `apps/medical/services.py` (~63%, 93 miss)

**Ryzyko:** Stan dokumentu medycznego, publikacja PDF, integralność outboxa.

**Uwaga architekturalna:** Moduł importuje `get_intake_form_context` z intake i prywatną `_try_delete_file` z outbox. Testy tego modułu są de facto testami integracyjnymi obejmującymi 3 aplikacje. Akceptujemy to jako koszt — refaktoryzacja coupling jest osobnym zadaniem.

| Przypadek testowy | Typ | Weryfikacja |
|-------------------|-----|-------------|
| `save_draft_document_version` — tworzenie nowego draftu | Integration | Wersja utworzona, status DRAFT |
| `save_draft_document_version` — aktualizacja istniejącego draftu | Integration | Brak nowej wersji, dane zaktualizowane |
| `publish_document_version` — brakujące wymagane pola | Integration | Wyjątek z walidacji payload |
| `publish_document_version` — happy path | Integration | Status PUBLISHED, outbox event created |
| `publish_document_version` — idempotentność (ponowna publikacja) | Integration | Brak duplikatu, ten sam wynik |
| `revoke_document_version` — usunięcie pliku PDF (mock `_try_delete_file`) | Integration | Status REVOKED, plik "usunięty" |
| `list_doctor_work_queue` — różne stany dokumentów | Integration | Poprawna denormalizacja w odpowiedzi |

**Mockowanie:** `patch('apps.medical.services._try_delete_file')`, `freeze_time`, pełny setup intake fixtures.

---

## Faza 2 — Parsowanie i walidacja (wysoki ROI, niski koszt utrzymania)

### 2.1. `apps/reception/xlsx_import.py` — warstwa pure functions (~70%, 114 miss)

**Podejście:** Ten moduł ma najlepszy stosunek kodu testowalnego do kosztu — duża warstwa czystych funkcji parsujących.

**Unit tests (bez DB, bez plików XLSX):**

| Funkcja | Przypadki |
|---------|-----------|
| `_normalize_header_cell` | Whitespace, case, diakrytyki |
| `_find_header_indices` | Kompletne nagłówki, brakujące kolumny |
| `_parse_time` | Poprawny format, nieprawidłowy, pusty |
| `_parse_date` | Formaty DE/PL, brak roku (domyślny), nieparsowalna wartość |
| `_split_full_name` | "Kowalski, Jan", "Jan Kowalski", jednowyrazowe, puste |
| `_title_case_name` | Wieloczłonowe nazwiska, dywisy |
| `_normalize_site_name` / `_cleanup_clinic_name` | Warianty nazw klinik |
| `_validate_headers` | Brakujące wymagane kolumny, dodatkowe kolumny |
| `_extract_file_metadata` | Poprawne wiersze, puste wiersze, brak nagłówków |
| `_normalize_row` | Poprawny wiersz, brakujące pola, złe typy |

**Dlaczego osobno:** Te funkcje to czysta logika string → struktura. Testy są szybkie (~0ms każdy), deterministyczne i odporne na zmiany w ORM.

**Integration tests (z DB, z plikami `.xlsx`):**

| Przypadek testowy | Weryfikacja |
|-------------------|-------------|
| `process_patient_xlsx_import_batch` — poprawny arkusz z 5 wierszami | 5 pacjentów + wpisy w kolejce |
| `process_patient_xlsx_import_batch` — błędne typy danych w wierszach | Błędy zapisane do `PatientImportError`, reszta przetworzona |
| `process_patient_xlsx_import_batch` — pusty arkusz | Informacyjny wynik, brak wyjątku |
| `enqueue_patient_xlsx_import` — mock `enqueue()` | Batch created, task enqueued |

**Pliki fixture XLSX:** Tworzyć programowo w teście za pomocą `openpyxl.Workbook()` — NIE commitować plików binarnych do repozytorium.

### 2.2. `apps/core/api_utils.py` (~75%, 36 miss)

| Przypadek testowy | Typ | Weryfikacja |
|-------------------|-----|-------------|
| Walidacja body z brakującymi polami | Unit | Odpowiedni komunikat błędu |
| Paginacja — parametry poza zakresem | Unit | Domyślne wartości |
| Paginacja — poprawne parametry | Unit | Poprawne offset/limit |
| Obsługa `DomainError` w middleware/handler | Unit | Poprawny HTTP status + JSON |

---

## Faza 3 — API endpoints (ochrona kontraktu)

### Podejście

Testy API weryfikują **kontrakt HTTP** (status codes, kształt odpowiedzi, autoryzację), nie logikę biznesową — ta jest pokryta w fazie 1. Używać `auth_client` fixture z `conftest.py`.

### 3.1. `apps/intake/api_views.py` (~59%, 97 miss)

| Przypadek testowy | Weryfikacja |
|-------------------|-------------|
| Każdy endpoint bez autentykacji | 403 lub 302 |
| Każdy endpoint z niewłaściwą rolą | 403 |
| POST z nieprawidłowym payloadem | 400 + struktura błędu |
| GET/POST happy path z rolą Reception | 200/201 + kształt odpowiedzi |

### 3.2. `apps/medical/api_views.py` (~59%, 130 miss)

Analogiczny wzorzec jak intake. Dodać:

| Przypadek testowy | Weryfikacja |
|-------------------|-------------|
| GET nieistniejącego zasobu | 404 |
| Operacja na dokumencie w niedozwolonym stanie | 400/409 + komunikat |

### 3.3. `apps/reception/api_views_split/` (queues ~60%, dictionaries ~63%, patients ~63%)

| Moduł | Kluczowe przypadki |
|-------|-------------------|
| `queues.py` | Lista kolejki; zmiana statusu — niedozwolone przejście; filtry query params |
| `dictionaries.py` | CRUD sukces; walidacja błędnych danych |
| `patients.py` | Wyszukiwanie; aktualizacja; ograniczenia dostępu |

### 3.4. `apps/operations/api_views.py` (~42%, 59 miss), `apps/outbox/api_views.py` (~68%, 35 miss)

Gałęzie błędów wskazane w kolumnie `Missing` raportu coverage — uzupełnić testy 400/404/403.

---

## Faza 4 — Widoki HTML i reszta (niski priorytet)

Realizować **tylko jeśli** po fazach 1-3 nadal brakuje do celu. Testy widoków HTML mają najgorszy stosunek wartości do kosztu utrzymania.

| Moduł | Podejście |
|-------|-----------|
| `tablet_views.py` (~38%, 121 miss) | Smoke tests: GET kluczowych URL po zalogowaniu → 200; anonim → redirect |
| `doctor_views.py` (~33%, 80 miss) | Jak wyżej |
| `intake/views.py` (~28%, 47 miss) | Jak wyżej |
| `patient_results/views.py` (~17%, 73 miss) | Lista + download — 200/404/410 |
| Admin (`medical/admin.py`, `reception/admin.py`) | Tylko jeśli konieczne; niski priorytet |

### Pliki celowo wyłączone z pokrycia (nie testować)

| Plik | Powód |
|------|-------|
| `cogitomedica/wsgi.py` | Entry point Django, zero logiki |
| `cogitomedica/asgi.py` | Entry point Django, zero logiki |
| `cogitomedica/formats/pl/formats.py` | Stałe lokalizacyjne |
| `cogitomedica/admin_callbacks.py` | Callbacki admina, niekrytyczne |

---

## Wymagania technologiczne

### Stack

- **Python 3.13**, **Django**, **pytest** + **pytest-django** + **pytest-cov**.
- Testy w `tests.py`, `api_tests.py`, `test_*.py` (istniejąca konwencja).
- `conftest.py` w katalogu głównym (nowy).

### Wymagane narzędzia (dodać do `requirements-dev.txt`)

| Narzędzie | Cel | Status |
|-----------|-----|--------|
| `model_bakery` | Generacja danych testowych bez boilerplate | **Nowy** |
| `freezegun` | Deterministyczne testy zależne od czasu | **Nowy** |
| `diff-cover` | Gate na pokrycie nowego kodu w CI | **Nowy** |

### Narzędzia już obecne (nie zmieniać)

| Narzędzie | Cel |
|-----------|-----|
| `unittest.mock` | Mockowanie I/O, tasków, zewnętrznych klientów |
| `django.test.Client` | Testy HTTP |
| `pytest-cov` | Raportowanie pokrycia |

### Struktura testów

- **Unit tests** czystych funkcji → `test_<moduł>.py` per aplikacja (np. `test_xlsx_parsing.py`).
- **Integration tests** z DB → istniejące `tests.py` per aplikacja.
- **API tests** → istniejące `api_tests.py` per aplikacja.
- **Fixture XLSX** → generowane programowo w teście (`openpyxl.Workbook()`), **nie** pliki binarne w repo.

---

## Ochrona przed regresją i flaky testami

### SLA na czas testów

Dodać do CI krok z timeoutem:

```yaml
- name: Tests
  run: python -m pytest -q --tb=short --cov --cov-report=xml --cov-report=term-missing
  timeout-minutes: 8
```

Jeśli suite przekroczy 8 minut, to jest problem do rozwiązania, nie normalna sytuacja.

### `setUpTestData` zamiast `setUp`

W nowych testach `TestCase` używać `setUpTestData` (class-level, raz per klasa) zamiast `setUp` (per test) dla danych, które nie są modyfikowane w testach. Różnica w szybkości: **10-50x** dla klas z wieloma testami.

### Zamrażanie czasu

Każdy test, który testuje logikę zależną od `timezone.now()`, **musi** używać `@freeze_time(...)`. Nie jest to rekomendacja — to wymaganie.

### Nie mockować tego, czego nie musisz

Preferować testy z prawdziwą bazą danych nad mockami ORM. Mock `Model.objects.filter(...)` łamie się przy każdej zmianie query i nie testuje prawdziwego zachowania. Mockować tylko:
- I/O zewnętrzne (pliki, HTTP, kolejki zadań),
- `timezone.now()`,
- `create_audit_event` (jeśli nie jest przedmiotem testu).

---

## Znane ryzyka i ograniczenia planu

| Ryzyko | Mitigacja |
|--------|-----------|
| Branch coverage obniży % po włączeniu — frustracja zespołu | Komunikacja: nowa baseline to informacja, nie regres |
| `model_bakery` generuje dane niezgodne z walidatorami modelu | Definiować `baker.prepare(..., field=value)` dla pól z custom walidacją |
| Nowy kod produkcyjny obniża % szybciej niż testy go podnoszą | Diff-cover gate (90% na nowy kod) chroni przed tym |
| Testy `anonymization.py` wymagają złożonego setup grafu modeli | Zainwestować w dedykowany fixture w `apps/reception/conftest.py` — zwróci się wielokrotnie |
| Cross-app coupling (`medical` → `intake` → `reception`) | Akceptujemy koszt testów integracyjnych; refaktoryzacja coupling to osobny projekt |
| Flaky testy dat/czasu | `freezegun` obowiązkowy, nie opcjonalny |

---

## Mierzalne kamienie milowe

| Kamień milowy | Kryterium zakończenia | Szacunkowy efekt |
|---------------|----------------------|------------------|
| Faza 0 zakończona | `conftest.py` istnieje, branch coverage włączone, `diff-cover` w CI, `fail_under` ustawione na baseline | % może spaść — to jest OK |
| Faza 1 zakończona | Testy anonymization, document_services, intake/services, medical/services wg tabel powyżej | +6-8pp pokrycia gałęzi |
| Faza 2 zakończona | Unit testy xlsx_import pure functions, api_utils | +3-4pp |
| Faza 3 zakończona | API contract tests dla intake, medical, reception endpoints | +4-6pp |
| Faza 4 (opcjonalna) | Smoke tests widoków HTML | +2-3pp |

**Cel docelowy:** ≥80% branch coverage (odpowiednik ~85-88% statement coverage) osiągnięty stabilnie, z mechanizmem diff-cover chroniącym przed regresją.
