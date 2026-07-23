# Wgranie zewnętrznego badania (recepcja)

Ten rozdział opisuje ścieżkę **External upload**: recepcja (lub administrator / manager wg uprawnień) wgrywa gotowy plik PDF wyniku z zewnętrznego źródła (np. laboratorium, inna placówka), powiązany z wizytą i ankietą pacjenta. To **nie** jest panel Befundu — lekarz nie edytuje treści klinicznej w formularzu skórnym; dokument w portalu pacjenta to opublikowany PDF po przetworzeniu w tle.

## Interfejs HTML (hub w Django Admin)

Recepcja / admin / manager mogą przejść całą ścieżkę **bez wywoływania API ręcznie**:

1. **Sidebar Unfold** — sekcja „Zewnętrzne badanie” z linkiem do huba (ta sama rola co API).
2. **Dashboard recepcji** (`/admin/reception-dashboard/`) — skróty do huba papierowego i external upload.
3. **Hub** — `GET /admin/external-upload/`: filtr statusu ankiety (`SUBMITTED` / `REOPENED` / oba), wybór wpisu kolejki, przejście do ekranu wpisu.
4. **Ekran wpisu** — `GET /admin/external-upload/<queue_entry_id>/`: tożsamość, lista załączników (`MATCHED` / `ACCEPTED`), upload PDF, wybór załącznika, podgląd, publikacja z drugim potwierdzeniem i opcjonalnym `resend_sms`, start rewizji po publikacji.

![Sidebar — sekcja Zewnętrzne badanie](/docs/manual/assets/screenshots/reception-external-upload-00-sidebar.png)

![Hub external upload — filtr i wybór wpisu](/docs/manual/assets/screenshots/reception-external-upload-01-hub.png)

![Ekran wpisu — tożsamość pacjenta i wizyty](/docs/manual/assets/screenshots/reception-external-upload-02-entry-identity.png)

![Upload PDF i lista załączników](/docs/manual/assets/screenshots/reception-external-upload-03-entry-upload-select.png)

![Podgląd PDF (link w nowej karcie)](/docs/manual/assets/screenshots/reception-external-upload-04-preview.png)

![Publikacja — locale, SMS, drugie potwierdzenie](/docs/manual/assets/screenshots/reception-external-upload-05-publish-confirm.png)

## Kiedy można wgrać plik

- Dla wpisu kolejki musi istnieć **ankieta** (`PatientIntakeForm`) w stanie **wysłana** lub **ponownie otwarta do korekt** (`SUBMITTED` albo `REOPENED`).
- Wymagany jest **numer telefonu** pacjenta (powiadomienie SMS po publikacji, jak przy Befundzie).
- Rola: **Recepcja**, **Administrator** lub **Manager** (lekarz w tej ścieżce nie wgrywa pliku).

## Limity i format

- Dozwolony jest wyłącznie **PDF** (typ MIME, sygnatura `%PDF`, walidacja struktury).
- **Maksymalny rozmiar pliku: 250 MB** (zgodnie z limitem nginx / timeout Gunicorna w środowisku produkcyjnym).
- Większe pliki są strumieniowane na dysk tymczasowy (`/tmp`); przy bardzo dużych plikach **cały worker HTTP** może być zajęty na czas uploadu (w prod często `--workers 1`) — unikaj szczytu wizyt przy największych plikach.

## Gdzie ląduje plik na HiDrive (ważne dla IT i recepcji)

- Aplikacja zapisuje reception upload pod prefiksem  
  **`{HIDRIVE_INCOMING_PATH}/external-upload/{queue_entry_id}/`**  
  (np. `/incoming/external-upload/<uuid-wpisu>/Nazwa.pdf`).
- Pliki laboratorium wrzucane „ręcznie” do **`/incoming/`** (bez podfolderu `external-upload/`) nadal obsługuje **osobna** logika dopasowania nazw do pacjenta w panelu lekarza — patrz [hidrive_incoming_reception.md](hidrive_incoming_reception.md).
- **Izolacja:** przy sprawdzaniu bramki PDF z `/incoming` dla Befundu system **pomija** całą gałąź `external-upload/`, żeby wynik wgrany przez recepcję nie był mylony z plikiem labu o podobnej nazwie.

## HTML hub a API

