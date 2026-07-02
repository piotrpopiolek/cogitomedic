# Raport księgowości (admin)

Moduł **Raport tygodniowy** w panelu administracyjnym (`/admin/accounting/report/`).

## Kto ma dostęp

- rola **Accounting** (`ACCOUNTING`)
- **Administrator** i **Manager** (nadzór)

Recepcja, lekarz i tablet — brak dostępu.

## Zakres raportu

- **Pierwsza publikacja** Befundu (`version_no = 1`) z datą `published_at` w wybranym zakresie (domyślnie bieżący tydzień poniedziałek–niedziela).
- **Rewizje** (kolejne wersje opublikowane po poprawce) **nie** tworzą nowej pozycji rozliczeniowej.
- Publikacje z modułu „Zewnętrzne badanie” (EXTERNAL_UPLOAD) — poza tym raportem w MVP.

## Kolumny eksportu (CSV / XLSX)

| Kolumna | Źródło |
| --- | --- |
| Nr | lp. w raporcie |
| Vorname / Nachname | pacjent |
| Adresse | ulica, kod, miasto |
| Email | pacjent |
| Befund-Arzt | lekarz pierwszej publikacji |
| Untersuchungsdatum | data kolejki (`queue_date`) |

Kolumny płatności (Rechnungsbetrag, Überweisung, Kartenzahlung) — planowane w kolejnej fazie.

## Eksport i audyt

Przyciski **Eksport CSV** / **Eksport XLSX** pobierają pełny zestaw wierszy z wybranego zakresu dat. Każdy eksport zapisuje zdarzenie audytu `ACCOUNTING_REPORT_EXPORT` (zakres dat, format, liczba wierszy — bez danych pacjentów w metadanych).
