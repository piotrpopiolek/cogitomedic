---
name: pdf-intake-consents-signature
overview: Asynchroniczne generowanie PDF intake (zgody + ankieta + podpis) uruchamiane po zapisie pacjenta, bez SMS i bez sekcji lekarskiej Befund.
todos: []
isProject: true
---

# Plan: Intake PDF (zgody + ankieta + podpis) jako osobny proces

## 1. Decyzje wejściowe (zaakceptowane)

1. Tworzymy **osobny plik planu** i osobny proces techniczny względem Befund.
2. PDF intake ma zawierać:
  - listę zgód pacjenta,
  - ankietę medyczną (anamnesis),
  - podpis pacjenta.
3. Generacja ma być **asynchroniczna** w obecnym wzorcu outbox.
4. Start procesu następuje **wyłącznie**, gdy `PatientIntakeForm.status == SUBMITTED`.
5. Łańcuch procesu intake-PDF:
  - `GENERATE_PDF -> HIDRIVE_UPLOAD`
  - **bez SMS**.
6. Dokument intake-PDF jest **bez części lekarskiej Befund**.
7. Język intake-PDF ma być zgodny z językiem, w którym pacjent wypełniał formularz (`form_locale`).
8. Język generowania PDF ma być utrwalony na poziomie `PatientIntakeForm` (niemutowalny po `SUBMITTED`).
9. Dla intake-PDF **nie budujemy opcji podglądu**.
10. Befund-PDF i intake-PDF to **osobne procesy biznesowe i techniczne**.
11. Konsumentem dokumentu są rejestracja i administratorzy (dedykowany moduł listy/pobierania dokumentów intake).

---

## 2. Cel funkcjonalny

Po przejściu formularza pacjenta do stanu `SUBMITTED` system automatycznie generuje i archiwizuje w HiDrive dokument intake-PDF zawierający komplet danych pacjenta z procesu tabletowego:

- zgody,
- odpowiedzi ankietowe,
- podpis.

Dokument ma być gotowy niezależnie od późniejszego procesu lekarza i publikacji Befund.

---

## 3. Zakres i granice

### In scope

- Asynchroniczny pipeline intake-PDF (`GENERATE_PDF -> HIDRIVE_UPLOAD`).
- Render PDF z danych:
  - `patient_intake_form`,
  - `patient_intake_consent`,
  - `anamnesis_payload`,
  - `signature_file_path` / `signature_sha256`.
- Lokalizacja treści dokumentu wg `form_locale`.
- Upload do HiDrive.
- Retry / failed / observability dla nowego procesu.

### Out of scope

- SMS dla intake-PDF.
- Preview intake-PDF.
- Sekcja lekarska Befund w tym dokumencie.
- Zmiana istniejącego procesu publish Befund poza niezbędną separacją.

---

## 4. Projekt techniczny (docelowy)

### 4.1. Oddzielenie procesów

- Utrzymać obecny proces Befund-PDF bez zmian semantycznych.
- Dodać osobny proces intake-PDF uruchamiany po zapisie pacjenta.
- Nie łączyć kolejek ani statusów procesów intake i Befund w jeden stan domenowy.

### 4.2. Outbox / eventy

Decyzja:

- wykorzystujemy **istniejący mechanizm** `OutboxEvent`,
- dodajemy dedykowane typy eventów:
  - `GENERATE_INTAKE_PDF`,
  - `HIDRIVE_UPLOAD_INTAKE_PDF`.
- bez zmian w architekturze outbox poza nowymi typami i handlerami.

### 4.3. Trigger procesu (jednoznaczny)

- Trigger enqueue następuje tylko przy zmianie `PatientIntakeForm` na `SUBMITTED`.
- Brak triggera na częściowy zapis roboczy.
- W tym samym commit transakcyjnym:
  - utrwalenie danych formularza,
  - utrwalenie `intake_pdf_locale` na `PatientIntakeForm`,
  - utworzenie wpisu outbox `GENERATE_INTAKE_PDF`.

### 4.4. Język dokumentu (niemutowalny)

- Źródło prawdy: pole na `PatientIntakeForm` (np. `intake_pdf_locale`), ustawiane przy `SUBMITTED`.
- Po `SUBMITTED` pole jest niemutowalne (walidacja model/service + testy).
- Renderer PDF ma używać locale pacjenta, nie `publish_locale` lekarza.
- Obsługa `de/en/pl`.

### 4.5. Zawartość PDF

Minimalny układ:

1. Nagłówek dokumentu i metadane (data, identyfikator formularza, pacjent).
2. Sekcja zgód:
  - kod/nazwa zgody,
  - status akceptacji,
  - timestamp akceptacji.
