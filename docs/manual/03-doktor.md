# Instrukcja: Lekarz, Manager i Administrator w panelu medycznym

Panel pod **`/doctor/`** służy do przeglądania **kolejki dokumentów medycznych**, uzupełniania **Befund** (opis badania), zapisywania **szkicu**, **publikacji** oraz — w razie potrzeby — **ponownej publikacji** z nową wersją PDF.

Dostęp: konta **Lekarz**, **Administrator** lub **Manager** (**Manager** — nadzór operacyjny, patrz [Przegląd](00-przeglad.md)).

## Wymagania wstępne

- Konto z rolą **Lekarz**, **Administrator** lub **Manager** (dla Managera: zakres zgodny z polityką placówki).
- Lekarz ma przypisane właściwe placówki, jeśli wymaga tego organizacja pracy.
- Używaj aktualnej przeglądarki internetowej.

---

## 1. Logowanie

1. Otwórz **`/doctor/login/`**.
2. Wprowadź **nazwę użytkownika** i **hasło**.
3. W razie potrzeby ustaw język panelu na stronie logowania.
4. Po zalogowaniu następuje przekierowanie na **`/doctor/`** (lista dokumentów).

![Logowanie lekarza](/docs/manual/assets/screenshots/doctor-01-login.png)

**Komunikat błędu** przy złych danych jest ogólny (np. brak uprawnień lub złe hasło — dokładna treść zależy od szablonu).

---

## 2. Lista dokumentów — `/doctor/`

Na liście pojawiają się wpisy z ukończoną ankietą cyfrową oraz wpisy obsługiwane ścieżką papierową.  
Szkice i wpisy oczekujące na pierwsze utworzenie dokumentu są widoczne dla osób z dostępem do panelu lekarza.

Tabela pokazuje m.in.:

- **Pacjent** (nazwisko, imię),
- **Data** kolejki,
- **Status dokumentu** — np. szkic lub opublikowany,
- **PDF** — status przygotowania pliku PDF,
- **HiDrive** — status zapisu do archiwum,
- **SMS** — status wysyłki powiadomienia logistycznego,
- Kolumna akcji: **Otwórz**.

**Blokada edycji:** jeśli dokument jest aktualnie edytowany przez inną osobę, zobaczysz oznaczenie blokady i nie otworzysz edycji do czasu jej zwolnienia.  
Zielone podświetlenie oznacza dokument opublikowany i zakończone przetwarzanie.

### Filtry (formularz nad tabelą)

- **Status** — szkic / opublikowany / wszystkie (zależnie od opcji).
- **Data kolejki**.
- **Wyszukiwanie pacjenta** (pole tekstowe).
- **Zakres** i **Opublikowano przez** — tylko dla **Administratora** i **Managera** (nadzór); lekarz widzi uproszczony zestaw filtrów.

### Sortowanie listy

- Kliknij nagłówek **Pacjent** lub **Data**, aby zmienić sortowanie w obrębie listy.
- **Zawsze na górze** pozostają wpisy wymagające pracy: bez dokumentu, szkic (`DRAFT`) lub opublikowany dokument z otwartą rewizją; dopiero poniżej — opublikowane wyniki bez rewizji (widoczne dla lekarza, który je opublikował).
- Zmiana filtra **nie resetuje** wybranego sortowania (kierunek jest zachowany w ukrytych polach formularza); zmiana strony paginacji też zachowuje sortowanie.

![Lista dokumentów z filtrami](/docs/manual/assets/screenshots/doctor-02-list-filters.png)

### Otwieranie dokumentu

- Jeśli dokument już istnieje, kliknięcie otwiera jego szczegóły.
- Jeśli dokument jeszcze nie istnieje i ankieta cyfrowa jest gotowa, system utworzy dokument na podstawie tej ankiety.
- Jeśli wpis ma autoryzowaną ścieżkę papierową, na liście zobaczysz osobną akcję utworzenia dokumentu papierowego.

System zapisuje historię działań użytkowników przy dokumentach.

![Komunikat błędu — brak ukończonej ankiety](/docs/manual/assets/screenshots/doctor-03-error-no-intake.png)

### Ścieżka papierowa — dokument bez cyfrowej ankiety

Gdy z przyczyn operacyjnych pacjent **nie** wypełnia ankiety na tablecie, a praca lekarza ma być mimo to możliwa **na podstawie dokumentacji papierowej** poza systemem:

1. **Najpierw** personel **Admin** lub **Manager** wykonuje **T1** (autoryzacja) w hubie **`/admin/paper-intake/`** — opis krok po kroku: [04-administrator-paper-intake.md](04-administrator-paper-intake.md). Bez tego kroku **nie** pojawi się na liście `/doctor/` możliwość utworzenia dokumentu papierowego.
2. **Na liście** `/doctor/` w wierszu takiego wpisu pojawia się akcja utworzenia dokumentu (zwykle **wyróżniona kolorem**). Kliknięcie uruchamia okno potwierdzenia: po utworzeniu dokumentu nie można już cofnąć autoryzacji papierowej w tym procesie.
3. Po zatwierdzeniu powstaje dokument papierowy, a wpis kolejki przechodzi do odpowiedniego statusu. Od tego momentu pracujesz w tym samym panelu co przy dokumentach z ankiety cyfrowej.
4. W nagłówku dokumentu system pokazuje **kto i kiedy autoryzował ścieżkę papierową** oraz **powód autoryzacji**. **Mapy ciała** i podsumowanie pól z tableta nie są dostępne, bo nie było cyfrowej ankiety.
5. **Procedura poza CogitoMedica:** fizyczne przechowywanie i weryfikacja papierowej zgody / anamnezy są po stronie **regulaminu placówki** — system zapisuje decyzję i metadane, nie zastępuje archiwum papierowego. Skrót procesu: [paper_intake_flow.md](paper_intake_flow.md).

