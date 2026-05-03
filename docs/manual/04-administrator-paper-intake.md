# Autoryzacja ścieżki papierowej — procedura dla Admin / Manager

Dokument dla personelu z grupą **Admin** lub **Manager**, które **autoryzuje** (T1) lub **cofa autoryzację** (T1′) ścieżkę „dokument medyczny bez cyfrowej ankiety”. **Recepcja** i **Tablet** **nie** wykonują T1 ani T2.

Powiązane: [diagram przepływu](paper_intake_flow.md), [skrót w instrukcji administratora](04-administrator.md), [instrukcja lekarza — sekcja papierowa](03-doktor.md).

---

## 1. Cel i zasady

- **T1 (autoryzacja):** formalna zgoda systemowa na to, że dany wpis kolejki może zostać obsłużony **bez** wypełnionej cyfrowej ankiety — bo ankieta / zgody są **prowadzone papierowo** według procedury placówki.
- **T2 (utworzenie dokumentu):** wykonuje lekarz lub nadzorca z rolą kliniczną z **`/doctor/`** — poza zakresem tej strony, ale **nie nastąpi**, dopóki T1 nie zostanie zapisany poprawnie.
- **Invariant:** status kolejki **PAPER_INTAKE_COMPLETED** występuje **wyłącznie** razem z istniejącym dokumentem `source_type = PAPER_INTAKE` (brak cyfrowego `intake_form`).

---

## 2. Gdzie w systemie

| Zasób | Adres / ścieżka |
|-------|-----------------|
| **Hub HTML** | **`/admin/paper-intake/`** — lista wpisów kwalifikujących się z ostatnich dni (nagłówek menu Unfold zależy od wdrożenia). |
| **Strona pojedynczego wpisu** | Z huba — szczegóły wpisu kolejki z formularzem autoryzacji / cofnięcia. |
| **API** (integracje) | `POST` / `DELETE` **`/api/v1/queue-entries/<uuid>/paper-intake-authorization`** — tożsame reguły co HTML; dla Admin/Manager **bez** dodatkowej bramki „zakres placówki” jak przy innych endpointach wpisu (patrz ogólna instrukcja [04-administrator.md](04-administrator.md) §3a). |

---

## 3. Warunki, które muszą być spełnione przed T1

System **odrzuci** autoryzację, jeśli np.:

1. **`entry_status`** wpisu nie jest **WAITING** (inny etap wizyty).
2. Brak ustawionej **`appointment_time`** — ścieżka papierowa wymaga zaplanowanej godziny wizyty.
3. Nie upłynęło jeszcze **minimum pełnych godzin** po `appointment_time` — wartość produkcyjna: stała **`PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT`** w kodzie (domyślnie **3** godziny). Ta sama logika jest ponownie sprawdzana przy **T2** (defense in depth).
4. Istnieje już **ukończona cyfrowa ankieta** w statusie wysłanym (`SUBMITTED` itd.) — wtedy obowiązuje ścieżka z tableta, nie papier.
5. Istnieje już **dokument medyczny** dla tego wpisu kolejki.
6. Istnieje już **aktywna autoryzacja** — najpierw użyj **T1′**, jeśli trzeba ją zastąpić (po konsultacji merytorycznej), zamiast dublować T1.

Komunikaty błędów w UI / API są **słownikowe** (klucze domenowe) — przy problemie zapisz czas, użytkownika i treść zwróconą przez system dla audytu wewnętrznego.

---

## 4. T1 — autoryzacja (krok po kroku)

1. Zaloguj się do **`/admin/`** jako **Admin** lub **Manager**.
2. Wejdź w **`/admin/paper-intake/`** i znajdź wpis (pacjent, data kolejki, placówka).
3. Otwórz **stronę wpisu** z huba.
4. Wypełnij pole **powód autoryzacji** (**reason**) — wymagana długość **10–500 znaków** (krótki opis sytuacji merytorycznej, np. awaria tableta, pacjent wyłącznie z papierową zgodą zgodnie z procedurą).
5. Zatwierdź **Autoryzuj** (etykieta zależy od tłumaczenia).
6. **Efekt:** wpis pozostaje w **WAITING**, ale pojawia się na **liście lekarza** w **stanie B** z przyciskiem utworzenia dokumentu papierowego — lekarz widzi interfejs w [03-doktor.md](03-doktor.md).

**Audyt:** zapis zdarzenia autoryzacji z identyfikatorem osoby zatwierdzającej i znacznikiem czasu.

---

## 5. T1′ — cofnięcie autoryzacji

Dostępne **tylko dopóki nie utworzono dokumentu medycznego** (brak T2).

1. Na tej samej stronie wpisu wybierz akcję cofnięcia (np. „Cofnij autoryzację” — wg tłumaczenia).
2. Podaj **osobny powód** cofnięcia (ten sam limit długości co przy T1, o ile UI/API tak wymaga).
3. Po zapisie wpis **znika** ze „stanu B” na liście lekarza; można ponownie przejść ścieżkę cyfrową lub, po spełnieniu warunków, ponownie wykonać T1.

**Audyt:** osobne zdarzenie cofnięcia.

---

## 6. Auto-revoke — kiedy autoryzacja znika bez ręcznego T1′

| Zdarzenie | Skutek |
|-----------|--------|
| Pacjent **wysłał** formularz cyfrowy z tableta | Autoryzacja papierowa jest **unieważniana** w tej samej transakcji co zapis ankiety — dalsza praca lekarza idzie w modelu **cyfrowym**. |
| Wpis kolejki ustawiony na **CANCELLED** | Autoryzacja jest **unieważniana** razem z anulowaniem wizyty. |

Personel powinien **nie planować** równoległej pracy „papier + tablet” na ten sam wpis — system rozstrzyga na korzyść **danych cyfrowych**, gdy się pojawią.

---

## 7. Obowiązki poza systemem (procedura placówki)

- **Fizyczna dokumentacja** (papierowa zgoda / anamneza) musi być **przechowywana i weryfikowana** zgodnie z polityką placówki — CogitoMedica przechowuje **metadane decyzji** i powiązanie z wpisem, a nie skan treści papieru.
- Ustal **kto** (rola) może prosić o T1 oraz kto zatwierdza merytorycznie przed wejściem do huba — to jest kontrola organizacyjna, nie tylko techniczna.

---

## 8. Miejsca na zrzuty ekranu (opcjonalnie)

Przy aktualizacji [screenshot-checklist.md](screenshot-checklist.md) można dodać:

- hub `/admin/paper-intake/` — lista,
- strona wpisu — formularz T1 z wypełnionym `reason`,
- ten sam ekran — widoczna akcja T1′.

Na razie dokument jest **tekstowy**; obrazki wstawia się tak jak w pozostałych rozdziałach manuala (ścieżki od root repozytorium, patrz [README](README.md)).
