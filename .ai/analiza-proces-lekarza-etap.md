# Analiza procesu lekarza – na jakim etapie jesteśmy

Porównanie wymagań z PRD, db-plan i api-plan z aktualną implementacją w kodzie.

---

## 1. Zakres procesu lekarza (z PRD / api-plan)

| ID | Wymaganie | Źródło |
|----|-----------|--------|
| US-008 | Wypełnianie części medycznej (Befund): dostęp do formularza pacjenta, sekcja medyczna z polami i listą zmian 1..N, **generowanie tekstu z checkboxów** (edytowalne), **generowanie podsumowania zbiorczego** (edytowalne), swoboda dopisywania | PRD §3.3, §5 |
| US-009 | Zapis szkicu; publikacja (Zatwierdź i wyślij) – idempotentna, kolejkuje PDF/outbox | PRD §3.3, §3.4 |
| US-010 | Edycja opublikowanego dokumentu, ponowna wysyłka (nadpisanie HiDrive, opcja resend_sms) | PRD §3.3 |
| US-019 | Własne szablony tekstu lekarza (DE/EN), globalne vs prywatne, użycie przy generowaniu tekstu | PRD §5 |

Z api-plan: lista dokumentów (work queue), pełny kontekst dokumentu (intake + wersja), create, save draft, publish, doctor-text-templates CRUD, wersje dokumentu.

---

## 2. Baza danych (db-plan vs implementacja)

| Element | Plan (db-plan) | Stan w kodzie |
|---------|----------------|----------------|
| `medical_document` | queue_entry, intake_form, status, current_version_no, last_published_at, created_by, updated_by | **Zgodne** – model `MedicalDocument` |
| `medical_document_version` | version_no, version_status, publish_request_id, pdf_*, medical_payload (JSONB), diagnosis_code, procedure_code, hidrive_*, sms_*, local_pdf_deleted_at | **Zgodne** – model `MedicalDocumentVersion` |
| Kontrakt `medical_payload` v1 | schema_version, authoring_locale, examination_scope, fitzpatrick_type, overall_image_assessment, lesions[], recommendations, final_assessment, summary_generated_text, summary_edited_text, template_context; per lesion: generated_text, edited_text | **Częściowo** – w API przyjmowany jest `MedicalPayloadMinimal` (tylko `schema_version` + extra). Pełna walidacja pól Befund (lesions, enumy) **nie jest** wymuszana w Pydantic |
| `doctor_text_template` | owner_user_id, name, template_locale, template_body, is_global, is_active | **Zgodne** – model `DoctorTextTemplate` |
| Outbox (GENERATE_PDF, HIDRIVE_UPLOAD, SMS_SEND) | Tak | Zaimplementowane w `publish_document_version` + zadania (outbox) |

**Wniosek DB:** Modele i kolumny są na miejscu. Brakuje **walidacji pełnego kontraktu** `medical_payload` v1 (enumy, struktura lesions) w warstwie API/serwisów.

---

## 3. API (api-plan vs implementacja)

| Endpoint | Plan | Stan |
|----------|------|------|
| **GET** `/medical-documents` | Lista work queue (status, queue_date, doctor_view, patient_search, paginacja), flagi pdf_generation_status, hidrive_sent, sms_sent | **Brak** – `medical_documents_view` obsługuje tylko **POST** (create). Nie ma GET listy. |
| **GET** `/medical-documents/{id}` | Pełny kontekst: dokument + intake_summary (consents, body_map, anamnesis_answers) + current_version (medical_payload, diagnosis_code, procedure_code) | **Brak** – brak widoku detail dla dokumentu medycznego. |
| **POST** `/medical-documents` | Create (queue_entry_id; intake_form_id z sesji/kontekstu). Idempotent create-or-get. | **Jest** – `create_or_get_medical_document`, zwraca 201 z medical_document_id. |
| **PUT** `/medical-documents/{id}/draft` | Zapis szkicu (medical_payload, diagnosis_code, procedure_code). Plan mówi PATCH, w kodzie PUT. | **Jest** – `medical_document_draft_view` (PUT), `save_draft_document_version`. |
| **POST** `/medical-documents/{id}/publish` | Publish z publish_request_id (idempotencja), opcjonalnie resend_sms. | **Częściowo** – publish jest, idempotencja (publish_request_id + „in progress”) jest. **Brak** parametru `resend_sms` w body. |
| **GET** `/medical-documents/{id}/versions` | Historia wersji | **Brak** |
| **GET** `/medical-document-versions/{id}` | Szczegóły wersji + status PDF/HiDrive/SMS | **Brak** |
| **GET** `/doctor-text-templates` | Lista (template_locale, scope, is_active) | **Jest** |
| **POST** `/doctor-text-templates` | Tworzenie szablonu | **Jest** |
| **GET** `/doctor-text-templates/{id}` | Odczyt pojedynczego szablonu | **Brak** – jest tylko PATCH (update), brak GET po id. |
| **PATCH** `/doctor-text-templates/{id}` | Aktualizacja szablonu | **Jest** |
| **DELETE** `/doctor-text-templates/{id}` | Usuwanie/dezaktywacja | **Brak** (plan nie wymienia explicite, ale CRUD zwykle obejmuje delete). |

