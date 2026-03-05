# Code review: Proces lekarza (panel lekarza end-to-end)

Przegląd pod kątem: błędy logiczne i bugi, bezpieczeństwo, wydajność, utrzymanie, styl.

**Stan wdrożenia (2026-02-22):** Wszystkie punkty 1.x, 2.x, 4.x, 5.x z sekcji poniżej zostały zrealizowane (intake SUBMITTED, consulting_room, filtry przy lang, XSS, befund-form.js, parse params, locale/UI, disable publish). Do zrobienia: scope outbox dla RECEPTION (IDOR), user-facing komunikaty błędów, optymalizacja prefetch list. Zob. `.ai/stan-wdrozenia-i-dalej.md`.

---

## 1. Błędy logiczne i bugi

### 1.1 [Średni] Walidacja `overall_image_assessment` vs puste grupy zmian (frontend)

**Gdzie:** `templates/doctor/detail.html` – `buildPayload()`, sekcja 4 (lesion groups).

**Problem:** Backend (medical_payload_schemas.MedicalPayloadV1) wymaga: gdy `overall_image_assessment === "CONTROL_NEEDED"`, lista `lesions` nie może być pusta. W `buildPayload()` grupy bez wpisanych numerów zmian są pomijane (`if (lesion_numbers.length === 0) return`), więc użytkownik może mieć wybrane „Kontrollbedürftige Hautveränderungen” i zero grup z numerami → payload z `lesions: []` → PUT draft zwróci 400.

**Sugestia:** Przed wysłaniem (draft/publish) w JS: jeśli `payload.overall_image_assessment === "CONTROL_NEEDED"` i `payload.lesions.length === 0`, pokazać komunikat (np. „Bitte mindestens eine Läsion mit Nummern angeben“) i nie wysyłać requestu. Opcjonalnie: przy przełączeniu na CONTROL_NEEDED wymusić co najmniej jedną grupę z numerami.

Wymagaj przynajmniej 1 grupy

### 1.2 [Niski] POST /medical-documents bez sprawdzenia statusu intake

**Gdzie:** `apps/medical/api_views.py` – `medical_documents_view` (POST), `apps/medical/services.py` – `create_or_get_medical_document`.

**Problem:** Serwis sprawdza tylko `intake_form.queue_entry_id == queue_entry_id`, nie sprawdza `form_status == SUBMITTED`. Przez API można utworzyć dokument medyczny dla ankiety w statusie IN_PROGRESS.

**Sugestia:** W `create_or_get_medical_document` (lub w widoku API przed wywołaniem) dodać warunek: `if intake_form.form_status != IntakeStatus.SUBMITTED: raise DomainError("Intake form must be submitted.")`. Spójne z tym, co robi `doctor_open_by_queue_view` po stronie HTML.

Dodaj sprawdzenie

### 1.3 [Niski] Przekierowanie przy zmianie języka gubi filtry (lista)

**Gdzie:** `cogitomedica/doctor_views.py` – `doctor_list_view`.

**Problem:** Gdy użytkownik jest na liście z filtrami (np. `?status=DRAFT&queue_date=2025-02-22&patient_search=Mueller`) i zmieni język (`?lang=en`), wykonywane jest `return redirect("doctor-list")` bez query stringu – filtry znikają.

**Sugestia:** Przy przekierowaniu zachować aktualne parametry: `redirect(request.path + "?" + request.GET.urlencode())` (po ewentualnej aktualizacji tylko `lang` w GET), albo nie przekierowywać przy samym `lang`, tylko ustawić sesję i odświeżyć z zachowaniem GET.

Popraw

---

## 2. Luki bezpieczeństwa i ochrona danych

### 2.1 [Wysoki] IDOR – brak autoryzacji „właściciela” dokumentu

**Gdzie:** Wszystkie endpointy operujące na `medical_document_id` lub `version_id`: `medical_document_detail_view`, `medical_document_draft_view`, `medical_document_publish_view`, `medical_document_versions_view`, `medical_document_version_detail_view`; oraz `doctor_document_detail_view` (HTML).

**Problem:** Autoryzacja ogranicza się do roli DOCTOR/ADMIN. Każdy zalogowany lekarz/admin może odczytać, edytować lub publikować **dowolny** dokument po podstawieniu UUID (np. z innej placówki/gabinetu), jeśli w systemie nie ma dodatkowego podziału po klinice.

**Sugestia:** Wprowadzić zasadę „dokument widoczny tylko w kontekście swojej jednostki” (np. clinic_site / consulting_room / site przypisany do użytkownika). Przed każdą operacją na dokumencie: pobrać dokument z `select_related("queue_entry__daily_queue__clinic_site")` i sprawdzić, czy `request.user` ma prawo do tej kliniki (np. pole `user.clinic_site_id` lub tabela dostępu). W razie braku uprawnień zwracać 404. To samo dla `doctor_open_by_queue_view` (queue_entry → daily_queue → clinic_site).

Pilnuj dokumnetów lekarz może widzieć dokumenty tylko dla swojego gabinetu.

