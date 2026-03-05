# Stan wdrożenia i propozycja dalszych kroków

Data: 2026-02-22. Źródła: `.ai/plan-pdf-generation.md`, `.ai/proces-lekarza-code-review.md`, `.cursor/plans/plan-tablet-form-i-dalej.plan.md`, `.cursor/plans/plan_django_staff_frontend.plan.md`, `.ai/proces-lekarza-dalej.md`, stan kodu.

---

## 1. Co zostało zrealizowane

### 1.1 Code review procesu lekarza (proces-lekarza-code-review.md)

| Punkt | Status | Gdzie w kodzie |
|-------|--------|-----------------|
| 1.1 Walidacja lesions przy CONTROL_NEEDED (frontend) | ✅ | `static/doctor/js/befund-form.js` – przed wysłaniem sprawdzenie `lesions.length` |
| 1.2 Sprawdzenie intake SUBMITTED przy tworzeniu dokumentu | ✅ | `apps/medical/services.py` – `create_or_get_medical_document`: `if intake_form.form_status != IntakeStatus.SUBMITTED` |
| 1.3 Zachowanie filtrów przy zmianie języka (lista) | ✅ | `cogitomedica/doctor_views.py` – redirect z `request.GET.copy()` i `query.urlencode()` |
| 2.1 Ograniczenie lekarza do gabinetu (consulting_room) | ✅ | `StaffUser.consulting_room`, `_doctor_consulting_room_id`, `check_doctor_document_access`, `check_doctor_queue_entry_access`, filtry w `list_doctor_work_queue` / `list_medical_documents` |
| 2.2 Escape HTML w intake summary (XSS) | ✅ | `befund-form.js` – escapowanie przed `innerHTML` |
| 4.1 Refaktor JS do pliku statycznego | ✅ | `static/doctor/js/befund-form.js` |
| 4.2 Wspólne parsowanie parametrów listy | ✅ | `parse_medical_documents_list_params()` w `apps/medical/services.py`, używane w `doctor_views` i API |
| 4.3 + 5.1 Język (authoring_locale, komunikaty UI) | ✅ | `panel_data.context.authoring_locale`, `panel_data.ui` (msg_*, btn_*), `cogitomedica/doctor_i18n.py` |
| 5.2 Wyłączenie przycisku po publikacji | ✅ | `befund-form.js` – po publish disable + odświeżanie statusu |

### 1.2 Plan PDF (plan-pdf-generation.md)

| Faza / element | Status | Uwagi |
|----------------|--------|--------|
| Ścieżka względna `pdf_local_path`, MEDIA_ROOT w retencji | ✅ | `pdf_builder.generate_befund_pdf` zwraca ścieżkę względną; `_try_delete_file` łączy z `MEDIA_ROOT` |
| Builder PDF (WeasyPrint, szablon HTML) | ✅ | `apps/medical/pdf_builder.py`, `templates/pdf/befund_document.html` |
| Integracja outbox GENERATE_PDF | ✅ | `apps/outbox/services.py`: PROCESSING → builder → COMPLETED/FAILED, path, checksum SHA-256, HIDRIVE_UPLOAD |
| Retencja 30 dni | ✅ | `run_retention_cleanup`, tylko gdy `hidrive_sent` i `sms_sent` |
| Stany PROCESSING/FAILED/DEAD_LETTER | ✅ | Wersja + outbox; przy błędzie `pdf_generation_status=FAILED` |
| Metryki (success ratio 1h, P95 latency publish→pdf/hidrive/sms) | ✅ | `apps/operations/metrics.py` |
| Health + alerty (backlog >900s, failed, success ratio <98%) | ✅ | `apps/operations/api_views.py` – `observability_health_view` z tablicą `alerts` |
| HiDrive/SMS | Mock | Zgodnie z decyzją – mock; statusy w UI |

### 1.3 Proces lekarza – UI i operacje

| Element | Status |
|---------|--------|
| Lista: statusy PDF/HiDrive/SMS, wiersz z `processing_error_message` | ✅ `templates/doctor/list.html` |
| Detail: sekcja „Processing status”, Refresh, Ponów | ✅ `templates/doctor/detail.html`, `befund-form.js` |
| Retry processing (dokument) | ✅ `POST /api/v1/medical-documents/<id>/retry-processing` (ADMIN/RECEPTION), `medical_document_retry_processing_view` |
| Outbox: lista eventów, retry eventu | ✅ `apps/outbox/api_views.py` – dla ADMIN + RECEPTION (bez scope po jednostce) |
| Scheduler (cykliczne zadania co 5 min) | ✅ `run_periodic_tasks`, serwis `scheduler` w docker-compose |

### 1.4 Proces lekarza – backend (proces-lekarza-dalej.md)

| Element | Status |
|---------|--------|
| GET /medical-documents z filtrami, consulting_room | ✅ |
| GET/PUT/POST (draft, publish, versions) | ✅ |
| Kontekst dokumentu (intake_summary, current_version, statusy) | ✅ |
| Resend SMS przy publikacji | ✅ (payload `resend_sms` w outbox/SMS_SEND) |

---

## 2. Co pozostało z code review / ustaleń (do zrobienia)

