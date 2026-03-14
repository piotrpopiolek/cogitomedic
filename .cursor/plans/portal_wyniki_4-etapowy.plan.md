---
name: Portal wyniki 4-etapowy
overview: "Plan implementacji 4-etapowego procesu udostępniania wyników pacjentowi (US-018, PRD 3.4a): wysyłka SMS logistycznego, integracja SMSApi, nowa aplikacja patient_results z logowaniem phone+DOB, OTP 15 min oraz serwowaniem PDF przez HTTPS."
todos: []
isProject: false
---

# Plan implementacji – portal wyniki (4 etapy)

## Kontekst i zakres

Proces udostępniania zgodnie z PRD 3.4a i US-018:

1. **SMS logistyczny** – treść „Nowa dokumentacja w Cogito" (bez linku); wysyłany po publikacji Befund
2. **Logowanie cross-verification** – pacjent na wyniki.cogitomedica.pl; phone + date_of_birth
3. **OTP 15 min** – 6-cyfrowy kod, MFA
4. **Dostęp do PDF** – serwowanie przez HTTPS; logi audytowe; filtrowanie wycofanych publikacji

**Stan wyjściowy (z analizy kodu):**

- Handler `SMS_SEND` w [apps/outbox/services.py](apps/outbox/services.py) tylko ustawia `sms_sent` – brak wywołania SMSApi
- Brak endpointów dla pacjenta (publicznych, bez staff auth)
- `smsapi-client` w `requirements.txt`; brak adaptera i konfiguracji
- Pacjent: `Patient` w [apps/reception/models.py](apps/reception/models.py) – `phone`, `date_of_birth` z walidacją
- PDF: `build_befund_pdf_bytes` w [apps/medical/pdf_builder.py](apps/medical/pdf_builder.py) – generuje z wersji; preview w [apps/medical/api_views.py](apps/medical/api_views.py) (linie 167–198)

---

## Architektura przepływu

```mermaid
flowchart TB
    subgraph publish [Publish Befund]
        Publish[publish_document_version]
        Publish --> Outbox
    end
    subgraph outbox [Outbox]
        Outbox[GENERATE_PDF]
        Outbox --> HIDRIVE
        HIDRIVE[HIDRIVE_UPLOAD]
        HIDRIVE --> SMS
        SMS[SMS_SEND]
    end
    subgraph sms [SMS]
        SMS --> Resolve[Resolve patient.phone]
        Resolve --> Adapter[SMSApi Adapter]
        Adapter --> Send["Send: 'Nowa dokumentacja w Cogito'"]
    end
    subgraph portal [Portal wyniki]
        Login[POST request-otp: phone, dob]
        Login --> Match{Patient match?}
        Match -->|Yes| GenOTP[Generate OTP, save session]
        GenOTP --> SendOTP[Send OTP SMS]
        SendOTP --> Verify[POST verify-otp: otp_code]
        Verify --> Session[Create session token]
        Session --> List[GET documents list]
        List --> Download[GET download/:version_id]
        Download --> PDF[Serve PDF + audit]
    end
```



---

## Faza 1: Integracja SMSApi (krok 1 procesu)

### 1.1 Adapter SMS w `apps/integrations/`

- Utworzyć moduł `apps/integrations/sms/`:
  - `client.py` – klasa `SmsAdapter` z metodą `send_sms(to: str, message: str) -> None`
  - Wykorzystać `smsapi.client.SmsApiPlClient` (smsapi.pl) lub `SmsApiComClient` (smsapi.com)
  - Konfiguracja: `SMSAPI_ACCESS_TOKEN`, `SMSAPI_USE_MOCK` (domyślnie `True` w dev)
  - Przy mock: tylko log; bez HTTP
- Dodać do [.env.example](.env.example):

```
  SMSAPI_ACCESS_TOKEN=
  SMSAPI_USE_MOCK=1
  

```

### 1.2 Modyfikacja handlera `SMS_SEND` w [apps/outbox/services.py](apps/outbox/services.py)

- Pobrać pacjenta: `version.medical_document.queue_entry.patient` (select_related)
- Znormalizować numer: `re.sub(r'\D', '', patient.phone)` lub użyć istniejącej walidacji
- Treść: `"Nowa dokumentacja w Cogito"`
- Wywołać `get_sms_adapter().send_sms(to=phone, message=text)`
- Po sukcesie: `version.sms_sent = True`, `version.sms_sent_at = now` (jak obecnie)
- Przy błędzie SMSApi: rzucić wyjątek – outbox ustawi FAILED/retry
- Zachować logikę `resend_sms` i pomijanie przy wcześniej wysłanym SMS

### 1.3 Testy

- Test jednostkowy adaptera (mock HTTP)
- Test outbox: publish → process → sprawdzenie wywołania `send_sms` i `sms_sent=True`

---

## Faza 2: Model OTP i serwis (kroki 2–3)

### 2.1 Nowa aplikacja `apps/patient_results/`

