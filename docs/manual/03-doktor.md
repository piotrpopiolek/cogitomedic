# Instrukcja: Lekarz (rola Doctor), Manager i administrator w panelu medycznym

Panel pod **`/doctor/`** służy do przeglądania **kolejki dokumentów medycznych**, uzupełniania **Befund** (opis badania), zapisywania **szkicu**, **publikacji** oraz — w razie potrzeby — **ponownej publikacji** z nową wersją PDF.

Dostęp: grupy **Doctor**, **Admin** lub **Manager** (te konta korzystają z tego samego interfejsu HTML; **Manager** — nadzór operacyjny, patrz [Przegląd](00-przeglad.md)).

## Wymagania wstępne

- Konto z grupą **Doctor**, **Admin** lub **Manager** (dla Managera: zakres zgodny z polityką placówki i uprawnieniami grupy).
- Lekarz ma przypisane **placówki (`clinic_sites`)** tam, gdzie moduły rejestracji/tabletu tego wymagają. **Kolejka dokumentów Befund** w panelu `/doctor/` nie opiera się na przypisaniu lekarza do zmiany: szkice (**DRAFT**) i wpisy z ukończoną ankietą bez jeszcze utworzonego dokumentu są **wspólne dla wszystkich lekarzy**; dokument **opublikowany** (**PUBLISHED**) widzi zwykle **twórca dokumentu** (lekarz, który pierwszy utworzył rekord z wpisu kolejki), a dodatkowo lekarz **przypisany do zmiany** w kolejce — jeśli pole przypisania jest używane w danej placówce.
- Przeglądarka z obsługą JavaScript (panel szczegółów dokumentu komunikuje się z API `/api/v1/`).

---

## 1. Logowanie

1. Otwórz **`/doctor/login/`**.
2. Wprowadź **nazwę użytkownika** i **hasło**.
3. **Język interfejsu panelu lekarza:** linki `?lang=de`, `?lang=en`, `?lang=pl` (lub wybór na stronie logowania) — ustawienie zapisywane jest w sesji (`doctor_lang`).
4. Po zalogowaniu następuje przekierowanie na **`/doctor/`** (lista dokumentów).

![Logowanie lekarza](/docs/manual/assets/screenshots/doctor-01-login.png)

**Komunikat błędu** przy złych danych jest ogólny (np. brak uprawnień lub złe hasło — dokładna treść zależy od szablonu).

---

## 2. Lista dokumentów (Work queue) — `/doctor/`

Na liście pojawiają się wpisy z **ukończoną ankietą** (`SUBMITTED`) oraz powiązany dokument medyczny (lub możliwość jego utworzenia). **Szkice (DRAFT)** oraz wpisy **oczekujące na pierwsze utworzenie dokumentu** są widoczne dla **każdego** użytkownika z dostępem do panelu w roli **Doctor** (oraz **Admin** / **Manager** w tym samym widoku) — można przejąć opisanie od kolegi po blokadzie edycji (patrz niżej); **Admin** i **Manager** mogą w razie potrzeby zapisać szkic lub opublikować mimo aktywnej blokady innego użytkownika (nadzór). **Dokument opublikowany** w tej samej tabeli zobaczysz, jeśli **Ty go utworzyłeś** (jesteś twórcą rekordu) lub jesteś **lekarzem przypisanym do danej zmiany** w kolejce (gdy to pole jest wypełnione).

Tabela pokazuje m.in.:

- **Pacjent** (nazwisko, imię),
- **Data** kolejki,
- **Status dokumentu** — np. **DRAFT** (szkic), **PUBLISHED** (opublikowany),
- **PDF** — status generowania pliku PDF (np. COMPLETED, PENDING, FAILED),
- **HiDrive** — status zapisu do archiwum,
- **SMS** — status wysyłki powiadomienia logistycznego,
- Kolumna akcji: **Otwórz** (`Öffnen` / odpowiednik w wybranym języku).

**Blokada edycji (szkic / semafor):** Gdy na dokumencie w stanie **DRAFT** obowiązuje **aktywna blokada edycji** (ktoś ma otwarty szczegół w trybie edycji), wiersz jest **podświetlony na żółto (amber)**; przy nazwisku — jeśli to **inny** lekarz — pojawia się ikona kłódki i podpis (**kto edytuje**). Przycisk **Otwórz** jest **nieaktywny**, gdy edytuje **inny** użytkownik (nie wejdziesz w edycję, dopóki blokada jest ważna — maks. 24 godziny lub do zwolnienia / publikacji). **Zielone** podświetlenie wiersza oznacza dokument **opublikowany** z **ukończonym łańcuchem**: PDF wygenerowany, zapis do HiDrive oraz **SMS logistyczny wysłany**.

### Filtry (formularz nad tabelą)

- **Status** — szkic / opublikowany / wszystkie (zależnie od opcji).
- **Data kolejki** (`queue_date`).
- **Wyszukiwanie pacjenta** (pole tekstowe).

![Lista dokumentów z filtrami](/docs/manual/assets/screenshots/doctor-02-list-filters.png)

### Otwieranie dokumentu

- Jeśli dokument już istnieje: link prowadzi do **`/doctor/<medical_document_id>/`** (dostęp do szkicu: wspólna kolejka dla **Doctor**; **Admin** i **Manager** — jak wyżej; do opublikowanego — wg zasad listy).
- Jeśli jeszcze nie: link używa **`/doctor/open/<queue_entry_id>/`** — serwer tworzy lub pobiera dokument medyczny dla wpisu kolejki z **ukończonym** formularzem intake (`SUBMITTED`). Każdy użytkownik z odpowiednią rolą może wykonać ten krok dla wspólnej kolejki. Gdy ankieta nie jest zakończona, zobaczysz **komunikat błędu** (np. ankieta nieukończona).

