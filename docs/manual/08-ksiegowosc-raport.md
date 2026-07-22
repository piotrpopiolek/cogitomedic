# Raport księgowości (admin)

Moduł **Raport tygodniowy** w panelu administracyjnym (`/admin/accounting/report/`).

**Instrukcja krok po kroku (scenariusz operacyjny):** [scenariusze.md § SC-004](scenariusze.md#sc-004-pobranie-listy-tygodniowej-dla-księgowości).

Wejście z menu Unfold: sekcja **Księgowość** → **Raport tygodniowy**.

## Kto ma dostęp

- rola **Accounting** (`ACCOUNTING`) — wyłącznie ten moduł (brak list pacjentów i innych ekranów ModelAdmin)
- **Administrator** i **Manager** (nadzór)

Recepcja, lekarz i tablet — **403 Forbidden**.

## Zakres placówek

- **Accounting** i **Admin** — wszystkie placówki (`get_scoped_clinic_site_ids` → brak filtra).
- **Manager** — tylko placówki przypisane do konta (jak w innych widokach z zakresem).

## Zakres raportu

Przełącznik **Wariant raportu** w formularzu:

### Opublikowane Befundy (`report_mode=published`, domyślnie)

- **Pierwsza publikacja** Befundu (`version_no = 1`, status `PUBLISHED`), której **data badania** (`DailyQueue.queue_date`) mieści się w wybranym zakresie kalendarzowym (domyślnie bieżący tydzień **poniedziałek–niedziela** w strefie `TIME_ZONE`, np. `Europe/Warsaw`). **Nie** filtrujemy po dniu publikacji (`published_at`) — lekarz może opisać wynik później; wiersz i tak trafia do tygodnia wizyty.
- **Rewizje** (kolejne wersje opublikowane po poprawce) **nie** tworzą nowej pozycji rozliczeniowej.
- Publikacje z modułu „Zewnętrzne badanie” (`EXTERNAL_UPLOAD`) — poza tym wariantem w MVP.
- Wiersze unieważnionych wersji (`revoked_at` ustawione) — wykluczone.
- Kolumna **Befund-Arzt** = lekarz pierwszej publikacji (`published_by_user`).

### Stawili się (`report_mode=attended`)

- Pacjenci z wpisem w kolejce w zakresie dat, którzy **wypełnili ankietę** (`PatientIntakeForm.form_status` w `{SUBMITTED, REOPENED}`).
- **Bez** wpisów anulowanych (`entry_status=CANCELLED`) i **bez** no-show z importu (brak złożonej ankiety).
- **Nie** wymaga opublikowanego Befundu — pacjent może być w raporcie zaraz po złożeniu formularza.
- Kolumna **Befund-Arzt**: lekarz pierwszej nieunieważnionej publikacji, jeśli istnieje; **bez** publikacji kolumna jest pusta (nie używamy `assigned_doctor` z kolejki).

### Ausfallhonorar (`report_mode=ausfall`)

- Pacjenci z wpisem w kolejce w zakresie dat, którzy **nie zrealizowali wizyty**: brak złożonej ankiety (no-show, odmowa, niepełne zgody / ankieta w toku).
- Technicznie: kolejka w zakresie **minus** wariant „Stawili się”; **bez** `CANCELLED`.
- Jedna kategoria do windykacji — bez podziału na przyczyny.
- Kolumna **Ausfallhonorar** w podglądzie i eksporcie = stała wartość `Ja`. Kolumna **Befund-Arzt** pusta. Sekcja agregatu per lekarz — ukryta.

## Podgląd w panelu

- Formularz **Data od** / **Data do** — opcjonalnie; bez parametrów stosowany jest bieżący tydzień.
- Po zmianie daty w polu **Von** / **Bis** raport **odświeża się automatycznie** (bez konieczności klikania „Pokaż raport”); przycisk pozostaje jako fallback. Zmiana daty resetuje podgląd do **strony 1**; wybrany rozmiar strony (`page_size`) jest zachowany.
- Linki **Eksport CSV** / **Eksport XLSX** zawsze wskazują bieżąco wybrane daty (aktualizowane przy zmianie pól dat).
- Tabela wierszy z paginacją (`page`, `page_size`; domyślnie **50**, dozwolone **10 / 20 / 50 / 100**). W **ciemnym motywie** Unfold tekst tabeli, hint i stopka paginacji używają klas `dark:` (kontrast `base-100` / `base-300` na `base-900`).
- Sekcja **Liczba publikacji per lekarz** — agregat z tego samego zestawu wierszy (ukryta w wariancie Ausfallhonorar).
- Brakujące dane pacjenta (np. adres, email) — pusty tekst w eksporcie i podglądzie.

## Kolumny eksportu (CSV / XLSX)

Nagłówki w eksporcie są w języku niemieckim (kanoniczne nazwy kolumn); w UI admina mogą być przetłumaczone wg `preferred_locale`.

| Kolumna | Źródło |
| --- | --- |
| Nr | lp. w raporcie |
| Vorname / Nachname | pacjent |
| Straße | ulica (`patient.street`) |
| PLZ/Ort | kod pocztowy + miejscowość (`postal_code` + `city`, format np. `10115 Berlin`) |
| Email | pacjent |
| Befund-Arzt | lekarz pierwszej publikacji (`published_by_user`); pusta w Ausfallhonorar |
| Untersuchungsdatum | data kolejki (`queue_date`), format `DD.MM.RRRR` |
| Ausfallhonorar | tylko w wariancie `ausfall`: stała wartość `Ja` |

Kolumny płatności (Rechnungsbetrag, Überweisung, Kartenzahlung) — planowane w kolejnej fazie (`ACCOUNTING_PAYMENT_COLUMNS_ENABLED = False`).

## Eksport i audyt

Przyciski **Eksport CSV** / **Eksport XLSX** pobierają **pełny** zestaw wierszy z wybranego zakresu dat i **wariantu** (bez paginacji). Nazwa pliku: `accounting_report_{published|attended|ausfall}_{date_from}_{date_to}.csv` lub `.xlsx`.

Adresy eksportu:

- `/admin/accounting/report/export.csv`
- `/admin/accounting/report/export.xlsx`

Każdy eksport zapisuje zdarzenie audytu `ACCOUNTING_REPORT_EXPORT` (zakres dat, format, `report_mode`, liczba wierszy — **bez** danych pacjentów w metadanych).

## API REST (przygotowanie)

W kodzie są schematy Pydantic (`AccountingReportQueryParams`, `AccountingReportResponse` w `apps/operations/api_schemas.py`) pod przyszły endpoint `GET /api/v1/accounting/report`. Obecnie raport jest dostępny wyłącznie przez widoki HTML admina i eksport plików powyżej.