---

## 4. Logika domenowa / serwisy

| Funkcjonalność | Plan | Stan |
|----------------|------|------|
| Tworzenie dokumentu (create_or_get) | Dla queue_entry + intake_form, idempotent | **Jest** – `create_or_get_medical_document` |
| Zapis szkicu | Update ostatniego DRAFT lub nowa wersja DRAFT | **Jest** – `save_draft_document_version` |
| Publikacja | Blokada wiersza, idempotencja (publish_request_id, „in progress”), ustawienie PUBLISHED, utworzenie wpisu GENERATE_PDF w outbox | **Jest** – `publish_document_version` |
| Republikacja (US-010) | Edycja opublikowanego → nowa wersja, publish → nadpisanie HiDrive, opcja resend_sms | Publikacja kolejnej wersji jest możliwa przez obecny flow (nowy draft → publish). **resend_sms** nie jest obsługiwane w request/outbox. |

---

## 5. Podsumowanie etapu

### Zaimplementowane (etap obecny)

- **Baza:** `medical_document`, `medical_document_version`, `doctor_text_template`, outbox (GENERATE_PDF itd.).
- **API:** tworzenie dokumentu (POST medical-documents), zapis szkicu (PUT …/draft), publikacja (POST …/publish) z idempotencją po `publish_request_id` i „publication in progress”.
- **Szablony:** listowanie i tworzenie/edycja szablonów tekstu (GET/POST doctor-text-templates, PATCH …/id).
- **Outbox:** łańcuch PDF → HiDrive → SMS (zgodnie z przyjętą architekturą).

### Brakuje (proces lekarza niekompletny)

1. **GET /medical-documents** – lista dokumentów (kolejka pracy lekarza) z filtrami i statusami.
2. **GET /medical-documents/{id}** – pełny kontekst dokumentu (intake + aktualna wersja) do widoku lekarza.
3. **Resend SMS** przy republikacji – parametr w publish (lub osobny flow) i obsługa w payloadzie/outbox.
4. **GET /medical-documents/{id}/versions** oraz **GET /medical-document-versions/{id}** – historia wersji i szczegóły wersji (status PDF/HiDrive/SMS).
5. **GET /doctor-text-templates/{id}** – odczyt pojedynczego szablonu (np. do formularza edycji).
6. **Walidacja medical_payload v1** – pełny kontrakt (enumy, lesions[], wymagane pola) w schemacie Pydantic przy zapisie draft.

---

## 6. Ocena etapu

**Obecny etap:** **wczesna Faza 2 – szkielet procesu lekarza**.

- Działają: **tworzenie dokumentu**, **zapis szkicu** (payload dowolny przez `extra="allow"`), **publikacja z idempotencją** i **outbox**. Lekarz **nie ma** w API: listy dokumentów do obrobienia, widoku szczegółów dokumentu z danymi intake, ani pełnej walidacji struktury Befund.

Aby uznać proces lekarza za „na etapie zgodnym z PRD” (US-008, US-009, US-010, US-019), konieczne jest uzupełnienie powyższych brakujących elementów, w pierwszej kolejności: **lista + kontekst dokumentu**.
