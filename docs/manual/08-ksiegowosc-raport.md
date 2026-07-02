# Raport księgowości (admin)

Moduł **Raport tygodniowy** w panelu administracyjnym (`/admin/accounting/report/`).

Wejście z menu Unfold: sekcja **Księgowość** → **Raport tygodniowy**.

## Kto ma dostęp

- rola **Accounting** (`ACCOUNTING`) — wyłącznie ten moduł (brak list pacjentów i innych ekranów ModelAdmin)
- **Administrator** i **Manager** (nadzór)

Recepcja, lekarz i tablet — **403 Forbidden**.

## Zakres placówek

- **Accounting** i **Admin** — wszystkie placówki (`get_scoped_clinic_site_ids` → brak filtra).
- **Manager** — tylko placówki przypisane do konta (jak w innych widokach z zakresem).

## Zakres raportu

- **Pierwsza publikacja** Befundu (`version_no = 1`, status `PUBLISHED`) z datą `published_at` w wybranym zakresie kalendarzowym (domyślnie bieżący tydzień **poniedziałek–niedziela** w strefie `TIME_ZONE`, np. `Europe/Warsaw`).
- **Rewizje** (kolejne wersje opublikowane po poprawce) **nie** tworzą nowej pozycji rozliczeniowej.
- Publikacje z modułu „Zewnętrzne badanie” (`EXTERNAL_UPLOAD`) — poza tym raportem w MVP.
- Wiersze unieważnionych wersji (`revoked_at` ustawione) — wykluczone.

## Podgląd w panelu

- Formularz **Data od** / **Data do** — opcjonalnie; bez parametrów stosowany jest bieżący tydzień.
- Tabela wierszy z paginacją (`page`, `page_size`; domyślnie **20**, maks. **100** wierszy na stronę).
- Sekcja **Liczba publikacji per lekarz** — agregat z tego samego zestawu wierszy.
- Brakujące dane pacjenta (np. adres, email) — pusty tekst w eksporcie i podglądzie.

## Kolumny eksportu (CSV / XLSX)

Nagłówki w eksporcie są w języku niemieckim (kanoniczne nazwy kolumn); w UI admina mogą być przetłumaczone wg `preferred_locale`.

| Kolumna | Źródło |
| --- | --- |
| Nr | lp. w raporcie |
| Vorname / Nachname | pacjent |
| Adresse | ulica, kod, miasto |
| Email | pacjent |
| Befund-Arzt | lekarz pierwszej publikacji (`published_by_user`) |
| Untersuchungsdatum | data kolejki (`queue_date`), format `DD.MM.RRRR` |

Kolumny płatności (Rechnungsbetrag, Überweisung, Kartenzahlung) — planowane w kolejnej fazie (`ACCOUNTING_PAYMENT_COLUMNS_ENABLED = False`).

## Eksport i audyt

Przyciski **Eksport CSV** / **Eksport XLSX** pobierają **pełny** zestaw wierszy z wybranego zakresu dat (bez paginacji). Nazwa pliku: `accounting_report_{date_from}_{date_to}.csv` lub `.xlsx`.

Adresy eksportu:

- `/admin/accounting/report/export.csv`
- `/admin/accounting/report/export.xlsx`

Każdy eksport zapisuje zdarzenie audytu `ACCOUNTING_REPORT_EXPORT` (zakres dat, format, liczba wierszy — **bez** danych pacjentów w metadanych).

## API REST (przygotowanie)

W kodzie są schematy Pydantic (`AccountingReportQueryParams`, `AccountingReportResponse` w `apps/operations/api_schemas.py`) pod przyszły endpoint `GET /api/v1/accounting/report`. Obecnie raport jest dostępny wyłącznie przez widoki HTML admina i eksport plików powyżej.
