# HiDrive: PDF z laboratorium w `/incoming/` (recepcja)

## Gdzie wrzucać pliki

- Katalog na HiDrive: **`/incoming/`** — bez podfolderów, bezpośrednio pliki PDF (na tym samym poziomie co **`/patients/`** i **`/processed/`**; nie używamy już podfolderu `hidrive`).
- PDF Befundu / intake trafiają do **`/patients/{id_pacjenta}/`** (np. `Befund_v1.pdf` obok folderu pacjenta).
- Po poprawnej publikacji Befundu system przenosi użyte pliki z dopasowania do **`/processed/`** (archiwum kliniki; portal pacjenta nie ma tam dostępu).

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
