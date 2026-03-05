---
name: ""
overview: ""
todos: []
isProject: false
---

# Plan: Obsługa generowania PDF (Befund)

Plan implementacji **realnego** generowania plików PDF dokumentu medycznego (Befund). Odniesienia: [PRD](.ai/prd.md), [db-plan](.ai/db-plan.md), [api-plan](.ai/api-plan.md).

**Stan wdrożenia (2026-02-22):** Fazy 1–4 zrealizowane: ścieżki względne i MEDIA_ROOT w retencji, builder WeasyPrint (`apps/medical/pdf_builder.py`), integracja GENERATE_PDF w outbox, retencja, metryki (success ratio, P95 latency), health z alertami. HiDrive/SMS pozostają mock. Szczegóły: `.ai/stan-wdrozenia-i-dalej.md`.

---

## 1. Cel i zakres

- **Cel:** Po publikacji wersji dokumentu medycznego system generuje plik PDF zawierający **wyłącznie Befund (część lekarska) oraz dane pacjenta do identyfikacji**, zapisuje go lokalnie, a następnie (w istniejącym łańcuchu outbox) uploaduje do HiDrive i wysyła SMS.
- **Poza zakresem PDF:** Do dokumentu **nie trafiają**: schemat ciała (body_map_data), podpis pacjenta (signature), zgody (consents). Te dane pozostają w systemie (intake form) i nie są renderowane w generowanym PDF.
- **Obecny stan:** W `apps/outbox/services.py` handler `GENERATE_PDF` jest stubem – ustawia `pdf_generation_status=COMPLETED`, `pdf_local_path="/tmp/pdfs/{id}.pdf"` i `pdf_checksum_sha256="a"*64` bez tworzenia pliku. Retencja i HiDrive w kodzie zakładają istnienie pliku.
- **Zakres planu:** (1) definicja treści PDF, (2) źródła danych, (3) wybór technologii generowania, (4) integracja z outbox, (5) ścieżki plików i checksum, (6) obsługa błędów i metryki.

---

## 2. Zawartość PDF (co trafia do dokumentu)

**Do PDF trafiają tylko:**


| Sekcja                      | Źródło danych                                          | Uwagi                                                                                                                                                                                                                                           |
| --------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dane pacjenta**           | `queue_entry.patient`                                  | Imię, nazwisko, data urodzenia, kontakt (nagłówek / identyfikacja).                                                                                                                                                                             |
| **Część medyczna (Befund)** | `medical_document_version.medical_payload` (schema v1) | Zakres badania, Fitzpatrick, ocena globalna, **grupy zmian** (numery Läsion + tekst końcowy per grupa: `edited_text` lub `generated_text`), rekomendacje, ocena końcowa, **podsumowanie** (`summary_edited_text` lub `summary_generated_text`). |


**Nie trafiają do PDF (w tym etapie):** schemat ciała, podpis pacjenta, zgody (ani treść zgód, ani informacja o akceptacji).

**W przyszłości** do PDF mają trafić **zdjęcia z Wideodermatoskopu** (obrazy zmian skórnych powiązane z numerami Läsion). Z tego powodu wybrano technologię generowania PDF z natywną obsługą obrazów (WeasyPrint).

Język w PDF (Wymóg dwujęzyczności): Zgodnie z wymogami medyczno-prawnymi w Niemczech (tzw. Locale Trap), dokumentacja wydawana pacjentowi oraz przechowywana w aktach powinna być **dwujęzyczna** (język bazowy kliniki np. DE + język pacjenta). Gwarantuje to czytelność dla niemieckiego personelu i medyczno-prawną ważność dla pacjenta. Źródła języków: `medical_payload.authoring_locale` oraz docelowo język pacjenta (`form_locale`). Słowniki kodów Befund w db-plan 5.2.

---

## 3. Źródła danych w kodzie

Do budowy PDF wystarczą:

- **MedicalDocumentVersion** (już w evencie): `version.medical_payload`, `version.medical_document_id`, `version.medical_payload_schema_version`.
- **MedicalDocument:** `doc.queue_entry_id`.
- **QueueEntry:** `entry.patient_id`, `entry.daily_queue` (np. data wizyty, gabinet – opcjonalnie do nagłówka).
- **Patient:** `patient.first_name`, `last_name`, `date_of_birth`, `phone`, `email`.

**Nie są potrzebne do PDF:** PatientIntakeForm (body_map_data, signature_file_path, consents), definicje zgód i anamnezy – skoro do dokumentu nie trafiają schemat ciała, podpis ani zgody.

