# Przegląd systemu Cogitomedica Digital Consents

Ten dokument zbiera pojęcia wspólne dla wszystkich ról. Szczegółowe procedury są w pozostałych plikach w tym katalogu.

![Przegląd procesu](/docs/manual/assets/screenshots/overview-01-process-diagram.png)

*Powyżej: uproszczony schemat kolejności kroków (recepcja → tablet → lekarz → system → pacjent).*

## Cel systemu

Cyfryzacja przyjęcia pacjenta: ankieta anamnestyczna i zgody na tablecie, dokumentacja medyczna u lekarza (Befund), generowanie PDF, archiwizacja (HiDrive) oraz powiadomienie SMS o charakterze wyłącznie logistycznym. Pacjent pobiera gotową dokumentację przez osobny portal wyników (weryfikacja telefon + data urodzenia + kod OTP).

Interfejs personelu i pacjenta obsługuje języki: **niemiecki, angielski, polski** (wybór zależy od ekranu i ustawień sesji).

## Role w systemie

Uprawnienia personelu wynikają z roli przypisanej do konta: `Reception`, `Doctor`, `Admin`, `Tablet`, `Manager`.

| Grupa / rola | Główny dostęp |
|--------------|----------------|
| **Reception** | Panel administracyjny (`/admin/`) — kolejki dzienne, pacjenci, wpisy kolejki, importy, podgląd PDF, dashboard recepcji |
| **Tablet** | Interfejs `/tablet/` — wybór kolejki i pacjenta, uruchomienie formularza dla pacjenta |
| **Doctor** | Panel `/doctor/` — kolejka pracy medycznej, formularz Befund, szkic / publikacja |
| **Manager** | Panel administracyjny i dashboard recepcji (kolejki, pacjenci, urządzenia, import, dokumenty) + panel `/doctor/` do nadzoru operacyjnego |
| **Admin** | Pełny panel administracyjny + te same panele co lekarz i (w razie potrzeby) recepcja/tablet |

Uwaga: konto **Admin** lub **Reception** może zalogować się na `/tablet/` (np. awaria dedykowanego konta TABLET). Zalecane jest jednak **osobne konto Tablet** na urządzeniu w poczekalni.

## Najważniejsze adresy

| Ścieżka | Zawartość |
|---------|-----------|
| `/admin/` | Panel administracyjny — logowanie personelu |
| `/admin/reception-dashboard/` | Dashboard operacyjny recepcji (importy, błędy outbox) |
| `/admin/intake-documents/` | Lista i podgląd wersji PDF dokumentów intake |
| `/tablet/` | Poczekalnia — kolejki i formularz pacjenta |
| `/doctor/` | Panel lekarza — lista dokumentów, edycja Befund |
| `/` (root) | Portal pacjenta — logowanie do wyników |
| `/otp/` | Wpis kodu OTP (portal pacjenta) |
| `/documents/` | Lista dokumentów do pobrania (po OTP) |

Dokładne ścieżki mogą być poprzedzone domeną produkcyjną (np. portal wyników na dedykowanym hostie).

## Przebieg dnia pracy (uproszczony)

1. **Recepcja** tworzy lub importuje **kolejkę dzienną** i wpisy pacjentów dla wybranej placówki, gabinetu i zmiany.
2. **Tablet** (lub personel na tablecie): wybór **dzisiejszej** kolejki → pacjenta → uruchomienie **sesji formularza** (ankieta, zgody, schemat ciała, podpis). Po wysłaniu formularz ma status zakończenia po stronie pacjenta; wpis kolejki przechodzi w stan wskazujący na ukończenie przez pacjenta.
3. **Lekarz** otwiera dokument medyczny powiązany z wizytą, uzupełnia **Befund**, zapisuje **szkic** lub **publikuje**. Publikacja uruchamia w tle generowanie PDF, upload do archiwum i SMS logistyczny do pacjenta.
4. **Pacjent** (poza sesją placówki) otrzymuje SMS bez treści medycznej, loguje się na portal wyników, podaje OTP i pobiera PDF.

## Stany wpisu kolejki

Stany w systemie obejmują m.in. (kolejność procesu):

- `WAITING` — oczekuje.
- `IN_PROGRESS` — pacjent w trakcie wypełniania (może się zmieniać w zależności od integracji).
- `PATIENT_COMPLETED` — pacjent zakończył formularz intake na tablecie.
- `DOCTOR_IN_PROGRESS` — lekarz pracuje nad dokumentem.
- `PUBLISHED` — dokument opublikowany.
- `CANCELLED` — anulowany.

W zależności od wersji językowej interfejsu nazwy statusów mogą być po polsku lub po angielsku.

## Co dzieje się po publikacji

Po publikacji dokumentu medycznego system wykonuje kolejne kroki: generowanie PDF, zapis do HiDrive i wysłanie SMS. Statusy tych kroków są widoczne w panelu lekarza.

## Gdzie szukać dalszych informacji

- Wymagania produktu: [`.ai/prd.md`](../../.ai/prd.md)
- Dokumentacja dla działu IT: [`.ai/api-plan-pl.md`](../../.ai/api-plan-pl.md)

## Indeks instrukcji

- [Recepcja — zarządzanie kolejką i import](01-rejestracja.md)
- [Recepcja — wgranie zewnętrznego badania (PDF spoza Befundu)](07-wgranie-zewnetrznego-badania.md)
- [Zmiana danych osobowych pacjenta (krok po kroku)](06-zmiana-danych-pacjenta.md)
- [Tablet — poczekalnia i formularz pacjenta](02-tablet.md)
- [Lekarz — panel Befund](03-doktor.md)
- [Administrator — konfiguracja i utrzymanie](04-administrator.md)
- [Administrator / Manager — autoryzacja ścieżki papierowej (T1, T1′)](04-administrator-paper-intake.md)
- [Ścieżka papierowa — diagram procesu (T1 / T2)](paper_intake_flow.md)
- [Pacjent — portal wyników](05-pacjent-wyniki.md)
