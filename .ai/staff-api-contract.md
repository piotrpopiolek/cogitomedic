# Kontrakt API dla panelu staff (recepcja, lekarz, admin)

Dokument opisuje endpointy używane przez personel oraz **RBAC** (kto ma dostęp). Pełna specyfikacja payloadów i kodów błędów: [api-plan.md](api-plan.md).

---

## 1. Role i zakres dostępu

| Rola       | Zakres API |
|-----------|------------|
| **RECEPTION** | Kolejki dzienne, wpisy kolejki, pacjenci (CRUD), urządzenia tabletu, sesje formularza (POST sessions → intake_form_id); dokumenty intake (PDF): lista, szczegóły, podgląd PDF – scope po placówce. |
| **TABLET**    | Lista kolejek, lista wpisów kolejki, kontekst formularza (GET intake-forms), zgody/anamneza/body map/podpis/submit (PUT/PATCH/POST na intake-forms). |
| **DOCTOR**    | Medical documents: lista (GET), tworzenie (POST), szczegóły (GET), draft (PUT), publish (POST), wersje (GET). |
| **ADMIN**     | Wszystko powyżej + użytkownicy staff, operacje outbox (lista, retry, process), retention, metryki (observability/metrics). |

---

## 2. Endpointy operacyjne (tylko ADMIN)

Dostęp: **wyłącznie rola ADMIN**. Dla RECEPTION/DOCTOR zwracane jest **403 Forbidden**.

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| **GET**  | `/api/v1/outbox-events` | Lista zdarzeń outbox (parametry: `status`, `event_type`, `retry_count_gte`, `limit`). |
| **POST** | `/api/v1/outbox-events/{id}/retry` | Wymuszenie ponowienia zdarzenia (body: `reason`). |
| **POST** | `/api/v1/operations/outbox/process` | Ręczne uruchomienie cyklu przetwarzania outbox (body: `limit`). |
| **POST** | `/api/v1/operations/retention/run` | Ręczny przebieg retencji (usuwanie lokalnych PDF; body: `older_than_days`, `dry_run`). |
| **GET**  | `/api/v1/observability/metrics` | Metryki Prometheus (m.in. outbox, integracje). |

**Health** (`GET /api/v1/observability/health`) – bez autentykacji (liveness/readiness).

---

## 3. Pozostałe grupy endpointów (skrót)

- **Auth:** POST login, POST logout, GET me – sesja + CSRF.
- **Recepcja:** daily-queues, queue-entries, patients, clinic-sites, consulting-rooms, tablet-devices, POST queue-entries/…/sessions; GET intake-documents (lista), GET intake-documents/{id} (szczegóły), GET intake-documents/{id}/preview-pdf (RECEPTION/ADMIN, scope po clinic_site).
- **Intake:** GET/PATCH intake-forms/{id}, PUT consents, PUT anamnesis, POST signature, POST submit.
- **Medical:** GET/POST medical-documents, GET medical-documents/{id}, PUT draft, POST publish, GET versions.

Szczegóły request/response i kody błędów: [api-plan.md](api-plan.md) §2.

---

## 4. Wejścia do UI (bez Unfold)

- **Tablet (poczekalnia):** `/tablet/` → logowanie (TABLET) → wybór kolejki → lista pacjentów → „Otwórz formularz” → ekran „Formularz przygotowany” → **„Przekaż tablet pacjentowi – wypełnij formularz”** → `/tablet/form/<intake_form_id>/` (zgody, anamneza, body map, podpis, submit).
- **Lekarz:** `/doctor/` → logowanie (DOCTOR/ADMIN) → lista dokumentów (work queue) z filtrami → „Öffnen” → `/doctor/<medical_document_id>/` (formularz Befund, zapis szkicu, publikacja).
- **Recepcja/Admin – dokumenty intake (PDF):** w menu panelu Unfold: Rejestracja (Admin) → **Dokumenty intake (PDF)** lub bezpośrednio `/admin/intake-documents/` – lista dokumentów z filtrami (data kolejki, status PDF, placówka, pacjent), paginacja, link do szczegółów i przycisk „Podgląd PDF” (inline).

---

## 5. Historia zmian

- **Dokumenty intake (PDF):** Dodane endpointy GET intake-documents (lista), GET intake-documents/{id}, GET intake-documents/{id}/preview-pdf dla RECEPTION/ADMIN (scope po clinic_site). W panelu Unfold: strona „Dokumenty intake (PDF)” pod `/admin/intake-documents/` (lista, szczegóły, podgląd PDF).
- **Opcja B (dopełnienie procesu):** GET outbox-events i POST outbox-events/{id}/retry ograniczone do roli ADMIN (wcześniej: dowolny zalogowany użytkownik). Process i retention były już ADMIN-only.
