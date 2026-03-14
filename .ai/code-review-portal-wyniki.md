# Przegląd kodu – Portal Wyniki (4-etapowy plan)

**Plan:** `.cursor/plans/portal_wyniki_4-etapowy.plan.md`  
**Data:** 2025-03-14  
**Testy:** Wszystkie 15 testów (outbox + patient_results) przechodzą w Dockerze.

---

## 1. Błędy logiczne i bugi

### 1.1 Brak walidacji pustego numeru telefonu w outbox SMS (WYSOKI)

**Lokalizacja:** `apps/outbox/services.py`, linie 124–132

Gdy pacjent ma pusty numer (`None` lub `""`), `adapter.send_sms(to=patient.phone, ...)` wywoła SMSApi z pustym odbiorcą. `format_phone_for_smsapi` zwraca `""`, co może powodować błąd API lub nieoczekiwane zachowanie.

**Rekomendacja:**
```python
patient = version.medical_document.queue_entry.patient
if not (patient.phone or "").strip():
    raise DomainError("Patient has no phone number; cannot send SMS.")
```
Wdrażamy poprawkę, zgłoś błąd zgodnie z przyjętym standardem projektu.

### 1.2 Duplikat zapytania do bazy w download PDF (NISKI)

**Lokalizacja:** `apps/patient_results/api_views.py`, linie 116–120

`get_patient_pdf_version` i `get_patient_pdf_path` oba wywołują `get_patient_pdf_version` – to drugie zapytanie do bazy jest zbędne.

**Rekomendacja:** Zmodyfikować `get_patient_pdf_path(version_id, patient_id)` tak, by przyjmowała opcjonalny obiekt `version`:
```python
def get_patient_pdf_path(version_id: UUID, patient_id: UUID, version: MedicalDocumentVersion | None = None) -> Path | None:
    if version is None:
        version = get_patient_pdf_version(version_id, patient_id)
    ...
```
W widoku przekazywać już pobraną wersję.

Wdrażamy poprawkę

### 1.3 Brak walidacji zakresu daty urodzenia (ŚREDNI)

**Lokalizacja:** `apps/patient_results/api_views.py`, `_parse_date`

Plan przewiduje walidację „DOB w rozsądnym zakresie”. Obecnie akceptowana jest dowolna poprawna data (np. `2030-01-01`), co może prowadzić do błędnych prób logowania.

**Rekomendacja:** Dodać sprawdzenie po parsowaniu:
```python
def _parse_date(s: str | None) -> date | None:
    ...
    d = datetime.strptime(...).date()
    if d > timezone.now().date():
        return None
    if d < timezone.now().date() - timedelta(days=120 * 365):  # np. max 120 lat
        return None
    return d
```
---
Wdrażamy poprawkę

## 2. Luki bezpieczeństwa

### 2.2 CAPTCHA – brak logowania przy błędzie (NISKI)

**Lokalizacja:** `apps/patient_results/services.py`, `_verify_captcha`

Przy błędzie wywołania Turnstile (`except Exception`) zwracane jest `False` bez logowania. Utrudnia to diagnostykę ataków i problemów z integracją.

**Rekomendacja:** Dodać `logger.warning("CAPTCHA verify failed", exc_info=True)` w bloku `except`.

Wdrażamy poprawkę

### 2.3 Pepper OTP – walidacja konfiguracji (NISKI)

Gdy `PATIENT_RESULTS_OTP_PEPPER` jest puste, OTP są hashowane bez peppera, co osłabia ochronę. Warto w trybie produkcyjnym wymuszać ustawienie tego parametru.

Wdrażamy poprawkę

---

## 3. Wydajność

### 3.1 Duplikat zapytania do bazy (patrz 1.2)

## 4. Utrzymanie i dług techniczny

### 4.1 Testy nieuwzględnione w Makefile (NISKI)

**Lokalizacja:** `Makefile`, `test-ci`

W `test-ci` brakuje testów `patient_results`:
```make
python manage.py test apps.core.tests apps.medical.api_tests apps.outbox.tests apps.operations.api_tests
```

Wdrażamy poprawkę

**Rekomendacja:** Dodać `apps.patient_results.tests apps.patient_results.api_tests`.

### 4.2 Niespójność importu normalize_phone (STYL)

**Lokalizacja:** `apps/patient_results/tests.py`

Test importuje `normalize_phone` z `apps.patient_results.services`, który re-eksportuje `phone_utils.normalize_phone`. Lepiej importować bezpośrednio z `apps.reception.phone_utils` dla przejrzystości.

Wdrażamy poprawkę

### 4.3 Normalizacja numeru telefonu a rate limit (ŚREDNI – do rozważenia)

Plan wymaga „jednej normalnej formy” numeru. `normalize_phone` zwraca tylko cyfry, więc:
- `+491762222222` → `491762222222`
- `01762222222` → `01762222222`

To różne stringi – ten sam numer w dwóch formatach może skutkować osobnymi limitami OTP (łącznie 6 zamiast 3 na godzinę). Długoterminowo warto wprowadzić kanoniczną formę (np. zawsze z prefiksem kraju) i używać jej wszędzie.

Wdrażamy poprawkę bez prefiksu kraju, bez + bez 0

---

## 5. Styl kodu i spójność

### 5.1 Obsługa wyjątków w `request_otp` (STYL)

**Lokalizacja:** `apps/patient_results/services.py`, linie 134–147

```python
try:
    with transaction.atomic():
        ...
except Exception:
    raise
```

Blok `try/except` tylko propaguje wyjątek; można go usunąć, aby nie zaciemniać kodu.

Wdrażamy poprawkę

### 5.2 Nagłówek Content-Disposition (DROBNE)

RFC 5987 zaleca escapowanie znaków w `filename*`. Obecna implementacja jest wystarczająca dla ASCII; dla pełnej zgodności można dodać `filename*=UTF-8''...`.

---

## Podsumowanie priorytetów

| Priorytet | Opis |
|-----------|------|
| WYSOKI | Walidacja pustego numeru telefonu w outbox przed wysłaniem SMS |
| ŚREDNI | Walidacja zakresu daty urodzenia (np. przyszłość, >120 lat) |
| ŚREDNI | Streaming PDF zamiast ładowania do pamięci (opcjonalnie) |
| NISKI | Logowanie przy błędzie CAPTCHA |
| NISKI | Dodać testy patient_results do Makefile |
| NISKI | Usunąć zbędny try/except w request_otp |
| NISKI | Optymalizacja – unikać duplikatu zapytania w get_patient_pdf_path |

---

## Testy

```bash
docker compose run --rm web sh -c "python manage.py migrate && python manage.py test apps.outbox.tests apps.patient_results.tests apps.patient_results.api_tests"
```
**Wynik:** 15 testów OK.