| Akcja w UI (POST `action=` lub GET) | Odpowiednik w REST / usłudze |
| --- | --- |
| Upload formularza (`action=upload`, plik `file`) | Ten sam łańcuch co `POST /api/v1/medical-documents/external-upload/upload` (multipart): utworzenie dokumentu `EXTERNAL_UPLOAD`, zapis na HiDrive, powiązanie z szkicem — w kodzie `create_external_upload_pdf_and_bind_draft`. |
| Wybór załącznika (`action=select`, `attachment_id`) | `POST /api/v1/medical-documents/{id}/external-upload/select-attachment` z JSON `{"attachment_id": "..."}`. |
| Start rewizji (`action=start_revision`) | `POST /api/v1/medical-documents/{id}/external-upload/revision/start`. |
| Publikacja (`action=publish`, `publish_request_id`, `publish_locale`, `verification_ack`, opcjonalnie `resend_sms`) | `POST /api/v1/medical-documents/{id}/external-upload/publish` z tym samym zestawem pól w JSON. |
| Podgląd PDF (link w nowej karcie) | `GET /api/v1/medical-documents/{id}/external-upload/preview-pdf` (sesja cookie przeglądarki; opcjonalnie osobna baza URL z `EXTERNAL_UPLOAD_PREVIEW_API_BASE_URL`). |

## Przebieg operacyjny (wysoki poziom, także przez API)

1. **Wybór wpisu kolejki** — hub HTML lub bezpośredni URL `/admin/external-upload/<uuid>/` (uprawnienia i filtr jak wyżej).
2. **Potwierdzenie tożsamości** na ekranie (imię, nazwisko, data urodzenia, telefon, data kolejki).
3. **Upload** pliku PDF (multipart).
4. **Wybór załącznika** do wersji roboczej, jeśli jest kilka lub zmieniasz wybór.
5. **Podgląd** (opcjonalnie) — pełny odczyt z HiDrive do przeglądarki (duży plik = duży transfer i pamięć).
6. **Drugie potwierdzenie** w UI (checkbox): pacjent na ekranie zgadza się z plikiem i decyzją o publikacji.
7. **Publikacja** z `publish_request_id` (UUID na żądanie), `publish_locale` (`de-DE`, `en-GB`, `pl-PL`), `resend_sms` (przy pierwszej publikacji zwykle wyłączone; przy korekcie / ponownym SMS — według procedury).

Po publikacji uruchamia się ten sam **łańcuch outbox** co dla Befundu: generowanie materialnego PDF (w tym wypadku z wybranego pliku z HiDrive), upload na ścieżkę pacjenta, SMS.

## Korekta po publikacji

- **Nowa rewizja bez zmiany pliku** (np. ponowne wysłanie SMS):  
  `POST .../external-upload/revision/start`, potem wybór **tego samego** załącznika w statusie `ACCEPTED` (już w `/processed/...`) przez `select-attachment`, ponownie `publish` z `resend_sms: true`.
- **Nowy plik:** `revision/start`, nowy upload (nowy `MATCHED` pod `/incoming/external-upload/...`), wybór, publish.
- **Cofnięcie dostępu pacjenta** do opublikowanej wersji: istniejący endpoint rewokacji dokumentu medycznego (rola i reguły jak w panelu lekarza / nadzór — zgodnie z konfiguracją produktu).

## Świadome ograniczenia (MVP)

- Brak skanera antywirusowego przy uploadzie (tylko walidacja PDF) — pliki musi pochodzić z zaufanego źródła operacyjnego.
- Podgląd i generowanie PDF dla bardzo dużych plików zużywają znaczną pamięć RAM po stronie serwera — zaplanuj zasoby VPS i unikaj równoległych operacji na kilku megaplikach, jeśli to możliwe.

## Powiązane dokumenty

- [hidrive_incoming_reception.md](hidrive_incoming_reception.md) — wrzutki „gołym” PDF do `/incoming/` pod kątem dopasowania do pacjenta (lab).
- [01-rejestracja.md](01-rejestracja.md) — recepcja, kolejki, wpisy.
- [03-doktor.md](03-doktor.md) — panel lekarza (Befund); dokument `EXTERNAL_UPLOAD` w panelu lekarza może być tylko do odczytu — szczegóły zależą od wdrożenia UI.
- Scenariusz filmowy: [SC-020](scenariusze.md#sc-020).