Serwis generowania PDF przyjmuje `MedicalDocumentVersion` i w jednym zapytaniu z `select_related("medical_document", "medical_document__queue_entry", "medical_document__queue_entry__patient")` pobiera wersję, dokument, wpis kolejki i pacjenta.

---

## 4. Technologia generowania PDF

**Wybór: WeasyPrint** (HTML/CSS → PDF). W **tym etapie** dokument to tekst + etykiety (Befund + dane pacjenta). W **przyszłości** do PDF trafią zdjęcia z Wideodermatoskopu – WeasyPrint ma natywną obsługę obrazów w szablonach HTML, co ułatwi dodanie zdjęć per grupa zmian bez zmiany stacku.


| Opcja            | Zalety                                                                                         | Wady                                                                 |
| ---------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **WeasyPrint** ✓ | HTML/CSS → PDF, łatwe szablony, **obsługa obrazów** (zdjęcia Wideodermatoskopu w przyszłości). | Zależności systemowe (Cairo, Pango) – uwzględnić w Dockerfile.       |
| ReportLab        | Czysty Python, brak zewn. bibliotek.                                                           | Obrazy możliwe, ale mniej wygodne; zmiana stacku przy dodaniu zdjęć. |
| xhtml2pdf (pisa) | Prosty pipeline HTML→PDF.                                                                      | Mniejsza zgodność CSS; słabsza obsługa obrazów.                      |


Kroki:

- Wydzielenie modułu `apps.medical.pdf`: funkcja `build_befund_pdf(version: MedicalDocumentVersion) -> bytes`.
- Szablon HTML (np. `templates/pdf/befund_document.html`) + kontekst: patient (name, DOB, contact), medical_payload (grupy zmian z tekstem końcowym, podsumowanie, rekomendacje, oceny) + dwujęzyczny słownik etykiet Befund (język bazowy + język pacjenta). W przyszłości: ścieżki do zdjęć Wideodermatoskopu per grupa/lesion.
- Konfiguracja: `PDF_BUILDER = "weasyprint"`; ścieżka do fontów jeśli potrzeba. W Dockerfile: zależności WeasyPrint (cairo, pango, gdk-pixbuf).

---

## 5. Ścieżki plików i checksum

- **Katalog:** Pliki PDF przechowywane lokalnie pod `MEDIA_ROOT`, w podkatalogu z datą (retencja, porządek), np. `pdfs/YYYY/MM/` – zgodnie z wzorcem `signatures/YYYY/MM/` z intake.
- **Nazwa pliku:** `{medical_document_version_id}.pdf` (unikalna per wersja).
- **Pole w DB:** `MedicalDocumentVersion.pdf_local_path` – ścieżka **względna do MEDIA_ROOT** (np. `pdfs/2026/02/<uuid>.pdf`), żeby przenośność i retencja działały z jednym `MEDIA_ROOT`. Retencja już wywołuje `_try_delete_file(version.pdf_local_path)` – trzeba w retencji (i przy odczycie do HiDrive) rozwiązywać pełną ścieżkę jako `Path(settings.MEDIA_ROOT) / version.pdf_local_path`.
- **Checksum:** Przy zapisie pliku obliczyć SHA-256 zawartości binarnej i zapisać w `pdf_checksum_sha256` (64 znaki hex). Wymagane przez db-plan i użyteczne przy weryfikacji po uploadzie.

---

## 6. Integracja z Outbox (GENERATE_PDF)

Obecny flow w `apps/outbox/services.py`:

1. `_execute_event(event, now)` dla `GENERATE_PDF`:
  - Pobiera `MedicalDocumentVersion` (już `select_for_update`).
  - **Obecnie:** od razu ustawia COMPLETED i dummy path/checksum, potem tworzy event `HIDRIVE_UPLOAD`.

Zmiany:

1. **Przed generowaniem:** ustawić `version.pdf_generation_status = PdfStatus.PROCESSING`, zapisać (żeby UI/API pokazywało „w trakcie”).
2. **Generowanie (poza transakcją blokującą wiersz?):**
  - Wariant A: generować PDF w tej samej transakcji – może być długo; blokuje wiersz.  
  - Wariant B: w transakcji tylko ustawić PROCESSING i zwolnić lock; wywołać builder; w nowej transakcji zapisać path/checksum/COMPLETED i utworzyć HIDRIVE_UPLOAD.  
   PRD: „Generowanie pliku PDF realizowane przez zadanie Django Tasks” – czyli w ramach jednego wywołania `_execute_event` możemy wykonać builder synchronicznie; transakcja może obejmować tylko „pobierz event + version”, potem builder (bez trzymania transakcji otwartej), potem osobna transakcja: zapis pliku na dysk, update version (COMPLETED, path, checksum), utworzenie HIDRIVE_UPLOAD. Zalecane: **generowanie (CPU) poza długą transakcją**, a w transakcji tylko odczyt i finalny zapis stanu.
