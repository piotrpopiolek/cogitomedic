# Narracja — film: „Po imporcie widać tylko jednego pacjenta”

Plik wideo: `import-troubleshooting.webm` (nagrywany skryptem `scripts/record_import_troubleshooting_video.py`).

Narracja po polsku — do nagrania lektora lub napisów w edytorze wideo (np. DaVinci Resolve, CapCut).

---

## Wprowadzenie (0:00–0:15)

Wyeksportowałaś z Doctolib dwóch pacjentów na dziś, zaimportowałaś plik — a w systemie widać tylko jedną osobę. Ten film pokazuje, jak to sprawdzić i jak dopisać brakującego pacjenta przed wizytą.

---

## Krok 1 — Lista pacjentów na dziś (0:15–0:45)

Otwieramy widok **Kolejki master/detail** i filtrujemy **dzisiejszą datę**.

Rozwijamy kolejkę na dziś. W tabeli widać **tylko jednego pacjenta** — to ten sam problem, który zgłaszałaś: spodziewałaś się dwóch osób na tablecie.

---

## Krok 2 — Ostatni import (0:45–1:15)

Przechodzimy do **Dashboardu recepcji**. W sekcji **Ostatnie importy** widać plik z Doctolib: status **zakończony**, **Dodano: 1**, **Błędy: 0**.

System nie zgłasza błędu drugiego pacjenta — wygląda na to, że z pliku przetworzono **jeden wiersz**.

---

## Krok 3 — Szczegóły importu (1:15–1:45)

Wchodzimy w **szczegóły importu**. Pole **Total rows** (łącznie wierszy) ma wartość **1**.

To potwierdza: w zaimportowanym pliku system znalazł i przetworzył **jednego pacjenta**. Jeśli w Excelu widzisz dwóch, sprawdź, czy na pewno wysłałaś **właściwy plik** i czy oba wiersze mają wypełnione **imię, nazwisko, telefon, e-mail i datę urodzenia**.

Przykładowy plik z dwoma pacjentami leży w dokumentacji: `docs/manual/assets/fixtures/demo-doctolib-2-patients.xlsx`.

---

## Krok 4 — Czy drugi pacjent jest w systemie? (1:45–2:15)

Szukamy po nazwisku **Schneider** na liście **Patients**.

Pacjent **Thomas Schneider** **jest** w bazie — np. z wcześniejszej wizyty — ale **nie trafił do dzisiejszej kolejki**, bo nie był w przetworzonym imporcie.

Gdyby go tu **nie było**, trzeba by ponownie zaimportować poprawny plik albo dodać pacjenta ręcznie, a potem dopisać do kolejki.

---

## Krok 5 — Ręczne dopisanie do kolejki (2:15–2:55)

Wchodzimy w **Queue entries → Add**.

Wybieramy **dzisiejszą kolejkę**, pacjenta **Thomas Schneider**, status **Waiting**, pozycję **2**. Zapisujemy.

To ten sam efekt, co gdyby support dopisał pacjenta „do kolejki” — bez czekania na IT.

---

## Krok 6 — Weryfikacja (2:55–3:25)

Wracamy do **master/detail** na dziś — w kolejce widać **dwóch pacjentów**.

Na **tablecie** w poczekalni powinni się pojawić oboje — warto sprawdzić to **przed** przyjazdem pacjentów.

---

## Podsumowanie (3:25–3:45)

1. **Master/detail** — ile osób jest na dziś w kolejce.
2. **Dashboard / historia importu** — ile wierszy system faktycznie przetworzył.
3. **Lista pacjentów** — czy brakująca osoba w ogóle jest w systemie.
4. **Queue entries** — ręczne dopisanie do kolejki, jeśli pacjent istnieje, ale nie trafił z importu.

Przy kolejnym imporcie: przed wizytą zawsze sprawdź liczbę osób w master/detail i porównaj z plikiem Excel z Doctolib.
