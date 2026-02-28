---
name: pdf-intake-consents-signature-final
overview: Asynchroniczne generowanie dwujęzycznego PDF z danymi Intake (zgody, ankieta, podpis) oparte na Hard Snapshot, dedykowanym agregacie (IntakeDocumentVersion) i niezawodnej idempotencji.
todos:
  - id: db-models
    content: "Modele bazy: Dodać tabele IntakeDocumentVersion oraz IntakeOutboxEvent w modelu bazy danych (wraz z migracjami)."
    status: pending
  - id: idempotency-lock
    content: "Endpoint Submit: Zabezpieczyć POST /submit warunkiem optimistic locking (idempotencja)."
    status: pending
  - id: hard-snapshot
    content: "Hard Snapshot: Zaimplementować tworzenie niezmiennego snapshot_payload z tekstami zgód (DE/Locale) i podpisem base64."
    status: pending
  - id: pdf-renderer
    content: "Renderer PDF: Stworzyć dwujęzyczny szablon HTML Intake-PDF oparty w 100% na danych ze snapshotu."
    status: pending
  - id: outbox-pipeline
    content: "Outbox Pipeline: Skonfigurować workery GENERATE_INTAKE_PDF i HIDRIVE_UPLOAD_INTAKE_PDF."
    status: pending
  - id: hidrive-folders
    content: "HiDrive: Dopasować docelowe ścieżki (foldery) w systemie zewnętrznym, by Intake i Befund trafiały pod to samo ID pacjenta."
    status: pending
  - id: tests-and-metrics
    content: "Testy: Zaimplementować scenariusze unit i integracyjne dla ścieżki Intake-PDF (w tym mocki błędów i weryfikacja dwujęzyczności)."
    status: pending
isProject: false
---

# Plan: Intake PDF (zgody + ankieta + podpis) – Bezpieczna Architektura

## 1. Decyzje wejściowe (zaakceptowane)

1. Tworzymy **osobny proces techniczny** względem Befund.
2. PDF intake ma zawierać: listę zgód pacjenta, ankietę medyczną (anamnesis) i podpis pacjenta (bez sekcji lekarskiej).
3. Generacja ma być **asynchroniczna** (Outbox). Start procesu po finalnym zapisie (submit) pacjenta na tablecie.
4. Łańcuch procesu: `GENERATE_INTAKE_PDF -> HIDRIVE_UPLOAD_INTAKE_PDF` (brak powiadomień SMS).
5. **Dwujęzyczność**: PDF jest generowany dwujęzycznie (Niemiecki + język wybrany przez pacjenta `form_locale`), aby dokument był legalny w DE i zrozumiały dla pacjenta.
6. **Brak opcji podglądu** dla intake-PDF.
7. **Wspólny folder archiwum**: Pliki Intake i Befund trafiają do tego samego logicznego folderu pacjenta w HiDrive.

---

## 2. Architektura i projekt techniczny (Docelowy)

Zaprojektowana w odpowiedzi na krytyczne ryzyka technologiczne i operacyjne, w pełni odizolowana od Befund i gwarantująca prawną niezmienność (auditability).

### 2.1. Rozwiązanie konfliktu Outbox i Statusów (Osobny Agregat)

- **Nowy model `IntakeDocumentVersion`**: Odpowiednik `MedicalDocumentVersion`, powiązany 1:1 z `PatientIntakeForm` (per wygenerowana wersja). Przechowuje statusy operacyjne (`pdf_generation_status`, `hidrive_sent`, `pdf_local_path`). Zapewnia czystość tabeli domenowej formularza.
- **Nowy model `IntakeOutboxEvent`**: Dedykowana tabela outboxowa połączona kluczem obcym (FK) z `IntakeDocumentVersion`. Nie psujemy relacyjnej integralności starego `outbox_event` (który pozostaje zarezerwowany dla `MedicalDocumentVersion`).
- Oba procesy mogą współdzielić bazowy kod workera PDF, ale operują na niezależnych tabelach.

### 2.2. Rozwiązanie utraty podpisu i falsyfikacji zgód (Hard Snapshot)

