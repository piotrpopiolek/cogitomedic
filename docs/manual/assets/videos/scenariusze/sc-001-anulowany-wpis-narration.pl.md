# Narracja — SC-001 — Anulowany wpis nadal w kolejce lekarza

Plik: `sc-001-cancelled-queue-entry.webm`

---

## Wprowadzenie (0:00–0:20)

Anulowałaś wizytę w recepcji, a lekarz nadal widzi pacjenta na liście? Po wdrożeniu poprawki anulowany wpis **nie powinien** pojawiać się u lekarza. Film pokazuje właściwą kolejność: anulowanie we właściwym wpisie i sprawdzenie listy `/doctor/`.

## Krok 1 — Recepcja: znajdź wpis

Logujemy się jako recepcja. Otwieramy wpisy kolejki na dziś i wchodzimy w szczegóły pacjenta demo (fikcyjne dane).

## Krok 2 — Anuluj właściwy wpis

Ustaw status na **Anulowano** i zapisz. Upewnij się, że to ten wpis, który miał ankietę „Pacjent zakończył”, a nie inny slot tego samego dnia.

## Krok 3 — Lista lekarza

Logujemy się jako lekarz, odświeżamy `/doctor/`. Wyszukaj nazwisko — anulowany wpis **nie powinien** być na liście pracy. Nie używaj starego linku `/doctor/open/{uuid}/` z historii przeglądarki.

## Czego nie robić

Nie traktuj anulowania wpisu jako „zamknięcia przypadku” przy złożonej ankiecie — nie ma osobnej akcji „anuluj ankietę” w UI.