- `models.py` – model `PatientResultsOtpSession`:
  - `id` UUID PK
  - `patient_id` FK → Patient (CASCADE)
  - `phone` varchar(20) – numer, na który wysłano OTP
  - `otp_code_hash` varchar(64) – SHA-256 hash kodu (nie przechowywać plaintext)
  - `expires_at` timestamptz – ważność 15 min
  - `verified_at` timestamptz NULL – po poprawnej weryfikacji
  - `created_at`
  - Indeks: `(patient_id, expires_at)`; ograniczenie: `expires_at > created_at`
- Migracja
- `Patient.normalize_phone()` – helper do porównania (re.sub, trim)

### 2.2 Serwis domenowy `request_otp(phone: str, date_of_birth: date)`

- Walidacja wejścia: format telefonu (regex jak w Patient), DOB w rozsądnym zakresie
- `Patient.objects.filter(phone__iexact=normalize_phone(phone), date_of_birth=dob)`
- **Bez enumeracji:** jeśli brak dopasowania – zwrócić generyczną odpowiedź sukcesu („Jeśli dane są poprawne, kod został wysłany”) – ten sam timing co przy sukcesie (np. `time.sleep` minimalny lub opcjonalnie fałszywy delay)
- Przy dopasowaniu:
  - Wygenerować 6-cyfrowy OTP: `random.randint(100000, 999999)`
  - Zapis: `PatientResultsOtpSession(patient_id=..., phone=..., otp_code_hash=sha256(otp).hexdigest(), expires_at=now+15min)`
  - Wywołać `SmsAdapter.send_sms(to=phone, message=f"Kod Cogito: {otp}. Ważny 15 min.")
  - Ograniczenie rate: max 3 OTP na ten numer w ciągu 1h (query `PatientResultsOtpSession` po `created_at`)
- Zwracać zawsze ten sam typ odpowiedzi (np. `{"status": "ok"}`)

### 2.3 Serwis `verify_otp(phone: str, date_of_birth: date, otp_code: str) -> str | None`

- Znaleźć pasującą sesję: `PatientResultsOtpSession.objects.filter(patient__phone=..., patient__date_of_birth=..., expires_at__gt=now, verified_at__isnull=True)`
- Porównać hash `sha256(otp_code.strip()).hexdigest() == session.otp_code_hash`
- Rate limit: max 5 prób na sesję (licznik w modelu lub osobnym polu)
- Po sukcesie: `session.verified_at = now`, zapis; zwrócić token sesji (np. signed cookie value lub JWT z `patient_id`, `expires_at`)
- Token: krótkotrwały (np. 1h), zawiera `patient_id` – używany do pobierania PDF

---

## Faza 3: API i widoki portalu (krok 4)

### 3.1 Endpointy API (publiczne, bez staff auth)

Dodać do [cogitomedica/api_urls.py](cogitomedica/api_urls.py) i [cogitomedica/openapi_extension.py](cogitomedica/openapi_extension.py) (NO_AUTH_OPERATIONS):


| Metoda | Ścieżka                                                   | Opis                                                                                                                                      |
| ------ | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/api/v1/patient-results/request-otp`                     | Body: `{"phone": "...", "date_of_birth": "YYYY-MM-DD"}`                                                                                   |
| POST   | `/api/v1/patient-results/verify-otp`                      | Body: `{"phone": "...", "date_of_birth": "...", "otp_code": "123456"}`; Response: `{"session_token": "...", "expires_at": "..."}`         |
| GET    | `/api/v1/patient-results/documents`                       | Header: `Authorization: Bearer <session_token>` lub cookie; Response: lista dokumentów `[{id, queue_date, document_id, version_id}, ...]` |
| GET    | `/api/v1/patient-results/documents/<version_id>/download` | Zwraca PDF (FileResponse); wymaga session token                                                                                           |


### 3.2 Logika listy dokumentów

- Z tokena wyciągnąć `patient_id`
- Zapytanie: `MedicalDocumentVersion` gdzie `version_status=PUBLISHED`, `pdf_generation_status=COMPLETED`, `medical_document__queue_entry__patient_id=patient_id`
- Filtrowanie wycofanych: na razie bez pola `revoked_at` – dokument jest dostępny jeśli jest `PUBLISHED` i `doc.current_version_id == version.id` (aktualna opublikowana wersja). Opcjonalnie: dodać `version_status=WITHDRAWN` w przyszłości
- Sortowanie: `-published_at`
- Zwracać: `version_id`, `queue_date`, `document_id` (dla audytu)

### 3.3 Serwowanie PDF

- Weryfikacja tokena → `patient_id`
- Sprawdzenie: `version` należy do dokumentu, którego `queue_entry.patient_id == patient_id`
- Sprawdzenie: `version.version_status == PUBLISHED`, `pdf_generation_status == COMPLETED`
- Serwowanie:
  - Jeśli `version.pdf_local_path` istnieje i plik na dysku: `FileResponse(open(path), content_type='application/pdf')`
  - W przeciwnym razie: `build_befund_pdf_bytes(version)` → `HttpResponse(pdf_bytes, content_type='application/pdf')`
