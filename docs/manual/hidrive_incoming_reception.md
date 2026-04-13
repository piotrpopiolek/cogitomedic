# HiDrive: PDF z laboratorium w `/incoming/` (recepcja)

## Gdzie wrzucać pliki

- Katalog na HiDrive: **`/incoming/`** (domyślnie) — bez podfolderów, bezpośrednio pliki PDF, obok **`/patients/`** i **`/processed/`** w tej samej „gałęzi” logicznej. Domyślnie aplikacja mapuje ścieżki logiczne na **`/users/<alias z OAuth>/…`** (alias z `GET /user/me`). Jeśli **przestrzeń wspólna (Common)** w API HiDrive ma **inny korzeń** niż Twój alias (np. `/users/nazwa_zespolu/…`), ustaw **`HIDRIVE_USERS_ROOT_PREFIX`** na ten absolutny prefix (bez końcowego `/`), a ścieżki logiczne trzymaj krótko, np. `HIDRIVE_INCOMING_PATH=/incoming`, `HIDRIVE_PROCESSED_PATH=/processed`, `HIDRIVE_PATIENTS_DIR_PREFIX=/patients`. W przeciwnym razie, gdy pliki mają być pod Twoim kontem w podfolderze `public`, użyj np. `HIDRIVE_INCOMING_PATH=/public/incoming` itd. **bez** `HIDRIVE_USERS_ROOT_PREFIX`.
- PDF Befundu / intake trafiają do **`{HIDRIVE_PATIENTS_DIR_PREFIX}/{id_pacjenta}/`** (np. domyślnie `/patients/{uuid}/Befund_v1.pdf`).
- Po poprawnej publikacji Befundu system przenosi użyte pliki z dopasowania do katalogu **`HIDRIVE_PROCESSED_PATH`** (archiwum kliniki; portal pacjenta nie ma tam dostępu).

## Nazwy plików (separator `_`, bez polskich znaków w nazwie pliku)

Dozwolone wzorce (wielkość liter bez znaczenia, rozszerzenie `.pdf`):

1. `Imie_Nazwisko.pdf` — np. `Jan_Kowalski.pdf`
2. `Nazwisko_Imie.pdf` — np. `Kowalski_Jan.pdf`
3. `Imie_Nazwisko_RRRR_MM_DD.pdf` — data urodzenia z podkreśleniami, np. `Jan_Kowalski_1985_03_12.pdf`
4. `Nazwisko_Imie_RRRR_MM_DD.pdf` — np. `Kowalski_Jan_1985_03_12.pdf`

Wiele plików dla tej samej osoby i tej samej „bazowej” nazwie: dopisać `_2`, `_3` itd. przed `.pdf`, np. `Kowalski_Jan_1985_03_12_2.pdf`.

## Kolizje imion i nazwisk

Jeśli w bazie jest więcej niż jeden pacjent pasujący do **krótkiej** nazwy pliku (bez daty urodzenia w nazwie), system **nie dopasuje** pliku i poprosi o dopisanie daty urodzenia do nazwy pliku (format `RRRR_MM_DD` z podkreśleniami).

## Pliki odrzucone przez lekarza

- Po odrzuceniu pliku w panelu lekarza nazwa na HiDrive dostaje prefix **`rejected_`** (np. `rejected_Kowalski_Jan.pdf`).
- Takie pliki są ignorowane przy dopasowaniu — recepcja widzi, że nazwa lub treść wymaga korekty.

## Uwagi

- Scalony PDF wysłany do pacjenta to **nowy dokument**; podpisy cyfrowe z PDF laboratorium nie są zachowywane.
- Folder **`/processed/`** zawiera pliki już powiązane z opublikowanym Befundem — nie usuwać ich ręcznie bez uzgodnienia z IT.
