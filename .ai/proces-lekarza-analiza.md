# Analiza procesu lekarza – stan bieżący

Krótki przegląd ścieżki lekarza w aplikacji: co jest zaimplementowane i jak to działa.

---

## 1. Przepływ (user flow)

1. **Logowanie** (`/doctor/login/`) – użytkownik z rolą DOCTOR lub ADMIN loguje się; sesja współdzielona z API.
2. **Lista (work queue)** (`/doctor/`) – tabela wpisów z **zakończoną ankietą pacjenta** (intake SUBMITTED). Filtry: status (DRAFT/PUBLISHED), data kolejki, wyszukiwanie po nazwisku. Kolumny: pacjent, data, status dokumentu, PDF, HiDrive, SMS. Przycisk **Öffnen**:
   - jeśli jest już dokument medyczny → przejście do szczegółów dokumentu,
   - jeśli nie ma → wywołanie `doctor_open_by_queue` (create-or-get dokumentu) i przekierowanie do szczegółów.
3. **Szczegóły dokumentu** (`/doctor/<medical_document_id>/`) – widok Befund:
   - **Intake (read-only)** – dane pacjenta i odpowiedzi z ankiety (wywiad).
   - **Formularz Befund** – sekcje 1–11 (zakres badania, Fitzpatrick, ocena globalna, grupy zmian z numerami/cechami/oceną/tekstem, podsumowanie, rekomendacje, ocena końcowa).
   - **Akcje:** Zapisz szkic → Zatwierdź i wyślij (z opcją „SMS erneut senden”).

---

## 2. Backend (API i serwisy)

| Element | Plik / endpoint | Opis |
|--------|-----------------|------|
| Lista dokumentów | `GET /api/v1/medical-documents` | Filtry: status, queue_date, patient_search; paginacja; zwraca items + pagination. |
| Kontekst dokumentu | `GET /api/v1/medical-documents/{id}` | Pełny kontekst: dokument + intake_summary (patient, consents, body_map, anamnesis_questions) + current_version (medical_payload, diagnosis_code, procedure_code). |
| Utworzenie dokumentu | `POST /api/v1/medical-documents` | create_or_get po queue_entry_id + intake_form_id. |
| Zapis szkicu | `PUT /api/v1/medical-documents/{id}/draft` | Walidacja medical_payload v1; update ostatniego DRAFT lub nowa wersja DRAFT. |
| Publikacja | `POST /api/v1/medical-documents/{id}/publish` | Body: publish_request_id (idempotencja), resend_sms. Ustawia PUBLISHED, outbox (GENERATE_PDF → HiDrive → SMS). |
| Wersje | `GET /api/v1/medical-documents/{id}/versions` | Lista wersji (id, version_no, status, pdf_generation_status, published_at, hidrive_sent, sms_sent). |
| Szablony | GET/POST `/doctor-text-templates`, GET/PATCH `.../{id}` | Lista/tworzenie/edycja szablonów tekstu (ulubione per zmiana i podsumowanie). |

Serwisy: `create_or_get_medical_document`, `get_medical_document_context`, `list_medical_documents`, `list_doctor_work_queue`, `save_draft_document_version`, `publish_document_version`, walidacja `validate_medical_payload_v1`.

---

## 3. Frontend (panel lekarza)

| Widok | Szablon | Opis |
|-------|---------|------|
| Logowanie | `doctor/login.html` | Formularz username/password, wybór języka (DE/EN/PL), next. |
| Lista | `doctor/list.html` | Formularz filtrów (status, data, patient_search), tabela z linkami Öffnen (document-detail lub open-by-queue). |
| Szczegóły | `doctor/detail.html` | JSON `doctor-panel-data`: documentId, apiBase, context (intake + current_version). Inline JS: renderowanie intake-summary, grupy zmian (szablon + dodawanie/usuwanie), buildPayload(), przyciski Zapisz szkic / Zatwierdź i wyślij. Przy publikacji: najpierw PUT draft, potem POST publish z publish_request_id i resend_sms. |

i18n: `cogitomedica/doctor_i18n.py` – etykiety sekcji, przycisków, filtrów (DE/EN/PL).

---

## 4. Dane i walidacja

- **medical_payload v1** – walidowany przy PUT draft (enumy, lesions[], reguły np. lesions puste tylko przy NO_CONTROL_NEEDED). Schemat w `apps/medical/medical_payload_schemas.py`.

---

## 5. Outbox (po publikacji)

- **GENERATE_PDF** – generacja PDF z wersji.
- **HIDRIVE_UPLOAD** – wysłanie do HiDrive.
- **SMS_SEND** – wysłanie SMS (z obsługą resend_sms przy republikacji).

---

## 6. Podsumowanie

**Proces lekarza jest zaimplementowany end-to-end:** lista → wejście w dokument (create-or-get) → szczegóły z intake + formularz Befund → zapis szkicu → publikacja z idempotencją i opcją ponownego SMS. Backend obsługuje listę, kontekst, draft, publish, wersje i szablony. Frontend to HTML + inline JS w `detail.html` (bez osobnego bundle’a); ewentualne rozszerzenia to m.in. historia wersji w UI, wybór szablonu w formularzu, lepsze komunikaty błędów i dostępność.