- **Bezpieczeństwo outbox:** Lista i retry outbox-events dla RECEPTION bez filtrowania po jednostce (consulting_room / clinic_site) – ryzyko IDOR. Dodać scope: np. tylko eventy powiązane z dokumentami z gabinetów dostępnych dla użytkownika.
- **Alerty „failed >10 min”:** Obecna logika (`updated_at__lte=ten_minutes_ago`) daje trwały alert dla starych failed (np. wczorajszy DEAD_LETTER). Lepiej: okno czasowe (np. „istnieje failed z updated_at w ostatnich 10 min”) lub osobna metryka „failed_not_resolved_since”.
- **Ekspozycja błędów:** `error_message` z outbox może zawierać stack trace / wewnętrzne dane. W UI dla lekarza/recepcji pokazywać tylko bezpieczny komunikat (np. kod błędu + krótki tekst); surowe `error_message` tylko w logach / API dla ADMIN.
- **Wydajność list:** Listy prefetch’ują wszystkie wersje i outbox_events. Wystarczy „latest version” – ograniczyć prefetch (np. annotate `latest_version_id`, prefetch tylko tej wersji + jej outbox).

---

## 3. Plany w toku (nie zrealizowane)

### 3.1 Plan tablet-form-i-dalej

- **Krok 1 – Formularz pacjenta na tablecie:** Nie zrobiony. Brak widoku `/tablet/form/<intake_form_id>/` z sekcjami: weryfikacja danych, zgody, anamneza, podpis, submit.
- **Krok 2 – Kontrakt staff + GET medical-documents + RBAC ops:** GET medical-documents jest; RBAC ops (process/retention tylko ADMIN) – częściowo (process tylko ADMIN; outbox list/retry dla ADMIN + RECEPTION).
- **Krok 3 – Front staff (Unfold):** Plan w `.cursor/plans/plan_django_staff_frontend.plan.md` – wszystkie todos pending (contract freeze, Unfold setup, shell, reception/doctor/ops MVP, E2E).

### 3.2 Proces-lekarza-dalej – backend

- Pełna walidacja `medical_payload` v1 (Pydantic) przy PUT draft – do doprecyzowania/wdrożenia.
- Użycie szablonu przy zapisie (US-019) – opcjonalnie.

---

## 4. Propozycja: co dalej

### Priorytet 1 (bezpieczeństwo i jakość)

1. **Scope outbox dla RECEPTION** – Filtrowanie listy outbox-events i retry po consulting_room (dokument → queue_entry → daily_queue → consulting_room; użytkownik RECEPTION z consulting_room widzi tylko swoje; bez consulting_room – jak teraz lub tylko ADMIN).
2. **User-facing komunikaty błędów** – Warstwa mapowania: kod błędu + krótki tekst w UI; `error_message` tylko w API dla ADMIN / w logach.

### Priorytet 2 (observability i utrzymanie)

3. **Alerty „failed” i metryki operacyjne** – Usunięcie logiki okien czasowych z endpointu `/health` i przeniesienie wyliczania alertów do zewnętrznego Prometheus Alertmanager. Wdrożenie darmowego stacku Prometheus OSS + Grafana OSS zgodnie z `.cursor/plans/observability_wdrożenie.plan.md`.
4. **Optymalizacja list** – Dla listy lekarza i GET /medical-documents: nie ładować pełnej historii wersji/outbox; np. tylko latest version + jej outbox (annotate + prefetch).

### Priorytet 3 (funkcjonalność)

5. **Formularz pacjenta na tablecie** – Zgodnie z plan-tablet-form-i-dalej: widok formularza (zgody, anamneza, podpis, submit), żeby zamknąć flow pacjenta bez Swaggera.
6. **Front staff (Unfold)** – Po ustaleniu kontraktu: integracja Unfold, shell, recepcja/lekarz/ops MVP.

### Opcjonalnie

- **Runbook** – Sekcja „GENERATE_PDF / HIDRIVE / SMS failed i DEAD_LETTER”: kroki dla recepcji/admin (logi, error_message, retry, ewentualna korekta danych).
- **Dokumentacja** – Zaktualizować `.ai/plan-pdf-generation.md` (zaznaczyć fazy 1–4 jako zrealizowane) lub trzymać ten plik jako „stan wdrożenia”.

---

## 5. Szybki odniesienie do plików

| Obszar | Pliki |
|--------|--------|
| PDF | `apps/medical/pdf_builder.py`, `apps/outbox/services.py` (GENERATE_PDF), `templates/pdf/befund_document.html` |
| Lekarz – backend | `apps/medical/services.py`, `apps/medical/api_views.py` |
| Lekarz – UI | `templates/doctor/list.html`, `templates/doctor/detail.html`, `static/doctor/js/befund-form.js`, `cogitomedica/doctor_views.py`, `cogitomedica/doctor_i18n.py` |
| Outbox API | `apps/outbox/api_views.py`, `apps/outbox/services.py` |
| Metryki / health | `apps/operations/metrics.py`, `apps/operations/api_views.py` |
| Scheduler | `apps/operations/management/commands/run_periodic_tasks.py`, `docker-compose.yml` (scheduler) |
