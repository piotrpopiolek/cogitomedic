---
name: pdf-intake-consents-signature
overview: Asynchroniczne generowanie PDF intake (zgody + ankieta + podpis) uruchamiane po zapisie pacjenta, bez SMS i bez sekcji lekarskiej Befund.
todos:
  - id: 38a2676b-b436-43a2-a731-8449ef93e2ac
    content: ""
    status: pending
  - id: 7368b6ee-eabb-459c-9c4d-67a59025290d
    content: ""
    status: pending
  - id: 5d91f239-241d-4e44-bd7b-541ce91b6036
    content: ""
    status: pending
  - id: 6be729d4-2cb1-4f31-85cb-edc08649b311
    content: ""
    status: pending
  - id: cd8d7bb5-743b-47c4-a972-68f5d60177cb
    content: ""
    status: pending
  - id: 57a23ee8-ac79-475c-9869-9eb0b28adcac
    content: ""
    status: pending
  - id: f4651026-5a6c-49f7-8842-f63bf0639460
    content: ""
    status: pending
  - id: 655484e4-c4fd-4c89-a8da-6b2e488e51d4
    content: ""
    status: pending
  - id: ab33086e-814f-4de0-aedb-48819835bb08
    content: ""
    status: pending
  - id: 9ea7b207-9295-4cf6-aa21-038bc6fd45b0
    content: ""
    status: pending
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
4. Start procesu ma następować **automatycznie po kliknięciu "zapisz" przez pacjenta**.
5. Łańcuch procesu intake-PDF:
  - `GENERATE_PDF -> HIDRIVE_UPLOAD`
  - **bez SMS**.
6. Dokument intake-PDF jest **bez części lekarskiej Befund**.
7. Język intake-PDF ma być zgodny z językiem, w którym pacjent wypełniał formularz (`form_locale`).
8. Dla intake-PDF **nie budujemy opcji podglądu**.
9. Befund-PDF i intake-PDF to **osobne procesy biznesowe i techniczne**.

---

## 2. Cel funkcjonalny

Po zakończeniu zapisu formularza pacjenta system ma automatycznie wygenerować i zarchiwizować w HiDrive dokument intake-PDF zawierający komplet danych pacjenta z procesu tabletowego:

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

Rekomendacja:

- dodać dedykowane typy eventów:
  - `GENERATE_INTAKE_PDF`,
  - `HIDRIVE_UPLOAD_INTAKE_PDF`.

Powód: jednoznaczność operacyjna i brak mieszania semantyki z procesem Befund.

### 4.3. Trigger procesu

- Trigger enqueue po akcji pacjenta "zapisz" (w praktyce po zapisie końcowym/submit formularza, gdy dostępne są zgody + anamnesis + podpis).
- W tym samym commit:
  - utrwalenie danych formularza,
  - utworzenie wpisu outbox `GENERATE_INTAKE_PDF`.

### 4.4. Język dokumentu

- Źródło prawdy: `patient_form_session.form_locale` (lub utrwalony odpowiednik na intake form, jeśli już istnieje).
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

- Osobne pola statusowe dla intake-PDF (rekomendowane) albo odseparowany rekord procesu.
- Rejestrować:
  - status generacji,
  - ścieżkę lokalną,
  - checksum,
  - status uploadu do HiDrive.

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
  - ponowny zapis/submit nie tworzy nieograniczonej liczby identycznych eventów.

---

## 6. Plan wdrożenia etapami

### Etap A: kontrakt i model procesu

- Doprecyzować miejsce przechowywania statusów intake-PDF.
- Dodać nowe typy eventów outbox i mapping workerów.
- Ustalić regułę idempotencji dla triggera po zapisie pacjenta.

### Etap B: generacja intake-PDF

- Zbudować warstwę kontekstu danych intake.
- Dodać szablon HTML/CSS intake-PDF (bez Befund).
- Dodać renderowanie wielojęzyczne wg `form_locale`.

### Etap C: pipeline asynchroniczny

- Worker `GENERATE_INTAKE_PDF`.
- Worker `HIDRIVE_UPLOAD_INTAKE_PDF`.
- Retry, backoff, status `FAILED`/`DEAD_LETTER` i audyt.

### Etap D: testy

- Unit: mapowanie zgód/ankiety/podpisu do kontekstu PDF.
- Unit: wybór języka z `form_locale`.
- Integracja: submit pacjenta -> outbox -> PDF -> upload HiDrive.
- Integracja: brak podpisu / uszkodzony plik podpisu -> failure path.
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

---

## 8. Kryteria akceptacji

1. Po zapisie pacjenta system automatycznie uruchamia asynchroniczny proces intake-PDF.
2. Intake-PDF zawiera zgody, ankietę i podpis.
3. Intake-PDF nie zawiera części lekarskiej Befund.
4. Intake-PDF jest generowany w języku formularza pacjenta (`form_locale`).
5. Proces kończy się na uploadzie do HiDrive (bez SMS).
6. Brak podglądu intake-PDF.
7. Proces intake jest logicznie i operacyjnie oddzielony od procesu Befund.