**Audyt:** odczyty i zapis przez API `/api/v1/` są rejestrowane w dzienniku zdarzeń (np. podgląd dokumentu); przy współdzieleniu szkiców kolejne wejścia różnych lekarzy dają **osobne wpisy** z identyfikatorem użytkownika.

![Komunikat błędu — brak ukończonej ankiety](/docs/manual/assets/screenshots/doctor-03-error-no-intake.png)

---

## 3. Szczegóły dokumentu i formularz Befund — `/doctor/<medical_document_id>/`

Przy wejściu na stronę szkicu system **próbuje nadać blokadę edycji**. Jeśli dokument jest już edytowany przez innego użytkownika, zobaczysz **komunikat błędu** zamiast formularza (HTTP 423). Po **opuszczeniu strony** przeglądarka wysyła żądanie **zwolnienia blokady** (best-effort). **Publikacja** również zwalnia blokadę.

### 3.1 Co zawiera ekran

- Podsumowanie danych z intake (zgodnie z implementacją): zgody, schemat ciała, anamneza.
- Część medyczna **Befund** — m.in.:
  - zakres badania, typ skóry Fitzpatrick, ocena globalna,
  - **grupy zmian** (lesions): numery zmian z wideodermatoskopu (`lesion_numbers`), cechy dermatoskopowe, ocena kliniczna, ryzyko złośliwości,
  - tekst **generowany** przez system z wybranych opcji oraz **edytowalny** przez lekarza (`edited_text` / `generated_text`) — zasada „baza, nie klatka”: lekarz może i powinien móc dopisać własny styl przed publikacją,
  - podsumowanie zbiorcze (również edytowalne).

![Fragment panelu Befund](/docs/manual/assets/screenshots/doctor-04-befund-section.png)

### 3.2 Szablony tekstu

Lekarz może korzystać z **własnych szablonów** (języki DE/EN/PL według konfiguracji). Szablony **globalne** lub **kliniczne** mogą być ograniczone do administratora — jeśli nie widzisz opcji tworzenia szablonu klinicznego, poproś admina.

Szczegóły uprawnień: [`.ai/instrukcja_szablony.md`](../../.ai/instrukcja_szablony.md).

### 3.3 Język publikacji PDF (`publish_locale` / `form_locale`)

Przy publikacji wybierasz język wersji dokumentu używany do generacji PDF — jest on **trwale** związany z wersją. Upewnij się, że odpowiada językowi ustalonemu z pacjentem, jeśli ma to znaczenie praktyczne.

---

## 4. Szkic vs publikacja

| Akcja | Skutek |
|--------|--------|
| **Zapisz jako szkic** | Możesz wrócić i edytować; **nie** uruchamia pełnego łańcucha wysyłki jak przy publikacji. |
| **Zatwierdź i wyślij (publikacja)** | Dokument przechodzi w tryb opublikowany; w tle kolejkowane są zadania: generowanie PDF, upload, SMS (logistyczny). |

UI **nie blokuje** przeglądarki na czas generowania — statusy PDF / HiDrive / SMS odświeżają się w liście lub w widoku szczegółów (zależnie od wersji frontu).

**Idempotentność:** wielokrotne kliknięcie „publikuj” dla tego samego stanu dokumentu nie powinno duplikować niepotrzebnie łańcucha zadań — serwer może zwrócić sukces bez tworzenia kolejnej publikacji w toku.

---

## 5. Błędy przetwarzania

Gdy któryś z etapów (PDF, HiDrive, SMS) się nie powiedzie, w liście mogą pojawić się statusy **FAILED** / **PENDING** oraz opcjonalnie **komunikat błędu** w wierszu (`processing_error_message`). W takiej sytuacji:

1. Sprawdź ponownie po kilku minutach (retry w tle).  
2. Jeśli błąd się utrzymuje — zgłoś **administratorowi** (outbox, logi).  
3. Nie publikuj wielokrotnie „w panice” — potwierdź najpierw stan w panelu lub u admina.

---

## 6. Edycja po publikacji

Po opublikowaniu możesz **wprowadzić korekty** i ponownie opublikować — powstaje **nowa wersja** PDF; ścieżka w archiwum może być nadpisywana zgodnie z konfiguracją. Przy ponownej publikacji może być dostępna opcja **ponownego wysłania SMS** do pacjenta — stosuj zgodnie z procedurą placówki.

---

## 7. Wylogowanie

**`/doctor/logout/`** (POST) — wylogowuje z sesji Django; następne wejście na `/doctor/` wymaga logowania.

---

## 8. Dobre praktyki

- Sprawdzaj **status SMS** tylko jako informację techniczną — treść SMS w systemie jest **logistyczna** (bez opisu badania/wyniku), zgodnie z RODO/BÄK.
- Przed publikacją **przeczytaj** wygenerowany tekst i dostosuj go do siebie; nie polegaj wyłącznie na szablonie automatycznym.
- Przy wielu grupach zmian pilnuj spójności **numerów zmian** z wideodermatoskopu.

Powiązane: [Przegląd](00-przeglad.md), [Administrator](04-administrator.md), [Pacjent — portal wyników](05-pacjent-wyniki.md).
