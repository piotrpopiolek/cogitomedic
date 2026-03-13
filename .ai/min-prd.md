# Mini PRD – Cogitomedica Digital Consents

**Dla agentów zewnętrznych (bez pełnego kontekstu projektu).**

## Co to jest

Aplikacja webowa do cyfryzacji przyjęć pacjentów, zgód i dokumentacji medycznej w placówce: tablety w poczekalni (pacjent), panel recepcji i lekarza (Django). Języki: **DE, EN, PL**.

## Stack

- **Backend:** Django 6.0.x
- **Zadania w tle:** tylko **Django Tasks** + **Transactional Outbox** (bez django-cron, bez Celery)

## Główne obszary

1. **Recepcja:** lista dzienna (Poczekalnia), CRUD pacjentów, **import z PDF** (format Doctolib) lub awaryjny Excel; unikalność pacjenta: `first_name` + `last_name` + `phone` + `date_of_birth`; `Doctolib Patient ID` opcjonalny, ale jeśli jest – unikalny.
2. **Tablet (pacjent):** recepcja wybiera kolejkę i pacjenta (sesja, **bez linków z tokenem**). Pacjent: dane do weryfikacji, ankieta anamnestyczna (Anamnesebogen), zgody, schemat ciała, podpis. Tylko w poczekalni na tablecie.
3. **Lekarz:** formularz medyczny (Befund) – grupy zmian (numery z Wideodermatoskopu), cechy dermatoskopowe, ocena, ryzyko; tekst **generowany z checkboxów, ale edytowalny** („baza, nie klatka”). Szkic vs Opublikowany; publikacja idempotentna (sprawdzenie „publikacja w toku” / `publish_request_id`).
4. **Archiwizacja:** Outbox → generowanie PDF → upload HiDrive (mock F1–2, API F3) → SMS (SMSApi). Retencja: usuwanie PDF z serwera po 30 dniach **tylko gdy** `hidrive_sent` i `sms_sent` true.
5. **Proces udostępniania wyników pacjentowi (4 etapy, RODO/BÄK):**
   - **Krok 1 – SMS logistyczny:** Po publikacji Befund outbox wysyła SMS przez SMSApi. Treść wyłącznie: „Nowa dokumentacja w Cogito” – bez informacji o badaniu czy wyniku (zgodność z prawem).
   - **Krok 2 – Logowanie cross-verification:** Pacjent wchodzi na bezpieczny portal (np. wyniki.cogitomedica.pl). Login = numer telefonu + data urodzenia (zweryfikowane w recepcji przy cyfryzacji). Silna weryfikacja „something you are/know”.
   - **Krok 3 – Dynamiczny OTP:** Po dopasowaniu telefon+DOB w DB system wysyła 6-cyfrowy kod OTP ważny 15 min. MFA / out-of-band – bez fizycznego dostępu do SIM nie przejdzie autoryzacji.
   - **Krok 4 – Dostęp:** Po poprawnej OTP Django serwuje PDF przez HTTPS. Pełna kontrola: logi audytowe (data, godzina, IP), możliwość wycofania publikacji przez lekarza – pacjent po OTP nie zobaczy już błędnego pliku (niemożliwe przy mailu).

## Zasady techniczne (obowiązkowe)

- **Outbox:** jeden mechanizm asynchroniczny (Django Tasks + Outbox). Stany: `PENDING → PROCESSING → PROCESSED` (+ `FAILED`, `DEAD_LETTER`).
- **Idempotentność:** publikacja dokumentu i import nie mogą tworzyć duplikatów (klucze idempotentności, sprawdzanie „w toku”).
- **JSON w DB:** każdy payload ma `schema_version`; walidacja przy zapisie (Pydantic/JSON Schema). Krytyczne dane kliniczne – w kolumnach relacyjnych.
- **Tłumaczenia:** tylko w DB, edytowalne w Django Admin (DE/EN/PL), bez fallbacków w kodzie.
- **Observability:** metryki (outbox, HiDrive, SMS, import), dashboardy (recepcja + Prometheus/Grafana), alerting (Alertmanager), runbooki przy alertach.

## Poza zakresem

Swobodny opis medyczny od pacjenta; BI; bezpośrednie API Doctolib; integracje inne niż HiDrive i SMSApi.

## Kontrakt Befund (medical_payload v1)

- Global + tablica `lesions[]`. Per grupa: `lesion_numbers` (int[]), `dermatoscopic_features`, `clinical_assessment`, `malignancy_risk`, `generated_text`, `edited_text`. Do PDF trafia tekst końcowy (`edited_text` lub `generated_text`).