3. **Zapis pliku:** wygenerowane `bytes` zapisać pod `MEDIA_ROOT/pdfs/YYYY/MM/<version_id>.pdf`, ustawić `pdf_local_path` na ścieżkę względną, obliczyć i ustawić `pdf_checksum_sha256`.
4. **Po sukcesie:** `pdf_generation_status = PdfStatus.COMPLETED`, zapis wersji, `OutboxEvent.objects.get_or_create(..., event_type=HIDRIVE_UPLOAD, ...)` – bez zmian w kontrakcie.
5. **Błąd:** przy wyjątku z buildera lub zapisu pliku: `pdf_generation_status = PdfStatus.FAILED`, nie tworzyć HIDRIVE_UPLOAD; outbox ustawi event na FAILED/DEAD_LETTER (obecna logika). Opcjonalnie zapisać `error_message` w wersji (jeśli dodamy pole) lub tylko w outbox event.

**Idempotentność:** Jedno zdarzenie GENERATE_PDF na wersję (UNIQUE per version + event_type). Ponowne przetworzenie po retry – builder powinien nadpisać plik tym samym ścieżką; bez duplikatów.

---

## 7. HIDRIVE_UPLOAD a plik lokalny

Obecnie `HIDRIVE_UPLOAD` tylko ustawia `hidrive_path` i `hidrive_sent=True` (mock). Docelowo w tym handlerze trzeba będzie:

- Odczytać plik z `MEDIA_ROOT / version.pdf_local_path`.
- Wysłać do HiDrive (lub mocka) pod ścieżką np. `/hidrive/medical/{document_id}/{version_id}.pdf`.
- Po sukcesie ustawić `hidrive_sent`, `hidrive_sent_at`.

W **planie PDF** wystarczy zagwarantować, że po GENERATE_PDF plik istnieje pod `pdf_local_path` i że retencja rozwiąże pełną ścieżkę przez `MEDIA_ROOT`. Szczegóły uploadu – osobny plan integracji HiDrive.

---

## 8. Retencja (30 dni)

W `run_retention_cleanup` już jest: usunięcie pliku tylko gdy `hidrive_sent` i `sms_sent`. Należy:

- Przy usuwaniu używać pełnej ścieżki: `full_path = Path(settings.MEDIA_ROOT) / version.pdf_local_path` (jeśli `pdf_local_path` jest względny).
- Obsłużyć przypadek `pdf_local_path` null (np. po wcześniejszym usunięciu lub błędzie) – nie wywoływać `unlink` na None.

---

## 9. Obsługa błędów i stany

- **PROCESSING:** Ustawiane na wejściu do generowania; po zakończeniu (sukces/porażka) nadpisane na COMPLETED lub FAILED.
- **FAILED:** Wyjątek w builderze lub zapisie pliku; outbox oznacza event jako FAILED, zwiększa retry_count, ustawia available_at (backoff). Wersja: `pdf_generation_status = FAILED`; brak HIDRIVE_UPLOAD do czasu retry.
- **DEAD_LETTER:** Po przekroczeniu max_retries; wymaga ręcznego retry lub korekty danych. Dashboard (PRD 3.5) powinien pokazywać DEAD_LETTER i FAILED.
- **Walidacja wejścia:** Przed generowaniem sprawdzić, czy `medical_payload` jest zgodny z schema_version (v1) i zawiera wymagane pola Befund. Nie jest wymagane sprawdzanie intake_form (podpis, zgody) – do PDF i tak nie trafiają.

---

## 10. Observability (PRD 3.5)

- **Metryki:**  
  - Czas generowania PDF per wersja (histogram lub timer): od rozpoczęcia GENERATE_PDF do ustawienia COMPLETED.  
  - Liczba sukcesów/porażek generowania (counter).  
  - Ekspozycja w `/observability/metrics` (Prometheus) – np. `cogitomedica_pdf_generation_duration_seconds`, `cogitomedica_pdf_generation_total` (success/failure).