- Nagłówki: `Content-Disposition: attachment; filename="befund-{queue_date}.pdf"`
- **Audit:** `create_audit_event(event_type="PATIENT_RESULTS_PDF_DOWNLOAD", patient_id=..., medical_document_id=..., metadata={"version_id": ..., "client_ip": ..., "downloaded_at": ...})`

### 3.4 Mechanizm sesji (token)

- Opcja A: **Signed cookie** – `patient_id` + `expires_at` w cookie, klucz z `SECRET_KEY`
- Opcja B: **JWT** – `patient_id`, `expires_at`; weryfikacja w middleware lub w widoku
- Zalecane: signed cookie (spójne z resztą aplikacji); domain np. `.cogitomedica.pl` dla wyniki.cogitomedica.pl

---

## Faza 4: Frontend portalu (HTML)

### 4.1 Widoki Django (SSR)

- `path("wyniki/", include("apps.patient_results.urls"))` w [cogitomedica/urls.py](cogitomedica/urls.py)
- Szablony: `wyniki/login.html`, `wyniki/otp.html`, `wyniki/documents.html`
- Flow:
  1. `/wyniki/` – formularz phone + DOB → POST do API request-otp
  2. `/wyniki/otp/` – formularz 6 cyfr → POST do API verify-otp → redirect na listę
  3. `/wyniki/documents/` – lista dokumentów z linkami do download

### 4.2 Styl i UX

- Prosty layout RWD (Tailwind jeśli w projekcie; inaczej minimalny CSS)
- Tłumaczenia: DE/EN/PL z `translation_key` (jak tablet)
- Komunikaty błędów ogólne (bez ujawniania np. „nieprawidłowy numer”)

---

## Faza 5: Zabezpieczenia i rate limiting

- **Rate limit OTP:** max 3 request-otp na numer/h; max 5 verify-otp na sesję
- **Rate limit brute force:** django-ratelimit lub cache (Redis/in-memory) na IP
- **CORS:** jeśli front na innej domenie – konfiguracja `CORS_ALLOWED_ORIGINS` dla wyniki.cogitomedica.pl
- **CSP / nagłówki:** `X-Content-Type-Options: nosniff` na PDF

---

## Faza 6: Wycofanie publikacji (opcjonalna)

- Dodać pole `MedicalDocumentVersion.revoked_at` (timestamptz NULL)
- Endpoint w panelu lekarza: `POST /medical-documents/{id}/revoke` – ustawia `revoked_at` na bieżącej opublikowanej wersji
- W portalu: przy liście i download wykluczać wersje z `revoked_at IS NOT NULL`

---

## Kolejność wdrożenia


| Kolejność | Zadanie                                                      | Zależności         |
| --------- | ------------------------------------------------------------ | ------------------ |
| 1         | Adapter SMS + konfiguracja                                   | -                  |
| 2         | Modyfikacja SMS_SEND w outbox                                | Adapter SMS        |
| 3         | Model PatientResultsOtpSession + migracja                    | -                  |
| 4         | Serwisy request_otp, verify_otp                              | Model, Adapter SMS |
| 5         | API endpointy (request-otp, verify-otp, documents, download) | Serwisy            |
| 6         | Widoki HTML / wyniki/                                        | API                |
| 7         | Rate limiting, testy E2E                                     | Wszystko           |
| 8         | (Opcjonalnie) Revocation                                     | -                  |


---

## Pliki do utworzenia/modyfikacji


| Plik                                | Akcja                                                         |
| ----------------------------------- | ------------------------------------------------------------- |
| `apps/integrations/sms/client.py`   | Utworzyć                                                      |
| `apps/integrations/sms/__init__.py` | Utworzyć                                                      |
| `cogitomedica/settings.py`          | Dodać SMSAPI_*                                                |
| `.env.example`                      | Dodać SMSAPI_*                                                |
| `apps/outbox/services.py`           | Modyfikacja SMS_SEND                                          |
| `apps/patient_results/`             | Nowa aplikacja (models, services, api_views, urls, templates) |
| `cogitomedica/urls.py`              | path wyniki/                                                  |
| `cogitomedica/api_urls.py`          | Ścieżki patient-results                                       |
| `cogitomedica/openapi_extension.py` | NO_AUTH dla patient-results                                   |


---

## Definicja ukończenia

- SMS logistyczny wysyłany przez SMSApi po publikacji (treść zgodna z PRD)
- Pacjent może wejść na /wyniki/, podać phone+DOB, otrzymać OTP i zalogować się
- Lista opublikowanych dokumentów pacjenta po zalogowaniu
- Pobranie PDF przez HTTPS z logowaniem w audit_event
- Rate limiting OTP i verify
- Testy jednostkowe i integracyjne
- Dokumentacja w api-plan.md (endpointy patient-results)

