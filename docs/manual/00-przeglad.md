# Przegląd systemu Cogitomedica Digital Consents

Ten dokument zbiera pojęcia wspólne dla wszystkich ról. Szczegółowe procedury są w pozostałych plikach w tym katalogu.

![Przegląd procesu (diagram tekstowy generowany przy zrzutach — `scripts/capture_manual_screenshots.py`)](/docs/manual/assets/screenshots/overview-01-process-diagram.png)

*Powyżej: uproszczony schemat kolejności kroków (recepcja → tablet → lekarz → backend → pacjent). Możesz go zastąpić własnym diagramem w narzędziu graficznym, zachowując ten sam plik `overview-01-process-diagram.png`.*

## Cel systemu

Cyfryzacja przyjęcia pacjenta: ankieta anamnestyczna i zgody na tablecie, dokumentacja medyczna u lekarza (Befund), generowanie PDF, archiwizacja (HiDrive) oraz powiadomienie SMS o charakterze wyłącznie logistycznym. Pacjent pobiera gotową dokumentację przez osobny portal wyników (weryfikacja telefon + data urodzenia + kod OTP).

Interfejs personelu i pacjenta obsługuje języki: **niemiecki, angielski, polski** (wybór zależy od ekranu i ustawień sesji).

## Role w systemie

Uprawnienia personelu wynikają z **grup Django** przypisanych do konta: `Reception`, `Doctor`, `Admin`, `Tablet`. Jedno konto może mieć jedną logiczną rolę operacyjną (typowo jedna grupa).

| Grupa / rola | Główny dostęp |
|--------------|----------------|
| **Reception** | Panel administracyjny Django (`/admin/`) — kolejki dzienne, pacjenci, wpisy kolejki, importy, podgląd PDF intake, dashboard recepcji |
| **Tablet** | Interfejs `/tablet/` — wybór kolejki i pacjenta, uruchomienie formularza dla pacjenta |
| **Doctor** | Panel `/doctor/` — kolejka pracy medycznej, formularz Befund, szkic / publikacja |
| **Admin** | Pełny Django Admin + te same panele co lekarz i (według potrzeb) recepcja/tablet |

Uwaga: konto **Admin** lub **Reception** może zalogować się na `/tablet/` (np. awaria dedykowanego konta TABLET). Zalecane jest jednak **osobne konto Tablet** na urządzeniu w poczekalni.

## Adresy URL (względem hosta placówki)

| Ścieżka | Zawartość |
|---------|-----------|
| `/admin/` | Django Admin (Unfold) — logowanie personelu z `is_staff` |
| `/admin/reception-dashboard/` | Dashboard operacyjny recepcji (importy, błędy outbox) |
| `/admin/intake-documents/` | Lista i podgląd wersji PDF dokumentów intake |
| `/tablet/` | Poczekalnia — kolejki i formularz pacjenta |
| `/doctor/` | Panel lekarza — lista dokumentów, edycja Befund |
| `/` (root) | Portal pacjenta — logowanie do wyników |
| `/otp/` | Wpis kodu OTP (portal pacjenta) |
| `/documents/` | Lista dokumentów do pobrania (po OTP) |

Dokładne ścieżki mogą być poprzedzone domeną produkcyjną (np. portal wyników na dedykowanym hostie).

## Przebieg dnia pracy (uproszczony)

1. **Recepcja** tworzy lub importuje **kolejkę dzienną** (`DailyQueue`) i wpisy pacjentów (`QueueEntry`) dla wybranej placówki, gabinetu i zmiany.
2. **Tablet** (lub personel na tablecie): wybór **dzisiejszej** kolejki → pacjenta → uruchomienie **sesji formularza** (ankieta, zgody, schemat ciała, podpis). Po wysłaniu formularz ma status zakończenia po stronie pacjenta; wpis kolejki przechodzi w stan wskazujący na ukończenie przez pacjenta.
3. **Lekarz** otwiera dokument medyczny powiązany z wizytą, uzupełnia **Befund**, zapisuje **szkic** lub **publikuje**. Publikacja uruchamia w tle generowanie PDF, upload do archiwum i SMS logistyczny do pacjenta.
4. **Pacjent** (poza sesją placówki) otrzymuje SMS bez treści medycznej, loguje się na portal wyników, podaje OTP i pobiera PDF.

## Stany wpisu kolejki (`QueueEntry`)

Stany w systemie obejmują m.in. (kolejność procesu):

- `WAITING` — oczekuje.
- `IN_PROGRESS` — pacjent w trakcie wypełniania (może się zmieniać w zależności od integracji).
- `PATIENT_COMPLETED` — pacjent zakończył formularz intake na tablecie.
- `DOCTOR_IN_PROGRESS` — lekarz pracuje nad dokumentem.
- `PUBLISHED` — dokument opublikowany.
- `CANCELLED` — anulowany.

Widoczne etykiety na listach mogą być po angielsku w interfejsie administracyjnym — powyższe nazwy techniczne odpowiadają polom w bazie.

## Proces backendowy po publikacji (informacja)

Po publikacji dokumentu medycznego kolejka zadań realizuje m.in.: generowanie PDF → zapis do HiDrive (lub mock) → SMS. Statusy **PDF / HiDrive / SMS** są widoczne w panelu lekarza w liście dokumentów. Błędy w tym łańcuchu powinny być monitorowane przez administrację (outbox, dashboard recepcji).

## Gdzie szukać dalszych informacji

- Wymagania produktu: [`.ai/prd.md`](../../.ai/prd.md)
- API (dla administratorów IT): [`.ai/api-plan-pl.md`](../../.ai/api-plan-pl.md), Swagger pod `/api/docs/swagger/` (po zalogowaniu do admina)

## Indeks instrukcji

- [Recepcja — zarządzanie kolejką i import](01-rejestracja.md)
- [Tablet — poczekalnia i formularz pacjenta](02-tablet.md)
- [Lekarz — panel Befund](03-doktor.md)
- [Administrator — konfiguracja i utrzymanie](04-administrator.md)
- [Pacjent — portal wyników](05-pacjent-wyniki.md)
