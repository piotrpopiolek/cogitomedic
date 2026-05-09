# Wgranie zewnętrznego badania (recepcja)

Ten rozdział opisuje ścieżkę **External upload**: recepcja (lub administrator / manager wg uprawnień) wgrywa gotowy plik PDF wyniku z zewnętrznego źródła (np. laboratorium, inna placówka), powiązany z wizytą i ankietą pacjenta. To **nie** jest panel Befundu — lekarz nie edytuje treści klinicznej w formularzu skórnym; dokument w portalu pacjenta to opublikowany PDF po przetworzeniu w tle.

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

## Przebieg operacyjny (wysoki poziom)

1. **Wybór wpisu kolejki** pacjenta z gotową ankietą (w produkcji: dedykowany hub / lista — po wdrożeniu UI).
2. **Potwierdzenie tożsamości** na ekranie (imię, nazwisko, data urodzenia, telefon, data kolejki).
3. **Upload** pliku PDF (multipart, endpoint API `POST /api/v1/medical-documents/external-upload/upload` z polami `queue_entry_id` i `file`).
4. **Wybór załącznika** do wersji roboczej, jeśli jest kilka lub zmieniasz wybór:  
   `POST /api/v1/medical-documents/{id}/external-upload/select-attachment` z JSON `{"attachment_id": "..."}`.
5. **Podgląd** (opcjonalnie):  
   `GET /api/v1/medical-documents/{id}/external-upload/preview-pdf` — pełny odczyt z HiDrive do przeglądarki (duży plik = duży transfer i pamięć).
6. **Drugie potwierdzenie** w UI (checkbox / modal): pacjent na ekranie zgadza się z plikiem i decyzją o publikacji.
7. **Publikacja:**  
   `POST /api/v1/medical-documents/{id}/external-upload/publish`  
   z ciałem JSON m.in. `publish_request_id` (unikalny UUID na żądanie), `publish_locale` (`de-DE`, `en-GB`, `pl-PL` itd. wg kontraktu), `resend_sms` (przy pierwszej publikacji zwykle `false`; przy korekcie / ponownym wysłaniu SMS — zwykle `true` po uzgodnieniu procedury).

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