### 2.2 [Średni] Potencjalny XSS w widoku szczegółów (intake summary)

**Gdzie:** `templates/doctor/detail.html` – budowanie HTML sekcji „Ankieta (wywiad)” i ustawianie `el("intake-summary").innerHTML = html`.

**Problem:** Do `html` trafiają: `p.last_name`, `p.first_name`, `p.date_of_birth`, `q.question_text`, `q.question_code`, `answerText` (w tym etykiety opcji i `free_text` z ankiety). Jeśli którekolwiek z tych pól zawierało by znaki `<`, `>`, `"`, `'` lub fragmenty JavaScript (np. treść pytania/odpowiedzi z konfiguracji lub od pacjenta), mogłoby dojść do wykonania kodu w przeglądarce.

**Sugestia:** Przed wstawieniem do `innerHTML` escapować wszystkie wartości (np. funkcja `escapeHtml(s)` zamieniająca `&`, `<`, `>`, `"`, `'` na encje). Alternatywnie: budować DOM przez `createElement` / `textContent` zamiast konkatenacji stringów do `innerHTML`.

Eskapuj

---


## 4. Utrzymanie i dług techniczny

### 4.1 [Średni] Duża ilość logiki w inline JS (detail.html)

**Gdzie:** `templates/doctor/detail.html` – blok `{% block extrajs %}` (~180 linii).

**Problem:** Logika formularza Befund (budowanie payloadu, wywołania API, obsługa grup zmian, prefill) jest w jednym skrypcie inline. Trudniejsze testy jednostkowe, brak ponownego użycia, ryzyko konfliktów przy merge’ach.

**Sugestia:** Przenieść JS do pliku np. `static/doctor/js/befund-form.js`, ładowanego z konfiguracją (documentId, apiBase, context) z `json_script`. Ułatwi to testy (np. buildPayload dla edge cases) i dalsze rozszerzenia (np. historia wersji, szablony).

Wykonaj refaktor

### 4.2 [Niski] Powielenie parsowania parametrów listy (HTML vs API)

**Gdzie:** `doctor_views.doctor_list_view` (status, queue_date, patient_search, page, page_size) i `medical_documents_view` (GET) – niemal ten sam zestaw parametrów i parsowanie.

**Problem:** Zmiana logiki filtrów (np. nowy filtr, walidacja) wymaga zmian w dwóch miejscach.

**Sugestia:** Wydzielić wspólną funkcję (np. w `apps/medical/services.py` lub w `core`) `parse_medical_documents_list_params(request) -> dict` i używać jej w obu widokach. Lista dokumentów w API i w HTML będzie spójna.

Wykonaj refaktor

### 4.3 [Niski] Stałe „de-DE” w JS

**Gdzie:** `templates/doctor/detail.html` – `authoring_locale: 'de-DE'` w `buildPayload()`.

**Problem:** Język generowania jest na sztywno ustawiony; panel ma wybór języka (DE/EN/PL) w `ui`/`lang`, ale nie jest on przekazywany do payloadu.

**Sugestia:** Czytać `authoring_locale` z konfiguracji przekazanej do panelu (np. z backendu na podstawie `lang` lub `form_locale`), np. `PANEL.context.authoring_locale || 'de-DE'`, i używać w `buildPayload()`.

Uwzględniaj język

---

## 5. Styl kodu i spójność

### 5.1 [Niski] Komunikaty błędów tylko po niemiecku w kilku miejscach

**Gdzie:** `templates/doctor/detail.html` – `alertMsg('danger', json.error || 'Fehler')`, `'Text generiert.'`, `'Entwurf gespeichert.'`, `'Netzwerkfehler.'` itd.

**Problem:** Reszta panelu korzysta z `ui` (DE/EN/PL); komunikaty po wywołaniach API są na sztywno po niemiecku.

**Sugestia:** Przekazać w `panel_data.ui` (lub osobno) klucze dla komunikatów (np. `msg_generate_success`, `msg_save_success`, `msg_network_error`, `msg_error`) i w JS używać `PANEL.ui?.msg_* || '...'`, żeby zachować spójność z resztą interfejsu i językiem użytkownika.

Uwzględniaj język

### 5.2 [Niski] Brak rate limiting / idempotencji po stronie klienta (publish)

**Gdzie:** `templates/doctor/detail.html` – przycisk „Zatwierdź i wyślij”.

**Problem:** Przy każdym kliknięciu generowany jest nowy `publish_request_id`. Backend jest idempotentny względem tego ID, ale użytkownik może wielokrotnie klikać i wysyłać wiele żądań (draft + publish), co może być mylące („Publikation in Bearbeitung”).

**Sugestia:** Po udanym publish wyłączyć przycisk lub zamienić na stan „Wysłano – publikacja w toku” i ewentualnie blokować ponowne wysłanie do czasu odświeżenia strony. Opcjonalnie: po pierwszym kliknięciu zapamiętać `publish_request_id` w zmiennej i przy kolejnych requestach (jeśli by były wysyłane) używać tego samego ID.

Wyłącz przycik

