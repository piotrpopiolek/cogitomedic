# Proces lekarza – co wykonać dalej

Stan po wdrożeniu: lista dokumentów, kontekst dokumentu, versions, GET szablonu po id.

---

## 1. Już zrobione (backend)

| Element | Status |
|--------|--------|
| GET /medical-documents | Lista z filtrami (status, queue_date, patient_search), paginacja, pdf_generation_status, hidrive_sent, sms_sent |
| GET /medical-documents/{id} | Pełny kontekst: dokument + intake_summary (consents, body_map, anamnesis) + current_version |
| POST /medical-documents | Create (create_or_get) |
| PUT /medical-documents/{id}/draft | Zapis szkicu (medical_payload, diagnosis_code, procedure_code) |
| POST /medical-documents/{id}/publish | Publish z idempotencją (publish_request_id) |
| GET /medical-documents/{id}/versions | Lista wersji dokumentu |
| GET /medical-document-versions/{id} | Szczegóły wersji (payload, statusy PDF/HiDrive/SMS) |
| GET/POST /doctor-text-templates | Lista i tworzenie szablonów |
| GET/PATCH /doctor-text-templates/{id} | Odczyt i edycja szablonu |
| Outbox (GENERATE_PDF → HiDrive → SMS) | Działa po publish |

---

## 2. Do zrobienia (żeby „przejść” proces lekarza)

### 2.1. Backend (dopracowanie)

1. **`resend_sms` przy publikacji (US-010)**  
   W body `POST .../publish` dodać opcjonalne pole `resend_sms: bool`.  
   Przy republikacji (edycja już opublikowanego dokumentu) front może ustawić `resend_sms: true`, żeby ponownie wysłać SMS.  
   W outboxie / payloadzie zadania SMS_SEND trzeba przekazać tę flagę (wysłać SMS nawet jeśli dla poprzedniej wersji już wysłano).

2. **Walidacja `medical_payload` v1 (Pydantic)**  
   Obecnie API przyjmuje `MedicalPayloadMinimal` (tylko `schema_version` + extra).  
   Dodać pełny schemat v1: enumy (fitzpatrick_type, overall_image_assessment, clinical_assessment, malignancy_risk, final_assessment, examination_scope[], recommendations[]), struktura `lesions[]` (lesion_numbers[], dermatoscopic_features[], clinical_assessment, malignancy_risk), reguła: `lesions` puste tylko gdy `overall_image_assessment=NO_CONTROL_NEEDED`; walidacja: lesion_numbers niepuste i bez duplikatów.  
   Użyć tego schematu przy PUT draft (wtedy 400 przy błędnej strukturze).

3. **Opcjonalnie: użycie szablonu przy zapisie (US-019)**  
   Szablony lekarza można wykorzystać przy zapisie draft (np. jako szkielet podsumowania). Semantyka „szablonu” (cały tekst vs. fragmenty) do ustalenia.

### 2.2. Frontend (panel lekarza)

Żeby proces lekarza był **używalny end-to-end**, potrzebny jest frontend:

4. **Widok listy (work queue)**  
   Wywołanie GET /medical-documents z filtrami (data, status, wyszukiwanie pacjenta).  
   Tabela/karty: pacjent, data kolejki, status dokumentu, pdf_generation_status, hidrive_sent, sms_sent.  
   Klik → przejście do szczegółów dokumentu.

5. **Widok szczegółów dokumentu**  
   GET /medical-documents/{id} → wyświetlenie intake_summary (zgody, body map, anamneza) + current_version (medical_payload, diagnosis_code, procedure_code).  
   Formularz Befund (zgodnie z tworzenie_befund.txt / befund-formularz-spec-v1-prd.md):  
   - sekcje 1–11 (zakres badania, Fitzpatrick, ocena globalna, wybór zmian, cechy per zmiana, ocena kliniczna i ryzyko per zmiana, rekomendacje, ocena końcowa),  
   - edytowalne pola tekstowe (edited_text / summary_edited_text),  
   - zapis szkicu (PUT draft) i publikacja (POST publish).

6. **Komunikacja z API**  
   Spójne wywołania: create (jeśli wejście od „nowego dokumentu”), draft, publish.  
   Obsługa błędów (404, 400, 409) i ewentualnie statusu „publikacja w toku” (idempotentny publish).

7. **Opcjonalnie**  
   - Historia wersji: GET .../versions i GET /medical-document-versions/{id} (np. w drawerze / modalu).  
   - Wybór szablonu (GET doctor-text-templates, GET …/id) przy generowaniu tekstu.  
   - Dashboard: zaległe dokumenty, błędy PDF/SMS (wymaga endpointów observability lub istniejących metryk).

### 2.3. Inne (opcjonalne)

8. **DELETE / doctor-text-templates/{id}**  
   Dezaktywacja lub usunięcie szablonu (CRUD). Obecnie jest tylko PATCH (is_active).

9. **Aktualizacja analizy**  
   Plik `.ai/analiza-proces-lekarza-etap.md` można zaktualizować: zaznaczyć w tabelach API/Logika, że GET list, GET detail, versions, GET template są zaimplementowane.

---

## 3. Kolejność rekomendowana

1. **Minimum do „przejścia” procesu (scenariusz lekarza):**  
   **Frontend** (pkt 4–6) – bez niego lekarz i tak nie korzysta z API.  
   Opcjonalnie równolegle: **resend_sms** (2.1.1) i **walidacja medical_payload** (2.1.2).

2. **Potem:**  
   Użycie szablonu przy zapisie (2.1.3), historia wersji w UI (2.2.7), DELETE szablonu (2.3.8).

3. **Dokumentacja:**  
   Aktualizacja analizy (2.3.9) po zakończeniu backendu.

---

## 4. Podsumowanie jednym zdaniem

**Backend procesu lekarza jest w ~90% gotowy.** Aby faktycznie „przejść” proces lekarza, kluczowe jest zbudowanie **frontendu panelu lekarza** (lista → szczegóły → formularz Befund → zapis szkicu → publikacja). Na backendzie warto jeszcze dodać **resend_sms** przy publish i **pełną walidację medical_payload v1**.