**Uwaga:** jeśli zobaczysz komunikat „brak cyfrowej ankiety”, najpierw upewnij się, że autoryzacja ścieżki papierowej została wykonana przez uprawnioną osobę.

---

## 3. Szczegóły dokumentu i formularz Befund

Przy wejściu do szkicu system zakłada blokadę edycji. Jeśli dokument edytuje inna osoba, zobaczysz komunikat i nie wejdziesz do edycji.

### 3.1 Co zawiera ekran

- Podsumowanie danych z ankiety cyfrowej (jeśli taka ankieta była wypełniona).  
  Przy ścieżce papierowej zobaczysz informacje o autoryzacji i informację o braku ankiety cyfrowej.
- Część medyczna **Befund** — m.in.:
  - zakres badania, typ skóry Fitzpatrick, ocena globalna,
  - **grupy zmian**: numery zmian z wideodermatoskopu, cechy dermatoskopowe, ocena kliniczna, ryzyko złośliwości,
  - tekst przygotowany przez system i edytowalny przez lekarza,
  - podsumowanie zbiorcze (również edytowalne).

![Fragment panelu Befund](/docs/manual/assets/screenshots/doctor-04-befund-section.png)

### 3.2 Szablony tekstu

Lekarz może korzystać z **własnych szablonów** (języki DE/EN/PL według konfiguracji). Szablony **globalne** lub **kliniczne** mogą być ograniczone do administratora — jeśli nie widzisz opcji tworzenia szablonu klinicznego, poproś admina.

Szczegóły uprawnień: [`.ai/instrukcja_szablony.md`](../../.ai/instrukcja_szablony.md).

### 3.3 Język publikacji PDF

Przy publikacji wybierasz język wersji dokumentu używany do generacji PDF — jest on **trwale** związany z wersją. Upewnij się, że odpowiada językowi ustalonemu z pacjentem, jeśli ma to znaczenie praktyczne.

---

## 4. Szkic vs publikacja

| Akcja | Skutek |
|--------|--------|
| **Zapisz jako szkic** | Możesz wrócić i edytować; **nie** uruchamia pełnego łańcucha wysyłki jak przy publikacji. |
| **Zatwierdź i wyślij (publikacja)** | Dokument przechodzi w tryb opublikowany; system w tle przygotowuje PDF, zapisuje go i wysyła SMS. |

UI **nie blokuje** przeglądarki na czas generowania — statusy PDF / HiDrive / SMS odświeżają się w liście lub w widoku szczegółów (zależnie od wersji frontu).

Jeśli klikniesz publikację kilka razy, system zwykle nie tworzy kilku takich samych publikacji.

---

## 5. Błędy przetwarzania

Gdy któryś z etapów (PDF, HiDrive, SMS) się nie powiedzie, w liście pojawi się odpowiedni status i czasem komunikat błędu. W takiej sytuacji:

1. Sprawdź ponownie po kilku minutach.  
2. Jeśli błąd się utrzymuje — zgłoś **administratorowi**.  
3. Nie publikuj wielokrotnie „w panice” — potwierdź najpierw stan w panelu lub u admina.

---

## 6. Edycja po publikacji

Po opublikowaniu możesz **wprowadzić korekty** i ponownie opublikować — powstaje **nowa wersja** PDF; ścieżka w archiwum może być nadpisywana zgodnie z konfiguracją. Przy ponownej publikacji może być dostępna opcja **ponownego wysłania SMS** do pacjenta — stosuj zgodnie z procedurą placówki.

---

## 7. Wylogowanie

Użyj opcji wylogowania w panelu lekarza. Kolejne wejście do panelu będzie wymagało ponownego logowania.

---

## 8. Dobre praktyki

- Sprawdzaj **status SMS** tylko jako informację techniczną — treść SMS w systemie jest **logistyczna** (bez opisu badania/wyniku), zgodnie z RODO/BÄK.
- Przed publikacją **przeczytaj** wygenerowany tekst i dostosuj go do siebie; nie polegaj wyłącznie na szablonie automatycznym.
- Przy wielu grupach zmian pilnuj spójności **numerów zmian** z wideodermatoskopu.

Powiązane: [Przegląd](00-przeglad.md), [Administrator](04-administrator.md), [Autoryzacja ścieżki papierowej — szczegóły](04-administrator-paper-intake.md), [Diagram przepływu papierowego](paper_intake_flow.md), [Pacjent — portal wyników](05-pacjent-wyniki.md).

## Typowe problemy (scenariusze)

| Objaw | Scenariusz |
|-------|------------|
| Anulowany wpis nadal na liście / status „—” | [SC-001](scenariusze.md#sc-001), [SC-002](scenariusze.md#sc-002) |
| Porzucenie otwartej rewizji | [SC-003](scenariusze.md#sc-003) |
| Brak PDF labu / HTTP 424 | [SC-005](scenariusze.md#sc-005) |
| Blokada edycji przez kolegę | [SC-014](scenariusze.md#sc-014) |
| Cofnięcie publikacji | [SC-015](scenariusze.md#sc-015) |
| Brak ukończonej ankiety / brak autoryzacji papierowej | [SC-021](scenariusze.md#sc-021), [SC-017](scenariusze.md#sc-017) |
| Pełna lista | [scenariusze.md](scenariusze.md) |