3. Sekcja ankiety:
  - pytanie,
  - odpowiedź/odpowiedzi,
  - opcjonalny free text.
4. Sekcja podpisu:
  - osadzony obraz podpisu,
  - `signature_sha256`,
  - `submitted_at`.

### 4.6. Przechowywanie i statusy

- Brak nowego agregatu procesu; używamy istniejących rekordów i statusów outbox.
- Metadane pliku intake-PDF zapisujemy w bycie intake (lub dedykowanej relacji 1:1 do intake), bez użycia `medical_document_version`.
- Rejestrować:
  - status generacji,
  - ścieżkę lokalną,
  - checksum,
  - status uploadu do HiDrive.

### 4.7. Konsumpcja dokumentu bez SMS/preview

- Rejestracja i administratorzy dostają moduł listy dokumentów intake:
  - filtrowanie po dacie, pacjencie, statusie przetwarzania,
  - podgląd metadanych i pobranie pliku z HiDrive,
  - obsługa przypadków błędnych (`FAILED`, `DEAD_LETTER`) z akcją retry.
- Moduł stanowi operacyjny punkt weryfikacji jakości dokumentu i obsługi reklamacji.

---

## 5. Walidacja i bezpieczeństwo

1. Przed enqueue:
  - formularz w stanie finalnym,
  - obecny podpis,
  - komplet wymaganych zgód i wymaganych odpowiedzi.
2. Render tekstów z bezpiecznym escapowaniem.
3. Podpis:
  - walidacja istnienia pliku,
  - walidacja integralności przez `signature_sha256`.
4. Idempotencja:
  - ponowny submit nie tworzy nieograniczonej liczby identycznych eventów.
5. Rozszerzenie bezpieczeństwa podpisu (rekomendowane):
  - dodać `signed_at`, `signed_by_role=TABLET`, `tablet_device_id` i `session_id` do metadanych podpisu,
  - zapisywać hash kanoniczny materiału dowodowego (podpis + kluczowe pola formularza + locale + timestamp),
  - logować zdarzenie audytowe podpisu i submitu (kto/system, kiedy, z jakiej sesji/urządzenia),
  - opcjonalnie dodać serwerowy znacznik czasu (TSA) jako etap 2, jeśli wymagania prawne będą rosły.

### 5.1 Snapshot danych (niemutowalność treści)

- Przy `SUBMITTED` zapisujemy niemutowalny snapshot:
  - treści zgód zaakceptowanych przez pacjenta,
  - etykiety pytań/odpowiedzi ankiety w wybranym locale,
  - mapowanie kod -> label użyte do renderu intake-PDF.
- PDF jest renderowany z tego snapshotu, nie z żywych słowników runtime.

---

## 6. Plan wdrożenia etapami

### Etap A: kontrakt i model procesu

- Dodać pola `intake_pdf_locale` i (jeśli przyjęte) `intake_snapshot` do `PatientIntakeForm`.
- Doprecyzować miejsce przechowywania statusów/metadanych intake-PDF.
- Dodać nowe typy eventów outbox i mapping workerów.
- Ustalić regułę idempotencji dla triggera po `SUBMITTED`.

### Etap B: generacja intake-PDF

- Zbudować warstwę kontekstu danych intake.
- Dodać szablon HTML/CSS intake-PDF (bez Befund).
- Dodać renderowanie wielojęzyczne wg `form_locale`.

### Etap C: pipeline asynchroniczny

- Worker `GENERATE_INTAKE_PDF`.
- Worker `HIDRIVE_UPLOAD_INTAKE_PDF`.
- Retry, backoff, status `FAILED`/`DEAD_LETTER` i audyt.
- Brak workerów SMS dla intake-PDF.

### Etap D: testy

- Unit: mapowanie zgód/ankiety/podpisu do kontekstu PDF.
- Unit: wybór języka z `intake_pdf_locale`.
- Integracja: `SUBMITTED` -> outbox -> PDF -> upload HiDrive.
- Integracja: brak podpisu / uszkodzony plik podpisu -> failure path.
- Integracja: wielokrotny submit nie tworzy wielu eventów (`idempotency`).
- Integracja: snapshot treści nie zmienia się po późniejszej zmianie słowników/treści zgód.
- E2E: pełen przepływ tabletowy bez udziału lekarza.

### Etap E: rollout

- Migracje i deploy.
- Smoke test na Dockerze.
- Checklista operacyjna monitoringu i rollbacku.

---

## 7. Metryki i observability

- Liczba zdarzeń `GENERATE_INTAKE_PDF` (pending/processing/failed/dead letter).
- Czas generacji intake-PDF p95/p99.
- Skuteczność uploadu intake-PDF do HiDrive.
- Wiek najstarszego oczekującego intake event.

