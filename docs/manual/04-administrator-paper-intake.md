# Autoryzacja ścieżki papierowej — procedura dla Administratora i Managera

Dokument dla personelu z rolą **Administrator** lub **Manager**, który **autoryzuje** (T1) lub **cofa autoryzację** (T1′) ścieżkę „dokument medyczny bez cyfrowej ankiety”. **Recepcja** i **Tablet** nie wykonują tych działań.

Powiązane: [diagram przepływu](paper_intake_flow.md), [skrót w instrukcji administratora](04-administrator.md), [instrukcja lekarza — sekcja papierowa](03-doktor.md).

---

## 1. Cel i zasady

- **T1 (autoryzacja):** formalna zgoda systemowa na to, że dany wpis kolejki może zostać obsłużony **bez** wypełnionej cyfrowej ankiety — bo ankieta / zgody są **prowadzone papierowo** według procedury placówki.
- **T2 (utworzenie dokumentu):** wykonuje lekarz lub nadzorca z rolą kliniczną z **`/doctor/`** — poza zakresem tej strony, ale **nie nastąpi**, dopóki T1 nie zostanie zapisany poprawnie.
- Status „paper intake completed” pojawia się dopiero po utworzeniu dokumentu papierowego.

---

## 2. Gdzie w systemie

| Zasób | Adres / ścieżka |
|-------|-----------------|
| **Panel autoryzacji** | **`/admin/paper-intake/`** — lista wpisów z ostatnich dni. |
| **Strona pojedynczego wpisu** | Z huba — szczegóły wpisu kolejki z formularzem autoryzacji / cofnięcia. |
| **Integracje techniczne** | Szczegóły dla działu IT są opisane w [04-administrator.md](04-administrator.md). |

---

## 3. Warunki, które muszą być spełnione przed T1

System **odrzuci** autoryzację, jeśli np.:

1. Wpis jest na niewłaściwym etapie wizyty.
2. Nie ma ustawionej godziny wizyty.
3. Od godziny wizyty nie minął jeszcze wymagany czas.
4. Cyfrowa ankieta została już wysłana — wtedy obowiązuje ścieżka cyfrowa, a nie papierowa.
5. Istnieje już **dokument medyczny** dla tego wpisu kolejki.
6. Istnieje już aktywna autoryzacja — najpierw ją cofnij, jeśli trzeba ją zastąpić.

Gdy pojawi się błąd, zapisz czas, użytkownika i treść komunikatu.

---

## 4. T1 — autoryzacja (krok po kroku)

1. Zaloguj się do **`/admin/`** jako **Admin** lub **Manager**.
2. Wejdź w **`/admin/paper-intake/`** i znajdź wpis (pacjent, data kolejki, placówka).
3. Otwórz **stronę wpisu** z huba.
4. Wypełnij pole **powód autoryzacji** — krótko opisz sytuację (np. awaria tabletu).
5. Kliknij **Autoryzuj**.
6. **Efekt:** wpis pozostaje w **WAITING**, ale pojawia się na **liście lekarza** w **stanie B** z przyciskiem utworzenia dokumentu papierowego — lekarz widzi interfejs w [03-doktor.md](03-doktor.md).

**Audyt:** zapis zdarzenia autoryzacji z identyfikatorem osoby zatwierdzającej i znacznikiem czasu.

---

## 5. T1′ — cofnięcie autoryzacji

Dostępne **tylko dopóki nie utworzono dokumentu medycznego** (brak T2).

1. Na tej samej stronie wpisu wybierz akcję cofnięcia (np. „Cofnij autoryzację” — wg tłumaczenia).
2. Podaj **powód** cofnięcia.
3. Po zapisie wpis **znika** ze „stanu B” na liście lekarza; można ponownie przejść ścieżkę cyfrową lub, po spełnieniu warunków, ponownie wykonać T1.

**Audyt:** osobne zdarzenie cofnięcia.

---

## 6. Auto-revoke — kiedy autoryzacja znika bez ręcznego T1′

| Zdarzenie | Skutek |
|-----------|--------|
| Pacjent **wysłał** formularz cyfrowy z tableta | Autoryzacja papierowa jest automatycznie unieważniana. Dalsza praca odbywa się ścieżką cyfrową. |
| Wpis kolejki ustawiony na **CANCELLED** | Autoryzacja jest **unieważniana** razem z anulowaniem wizyty. |

Personel powinien **nie planować** równoległej pracy „papier + tablet” na ten sam wpis — system rozstrzyga na korzyść **danych cyfrowych**, gdy się pojawią.

**Scenariusze:** [SC-016](scenariusze.md#sc-016) (autoryzacja znika po ankiecie z tableta), [SC-017](scenariusze.md#sc-017) (brak autoryzacji papierowej na liście lekarza).

---

## 7. Obowiązki poza systemem (procedura placówki)

- **Dokumentacja papierowa** musi być przechowywana i weryfikowana zgodnie z polityką placówki.
- Ustalcie wewnętrznie, kto może prosić o autoryzację i kto ją zatwierdza.

---

## 8. Zrzuty ekranu (demo)

![Hub autoryzacji ścieżki papierowej](/docs/manual/assets/screenshots/paper-intake-01-hub.png)

![Formularz T1 — powód autoryzacji](/docs/manual/assets/screenshots/paper-intake-02-entry-authorize.png)

![Aktywna autoryzacja — formularz cofnięcia T1′](/docs/manual/assets/screenshots/paper-intake-03-entry-revoke.png)

Nazwy plików: [screenshot-checklist.md](screenshot-checklist.md). Generowanie: [assets/screenshots/README.md](assets/screenshots/README.md).