- **Alerting:** Istniejące alerty outbox (oldest_pending, failed_count, dead_letter) obejmują także GENERATE_PDF.
- **Runbook:** Dodać sekcję „GENERATE_PDF failed / DEAD_LETTER”: (1) sprawdzić error_message w outbox_event i logi, (2) zweryfikować dane wersji (medical_payload, patient), (3) ewentualna korekta i ręczny retry eventu.

---

## 11. Fazy implementacji (propozycja)


| Faza                     | Zadania                                                                                                                                                                                                                                                                 | Efekt                                                                                                          |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **1. Przygotowanie**     | Ścieżka względna w `pdf_local_path`; w retencji i (na przyszłość) w HIDRIVE_UPLOAD rozwiązywanie pełnej ścieżki przez MEDIA_ROOT. Konfiguracja `PDF_ROOT`/`MEDIA_ROOT/pdfs/`.                                                                                           | Spójne zapisy i usuwanie plików.                                                                               |
| **2. Builder PDF**       | Moduł `apps.medical.pdf`: szablon HTML + kontekst (patient, medical_payload), słownik etykiet Befund (authoring_locale), render **WeasyPrint**. W tym etapie tylko tekst; struktura szablonu gotowa na przyszłe wstawienie zdjęć Wideodermatoskopu.                     | Funkcja `build_befund_pdf(version) -> bytes`.                                                                  |
| **3. Integracja outbox** | W `_execute_event(GENERATE_PDF)`: ustaw PROCESSING; wywołaj builder; zapisz plik pod `pdfs/YYYY/MM/<id>.pdf`; oblicz SHA-256; ustaw COMPLETED, pdf_local_path (względny), pdf_checksum_sha256; utwórz HIDRIVE_UPLOAD. Obsługa wyjątków → FAILED, bez tworzenia HIDRIVE. | End-to-end: publish → PDF na dysku → kolejkowanie uploadu.                                                     |
| **4. Testy i metryki**   | Testy jednostkowe buildera (mock version + patient); test integracyjny outbox: publish → process → weryfikacja pliku i checksum. Metryki czasu i success/failure.                                                                                                       | Stabilność i monitoring.                                                                                       |
| **5. (Przyszłość)**      | Zdjęcia z Wideodermatoskopu w PDF (obrazy zmian powiązane z numerami Läsion); pełna dwujęzyczność etykiet i tekstów (DE + język pacjenta); nagłówek kliniki, data wizyty.                                                                                               | Pełny dokument z obrazami i zabezpieczeniem prawnym (Locale Trap); WeasyPrint już wybrany pod obsługę obrazów. |


---

## 12. Zależności i ustawienia

- **Zależności:** **WeasyPrint** (`weasyprint`) + zależności systemowe: cairo, pango, gdk-pixbuf (do zainstalowania w Dockerfile / CI).
- **Ustawienia (settings):**  
  - `MEDIA_ROOT` – już jest.  
  - `PDF_RELATIVE_DIR = "pdfs"` – podkatalog w MEDIA_ROOT.  
  - `PDF_BUILDER = "weasyprint"`; opcjonalnie `PDF_TEMPLATE = "pdf/befund_document.html"`, ścieżka fontów.
- **Słowniki:** Dwujęzyczne etykiety Befund (np. DE + PL) – z wydzielonego modułu (np. `apps.medical.pdf_labels` lub mapowanie kodów z db-plan 5.2) z uwzględnieniem `medical_payload.authoring_locale` oraz języka pacjenta.

---

## 13. Podsumowanie

- **Wejście:** Zdarzenie outbox `GENERATE_PDF` z `medical_document_version_id`.
- **Dane:** Wersja (medical_payload), dokument → queue_entry (patient). **Bez** intake_form (zgody, podpis, schemat ciała nie wchodzą do PDF).
- **Wyjście:** Plik PDF w `MEDIA_ROOT/pdfs/YYYY/MM/<version_id>.pdf`, `pdf_local_path` (względny), `pdf_checksum_sha256`, `pdf_generation_status=COMPLETED`, utworzenie zdarzenia `HIDRIVE_UPLOAD`.
- **Błędy:** PROCESSING → FAILED przy wyjątku; outbox retry/DEAD_LETTER bez zmian.
- **Retencja:** Usuwanie pliku po 30 dniach tylko gdy hidrive_sent i sms_sent; ścieżka rozwiązywana przez MEDIA_ROOT.

Dokument można traktować jako specyfikację do implementacji; po realizacji faz 1–4 pipeline publish → PDF (tylko Befund + pacjent) → HiDrive → SMS będzie oparty o realnie wygenerowany plik.