- W momencie transakcji `POST /submit` (gdy pacjent kończy proces) backend tworzy **Hard Snapshot**.
- Tworzony jest rekord `IntakeDocumentVersion` z dużym obiektem JSON w polu `snapshot_payload`.
- **Zgody i ankiety**: Do JSON-a wczytywana jest *aktualna w tej milisekundzie* pełna treść tekstowa zgód i pytań (w języku DE oraz języku pacjenta).
- **Podpis**: System upewnia się, że plik podpisu istnieje, odczytuje go i wbudowuje do `snapshot_payload` jako czysty `base64`.
- **Zasada**: Worker asynchroniczny czyta **wyłącznie ze snapshotu**. Zapewnia to 100% odzwierciedlenie tego, co pacjent fizycznie zaakceptował.

### 2.3. Rozwiązanie idempotencji na tablecie (Optimistic Locking)

- Endpoint `POST /submit` wykonuje warunkowy update w bazie:
`UPDATE patient_intake_form SET form_status = 'SUBMITTED' WHERE id = X AND form_status = 'IN_PROGRESS'`
- Jeśli pacjent kliknie "Zapisz" kilkukrotnie (lagi sieci), tylko pierwszy request faktycznie zmieni stan, utworzy `IntakeDocumentVersion` i zakolejkuje event do `IntakeOutboxEvent`. Kolejne odbiją się od tego warunku i zwrócą idempotentny sukces bez tworzenia duplikatów.

### 2.4. Język dokumentu i Archiwum

- **Dwujęzyczny szablon**: Układ np. `Tytuł: Einverständniserklärung / Zgoda na badanie`. Źródło dla języka pacjenta to `patient_form_session.form_locale`.
- **Struktura HiDrive**: Ścieżka archiwizacji np.: `/Patients/{patient_id}/{date}_intake.pdf` oraz `/Patients/{patient_id}/{date}_befund.pdf`, co ułatwi skompletowanie teczki pacjenta.

---

## 3. Plan wdrożenia etapami

### Etap A: Modele bazy danych i infrastruktura

- Utworzyć modele `IntakeDocumentVersion` oraz `IntakeOutboxEvent` (+ migracje DB).
- Dodać typy eventów outbox: `GENERATE_INTAKE_PDF`, `HIDRIVE_UPLOAD_INTAKE_PDF`.

### Etap B: Transakcja Submit (Snapshot + Idempotencja)

- Rozbudować `POST /submit`: zaimplementować Optimistic Locking.
- Budowa i zapis `snapshot_payload` w `IntakeDocumentVersion` z treściami zgód (DE+Locale) i obrazkiem podpisu (base64).
- Zakolejkowanie wygenerowanego snapshotu do `IntakeOutboxEvent`.

### Etap C: Renderer PDF

- Przygotować szablon HTML/CSS wyłącznie dla sekcji intake (nagłówek pacjenta, lista zgód, ankieta, wbudowany podpis base64).
- Mechanizm renderujący musi iterować po `snapshot_payload` i wypluwać dwujęzyczne etykiety bez odwoływania się do bazy live.

### Etap D: Pipeline Asynchroniczny i HiDrive

- Skonfigurować worker przetwarzający `IntakeOutboxEvent`.
- Rozszerzyć logikę uploadu do HiDrive o spójne partycjonowanie w folderze pacjenta (obsługa struktury folderów per pacjent).

### Etap E: Testy i Rollout

- **Unit**: Mapowanie do Hard Snapshot, renderowanie dwujęzycznego HTML, poprawne osadzenie podpisu base64.
- **Integracja**: `submit` formularza generujący poprawnie outbox event, worker tworzący plik z pełnym uploadem.
- **Idempotencja**: Test API z jednoczesnymi żądaniami `POST /submit`.
- Migracje bazodanowe, dodanie monitoringu (logi, metryki p95/p99) dla nowej tabeli outboxa.

---

## 4. Kryteria akceptacji

1. Akcja pacjenta `Zapisz` idempotentnie uruchamia asynchroniczny proces dla Intake-PDF.
2. Powstaje dedykowany rekord `IntakeDocumentVersion` trzymający `snapshot_payload` z danymi (zgody, ankieta, podpis base64).
3. Wygenerowany Intake-PDF jest w pełni dwujęzyczny (DE + język tabletu).
4. Dokument uploaduje się bezbłędnie do folderu pacjenta na koncie HiDrive (obok ewentualnego Befund).
5. Architektura `outbox_event` procesu medycznego nie została naruszona.

