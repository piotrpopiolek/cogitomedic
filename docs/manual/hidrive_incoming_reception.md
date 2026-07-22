# HiDrive: PDF z laboratorium w `/incoming/` (recepcja)

## Oddzielnie: wgranie zewnętrznego badania przez aplikację

Recepcja może wgrywać PDF przez **aplikację** — wtedy plik trafia pod  
**`/incoming/external-upload/{queue_entry_id}/...`** (nie mieszać z ręcznym wrzutem labu do katalogu głównego `/incoming/`).  
Przy **bramce dopasowania plików labu do pacjenta** (panel lekarza) ścieżki z prefiksem `external-upload/` są **ignorowane**, żeby wynik z recepcji nie wszedł do listy „PDF z laboratorium” dla Befundu. Szczegóły procesu: [07-wgranie-zewnetrznego-badania.md](07-wgranie-zewnetrznego-badania.md).

## Gdzie wrzucać pliki

- Katalog na HiDrive: **`/incoming/`** (domyślnie) — bez podfolderów, bezpośrednio pliki PDF.
- Dokumenty pacjenta trafiają do folderu pacjenta (np. `/patients/...`).
- Po poprawnej publikacji system przenosi użyte pliki do folderu archiwum (np. `/processed/`), niedostępnego dla pacjenta.
- Jeśli nie masz pewności, jaka ścieżka jest poprawna w Waszej placówce, skontaktuj się z działem IT.

## Nazwy plików (separator `_`, bez polskich znaków w nazwie pliku)

Dozwolone wzorce (wielkość liter bez znaczenia, rozszerzenie `.pdf`):

1. `Imie_Nazwisko.pdf` — np. `Jan_Kowalski.pdf`
2. `Nazwisko_Imie.pdf` — np. `Kowalski_Jan.pdf`
3. `Imie_Nazwisko_RRRR_MM_DD.pdf` — data urodzenia z podkreśleniami, np. `Jan_Kowalski_1985_03_12.pdf`
4. `Nazwisko_Imie_RRRR_MM_DD.pdf` — np. `Kowalski_Jan_1985_03_12.pdf`

Jeśli masz wiele plików tej samej osoby o tej samej nazwie bazowej, dopisz `_2`, `_3` itd. przed `.pdf`, np. `Kowalski_Jan_1985_03_12_2.pdf`.

Spacje i myślniki w imieniu lub nazwisku w nazwie pliku zapisuj jako **podkreślenia** (`_`). W pliku używaj **liter łacińskich bez ogonków** (np. `Muller` zamiast `Müller`, `Garcia` zamiast `García`) — system i tak dopasuje warianty z umlautami, ale taka konwencja ogranicza pomyłki.

## Wieloczłonowe imiona i nazwiska

System porównuje nazwę pliku z danymi pacjenta w rejestracji: pole **imię** i pole **nazwisko** (osobno). Nie ma dodatkowych pól na drugie imię ani drugie nazwisko — całość musi być wpisana tak, jak ma się pojawić w nazwie pliku.

### Zasada dla recepcji

| W rejestracji (pole) | W nazwie pliku na HiDrive |
| --- | --- |
| Wszystkie człony **imienia** w polu *Imię* | Te same człony, połączone `_` |
| Wszystkie człony **nazwiska** w polu *Nazwisko* (w tym „von …”, nazwisko dwuczłonowe) | Te same człony, połączone `_` |
| Kolejność | `Imie_…_Nazwisko.pdf` **lub** `Nazwisko_…_Imie.pdf` (oba warianty działają) |

### Przykłady, które **działają**

| Imię w systemie | Nazwisko w systemie | Przykładowa nazwa pliku |
| --- | --- | --- |
| Jean Christophe | Scheider | `Jean_Christophe_Scheider.pdf` lub `Scheider_Jean_Christophe.pdf` |
| Hans Peter | Müller | `Muller_Hans_Peter.pdf` lub `Hans_Peter_Muller.pdf` |
| Anna | Müller-Schmidt | `Muller_Schmidt_Anna.pdf` (myślnik → `_`) |
| Klaus | von Stauffenberg | `von_Stauffenberg_Klaus.pdf` |
| Luis | García Hernández | `Garcia_Hernandez_Luis.pdf` |
| Jean-Pierre | Müller | `Muller_Jean-Pierre.pdf` |

Przy ryzyku, że w bazie są **dwaj pacjenci** o podobnym imieniu i nazwisku, dopisz **datę urodzenia** do nazwy pliku, np. `Muller_Hans_Peter_1985_03_12.pdf`.

### Przykłady, które **nie** zostaną dopasowane (celowo — bezpieczeństwo danych)

System **nie zgaduje** skróconych ani niepełnych nazw — plik musi odpowiadać temu, co jest w rejestracji.

| Problem | Przykład |
| --- | --- |
| W bazie pełne imię, w pliku skrót | Baza: imię „Hans **Peter**”, nazwisko „Müller” — plik: `Muller_Hans.pdf` (**brak** „Peter”) |
| W bazie nazwisko złożone, w pliku jeden człon | Baza: „Müller-**Schmidt**” — plik: `Schmidt_Anna.pdf` (**brak** „Muller”) |
| W bazie człon „von”, w pliku pominięty | Baza: „von Stauffenberg” — plik: `Stauffenberg_Klaus.pdf` (**brak** „von”) |
| Tylko nazwisko lub tylko imię w pliku | `Muller.pdf` przy pacjencie „Hans” / „Müller” |
| Zła data urodzenia w nazwie | `Muller_Hans_1999_01_01.pdf` przy innej dacie w kartotece |

**Co zrobić:** popraw nazwę pliku tak, aby zawierała **wszystkie człony** imienia i nazwiska jak w systemie (albo uzupełnij dane pacjenta w rejestracji, jeśli plik z labu jest wzorcem). Po zmianie imienia lub nazwiska pacjenta w systemie zapisz kartę — klucze dopasowania odświeżają się automatycznie.

## Kolizje imion i nazwisk

Jeśli w bazie jest więcej niż jeden pacjent pasujący do **krótkiej** nazwy pliku (bez daty urodzenia w nazwie), system **nie dopasuje** pliku i poprosi o dopisanie daty urodzenia do nazwy pliku (format `RRRR_MM_DD` z podkreśleniami).

## Pliki odrzucone przez lekarza

- Po odrzuceniu pliku w panelu lekarza nazwa na HiDrive dostaje przedrostek **`rejected_`** (np. `rejected_Kowalski_Jan.pdf`).
- Takie pliki są ignorowane przy dopasowaniu — recepcja widzi, że nazwa lub treść wymaga korekty.
- Po usunięciu prefixu `rejected_` (lub wgraniu nowego PDF pod poprawną nazwą): przy **szkicu** otwórz kartę ponownie; przy **opublikowanym** dokumencie uruchom rewizję i otwórz kartę ponownie — system wtedy ponownie skanuje `/incoming/` i podpina plik jako `MATCHED`.

## Uwagi

- PDF wysłany do pacjenta to **nowy dokument**; podpisy cyfrowe z PDF laboratorium nie są zachowywane.
- Folder **`/processed/`** zawiera pliki już powiązane z opublikowanym dokumentem — nie usuwaj ich ręcznie bez uzgodnienia z działem IT.
