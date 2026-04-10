# Kontrakt API dla panelu staff (recepcja, lekarz, admin)

Dokument opisuje endpointy używane przez personel oraz **RBAC** (kto ma dostęp). Pełna specyfikacja payloadów i kodów błędów: [api-plan.md](api-plan.md).

---

## 1. Role i zakres dostępu

| Rola       | Zakres API |
|-----------|------------|
| **RECEPTION** | Kolejki dzienne, wpisy kolejki, pacjenci (CRUD), urządzenia tabletu, sesje formularza (POST sessions → intake_form_id); dokumenty intake (PDF): lista, szczegóły, podgląd PDF – scope po placówce. |
| **TABLET**    | Lista kolejek, lista wpisów kolejki, kontekst formularza (GET intake-forms), zgody/anamneza/body map/podpis/submit (PUT/PATCH/POST na intake-forms). **Zakres kolejek:** gdy w sesji jest `tablet_device_id` i urządzenie ma przypisaną placówkę (`TabletDevice.clinic_site_id`), API i widok HTML zwracają tylko kolejki tej placówki; bez przypisania – pusta lista. |
| **DOCTOR**    | Medical documents: lista (GET), tworzenie (POST), szczegóły (GET), draft (PUT), unlock (POST), publish (POST), wersje (GET). Blokada edycji szkicu (max 24h): inny lekarz dostaje `423` na PUT draft; GET kontekstu zawiera `locked_by_*`. |
| **ADMIN**     | Wszystko powyżej + użytkownicy staff, operacje outbox (lista, retry, process), retention, metryki (observability/metrics). |

---

## 2. Endpointy operacyjne (tylko ADMIN)

Dostęp: **wyłącznie rola ADMIN**. Dla RECEPTION/DOCTOR zwracane jest **403 Forbidden**.

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| **GET**  | `/api/v1/outbox-events` | Lista zdarzeń outbox (parametry: `status`, `event_type`, `retry_count_gte`, `limit` — jak inne listy: domyślnie **20**, maks. **100**, `parse_list_limit`). |
| **POST** | `/api/v1/outbox-events/{id}/retry` | Wymuszenie ponowienia zdarzenia (body: `reason`). |
| **POST** | `/api/v1/operations/outbox/process` | Ręczne uruchomienie cyklu przetwarzania outbox (body: `limit`). |
| **POST** | `/api/v1/operations/retention/run` | Ręczny przebieg retencji (usuwanie lokalnych PDF; body: `older_than_days`, `dry_run`). |
| **GET**  | `/api/v1/observability/metrics` | Metryki Prometheus (m.in. outbox, integracje). |

**Health** (`GET /api/v1/observability/health`) – bez autentykacji (liveness/readiness).

**Paginacja list staff:** Parametry `page` (domyślnie `1`) i `page_size` (domyślnie **20**, maks. **100**) — stałe `DEFAULT_LIST_LIMIT` / `MAX_LIST_LIMIT` w `apps.core.api_utils`. Wszystkie listy z parametrem `limit` (placówki, kolejki, batche importów, **GET outbox-events**, **GET intake-outbox-events**) używają `parse_list_limit` — te same domyślne i maksymalne wartości.

---

## 3. Pozostałe grupy endpointów (skrót)

- **Auth:** POST login, POST logout, GET me – sesja + CSRF.
- **Recepcja:** daily-queues, queue-entries, patients, clinic-sites, consulting-rooms, tablet-devices (CRUD; pole `clinic_site_id` – przypisanie tabletu do placówki), POST queue-entries/…/sessions; GET intake-documents (lista), GET intake-documents/{id} (szczegóły), GET intake-documents/{id}/preview-pdf (RECEPTION/ADMIN, scope po clinic_site). Dla TABLET: GET daily-queues i GET daily-queues/{id}/entries używają scope z urządzenia w sesji (`tablet_device_id` + `TabletDevice.clinic_site_id`), gdy dostępne.
- **Intake:** GET/PATCH intake-forms/{id}, PUT consents, PUT anamnesis, POST signature, POST submit.
- **Medical:** GET/POST medical-documents, GET medical-documents/{id}, PUT draft, POST unlock, POST publish, GET versions.

Szczegóły request/response i kody błędów: [api-plan.md](api-plan.md) §2.

---

## 4. Wejścia do UI (bez Unfold)

- **Tablet (poczekalnia):** `/tablet/` → logowanie (TABLET) → wybór kolejki → lista pacjentów → „Otwórz formularz” → ekran „Formularz przygotowany” → **„Przekaż tablet pacjentowi – wypełnij formularz”** → `/tablet/form/<intake_form_id>/` (zgody, anamneza, body map, podpis, submit).
- **Lekarz:** `/doctor/` → logowanie (DOCTOR/ADMIN) → lista dokumentów (work queue) z filtrami → „Öffnen” → `/doctor/<medical_document_id>/` (formularz Befund, zapis szkicu, publikacja).
- **Recepcja/Admin – dokumenty intake (PDF):** w menu panelu Unfold: Rejestracja (Admin) → **Dokumenty intake (PDF)** lub bezpośrednio `/admin/intake-documents/` – lista dokumentów z filtrami (data kolejki, status PDF, placówka, pacjent), paginacja, link do szczegółów i przycisk „Podgląd PDF” (inline).

---

## 5. Portal wyniki (US-018) – poza kontraktem staff

Portal wyniki dla pacjenta (wyniki.cogitomedica.pl) korzysta z **osobnych endpointów**, bez sesji staff:
- Logowanie: phone + date_of_birth (dane zweryfikowane w recepcji).
- OTP 6-cyfrowy, ważność 15 min.
- Po poprawnej OTP: serwowanie PDF przez HTTPS; zdarzenia audytowe w `audit_event` (typy `PATIENT_RESULTS_*`: OTP, lista dokumentów, pobranie PDF / odmowa).
- Szczegóły: PRD 3.4a, api-plan §4.2 (Patient results portal).

## 6. Historia zmian

- **Tablet przypisany do placówki:** TabletDevice ma pole `clinic_site_id`. Tablet zalogowany z `android_id` ma w sesji `tablet_device_id`; GET daily-queues / daily-queues/{id}/entries i widok HTML poczekalni filtrują kolejki po `device.clinic_site_id`. Bez przypisania tablet widzi pustą listę (komunikat w UI). Przypisanie w adminie lub przez API (POST/PATCH tablet-devices).
- **Dokumenty intake (PDF):** Dodane endpointy GET intake-documents (lista), GET intake-documents/{id}, GET intake-documents/{id}/preview-pdf dla RECEPTION/ADMIN (scope po clinic_site). W panelu Unfold: strona „Dokumenty intake (PDF)” pod `/admin/intake-documents/` (lista, szczegóły, podgląd PDF).
- **Opcja B (dopełnienie procesu):** GET outbox-events i POST outbox-events/{id}/retry ograniczone do roli ADMIN (wcześniej: dowolny zalogowany użytkownik). Process i retention były już ADMIN-only.
- **Proces udostępniania (PRD 3.4a):** SMS wyłącznie logistyczny; pacjent pobiera PDF przez portal wyniki (phone+DOB, OTP, HTTPS).