### 7.1. SLO/alerty/ownership (proponowane)

- SLO:
  - 99% intake-PDF wygenerowanych i wysłanych do HiDrive w <= 5 minut od `SUBMITTED`,
  - `FAILED + DEAD_LETTER` < 1% dziennie.
- Alerty:
  - krytyczny: `oldest_pending_age_seconds > 600` przez 10 minut,
  - krytyczny: `dead_letter_count > 0` dla `GENERATE_INTAKE_PDF` lub `HIDRIVE_UPLOAD_INTAKE_PDF`,
  - ostrzegawczy: skuteczność uploadu < 98% w oknie 1h.
- Ownership:
  - owner operacyjny: zespół backend/on-call,
  - owner biznesowy: recepcja + administracja (akceptacja jakości dokumentu w module operacyjnym),
  - runbook: procedura retry, ręcznej weryfikacji i eskalacji.

### 7.2. Wydajność i pojemność (proponowane)

- Capacity planning:
  - oszacować max submitów/h i średni rozmiar PDF,
  - wyliczyć CPU-time na render i I/O na upload.
- Ochrona systemu:
  - limit równoległych renderów PDF (worker concurrency),
  - kolejka priorytetowa lub osobna pula workerów dla intake-PDF,
  - backpressure przy skokach ruchu (kontrolowane opóźnienie zamiast lawiny błędów).
- Budżet operacyjny:
  - dashboard kosztów storage/transfer dla intake-PDF,
  - polityka retencji zgodna z wymaganiami prawnymi.

---

## 8. Kryteria akceptacji

1. Po zapisie pacjenta system automatycznie uruchamia asynchroniczny proces intake-PDF.
2. Intake-PDF zawiera zgody, ankietę i podpis.
3. Intake-PDF nie zawiera części lekarskiej Befund.
4. Intake-PDF jest generowany w języku formularza pacjenta (`form_locale`).
5. Proces kończy się na uploadzie do HiDrive (bez SMS).
6. Brak podglądu intake-PDF.
7. Proces intake jest logicznie i operacyjnie oddzielony od procesu Befund.

---

## 9. Pytania do domknięcia przed implementacją (rozwinięte)

1. **Czy trigger to wyłącznie submit, a nie każde „zapisz”?**
  - Decyzja: wyłącznie przejście `PatientIntakeForm -> SUBMITTED`.
  - Konsekwencja: endpointy zapisu roboczego nie enqueue'ują outbox.
  - Test: brak eventu dla draft save, obecność eventu dla submit.
2. **Gdzie zapisujemy niemutowalny snapshot treści?**
  - Decyzja: snapshot w `PatientIntakeForm` (np. `intake_snapshot_json` + `intake_pdf_locale`).
  - Zakres snapshotu: zgody, pytania, odpowiedzi, mapowanie kod->label, metadane podpisu.
  - Test: zmiana słowników po submit nie zmienia kolejnego renderu historycznego dokumentu.
3. **Jaki jest idempotency key i constrainty DB?**
  - Decyzja: klucz idempotencji oparty o `intake_form_id` + `event_type`.
  - Egzekucja: unikalność outbox dla pary (`aggregate_id=intake_form_id`, `event_type=GENERATE_INTAKE_PDF`) lub dedykowany unique index zgodny z aktualnym modelem.
  - Test: wielokrotny submit nie tworzy duplikatów eventu.
4. **Jaki model wersjonowania intake-PDF przy korektach po submit?**
  - Decyzja bazowa: po submit formularz jest zamknięty (brak edycji), brak nowych wersji.
  - Wariant awaryjny: jeśli biznes dopuści korektę, tworzymy nową wersję intake-PDF z pełnym śladem audytu i wskazaniem wersji aktywnej.
  - Do domknięcia z biznesem przed implementacją endpointów korekcyjnych.
5. **Kto konsumuje dokument i jak obsługujemy reklamacje?**
  - Decyzja: rejestracja i administratorzy przez dedykowany moduł.
  - Proces: wyszukanie dokumentu, pobranie, sprawdzenie metadanych (locale, podpis, timestamp), retry przy błędach technicznych.
  - Runbook: klasyfikacja reklamacji (błędny język, brak podpisu, brak uploadu) + ścieżka eskalacji.
6. **Jakie SLO/alerty i kto jest ownerem on-call?**
  - Decyzja: SLO/alerty z sekcji 7.1.
  - Owner techniczny: backend on-call.
  - Owner operacyjny: rejestracja/admin monitorujący moduł dokumentów intake.
  - Warunek go-live: dashboard + alerting + runbook aktywne.

