# Instrukcja: Lekarz, Manager i Administrator w panelu medycznym

Panel pod **`/doctor/`** służy do przeglądania **kolejki dokumentów medycznych**, uzupełniania **Befund** (opis badania), zapisywania **szkicu**, **publikacji** PDF dla pacjenta oraz — w razie potrzeby — **korekty (rewizji)**, **ponownego SMS** i **cofnięcia publikacji**.

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

- **Pacjent** (nazwisko, imię) — przy szkicu dodatkowo kto **aktualnie edytuje** albo kto **ostatnio** zapisał szkic,
- **Data** kolejki,
- **Status dokumentu** — np. szkic lub opublikowany (oraz etykieta **W edycji** przy aktywnym semaforze, **Rewizja**, gdy trwa korekta),
- **PDF** — status przygotowania pliku PDF,
- **HiDrive** — status zapisu do archiwum,
- **SMS** — status wysyłki powiadomienia logistycznego,
- Kolumna akcji: **Otwórz**.

### Kolory wierszy (legenda)

| Kolor | Znaczenie |
| --- | --- |
| **Zielony** | Dokument **opublikowany** i pipeline wychodzący zakończony (PDF / HiDrive / SMS). |
| **Żółty** | Szkic (`ENTWURF`) z **aktywną blokadą edycji** — ktoś właśnie pracuje nad Befundem. W kolumnie Status widać chip **W edycji**; pod nazwiskiem pacjenta: **Edytuje: …** (także gdy to Ty). Przycisk **Otwórz** jest zablokowany tylko gdy edytuje **inna** osoba. |
| **Różowy** | Wpis oczekuje na publikację (okno SLA) — im intensywniejszy odcień, tym bliżej limitu czasu. |

Blokada edycji wygasa po ok. **6 godzinach** bezczynności. Po wygaśnięciu wiersz przestaje być żółty, ale przy szkicu nadal widać **Ostatnio edytował: …** (bez blokady otwarcia) — żeby zaległe ENTWURF nie wyglądały jak „niczyje”.

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

## 3. Wypełnienie Befundu (krok po kroku)

Przy wejściu do szkicu system zakłada blokadę edycji. Jeśli dokument edytuje inna osoba, zobaczysz komunikat i nie wejdziesz do edycji.

### 3.1 Co zawiera ekran

- Podsumowanie danych z ankiety cyfrowej (jeśli taka ankieta była wypełniona).  
  Przy ścieżce papierowej zobaczysz informacje o autoryzacji i informację o braku ankiety cyfrowej.
- Część medyczna **Befund** — sekcje opisane poniżej.

![Fragment panelu Befund — grupy zmian](/docs/manual/assets/screenshots/doctor-04-befund-section.png)

### 3.2 Zakres badania i typ skóry

1. Zaznacz **zakres badania** (np. obszary niewłączone do oględzin — zgodnie z faktycznym przebiegiem wizyty).
2. Wybierz **typ skóry Fitzpatrick** — wymagany przed publikacją.
3. Ustaw **ocenę globalną obrazu** (np. czy potrzebna jest kontrola).

### 3.3 Grupy zmian (lesions)

Dla każdej **grupy zmian** z wideodermatoskopu:

1. Podaj **numery zmian** (te same numery co na urządzeniu / w protokole).
2. Zaznacz **cechy dermatoskopowe** (asymetria, nieregularny brzeg, siatka barwnikowa itd.).
3. Wybierz **ocenę kliniczną** oraz **ryzyko złośliwości**.
4. Przeczytaj tekst przygotowany przez system i **dostosuj go** w polu edytowalnym — to trafia do PDF.

Możesz dodać **kilka grup** (np. nieszkodliwe zmiany w jednej grupie, zmiany wymagające kontroli w drugiej). Pilnuj, by numery się nie powtarzały między grupami w sposób sprzeczny z protokołem.

### 3.4 Zalecenia, ocena końcowa, podsumowanie

1. Zaznacz **zalecenia** (np. kontrola za 6 miesięcy, wizyta przy zmianie).
2. Wybierz **ocenę końcową** (brak wysokiego podejrzenia / nie można wykluczyć).
3. Uzupełnij lub popraw **podsumowanie zbiorcze** — również edytowalne.

### 3.5 Szablony tekstu

Lekarz może korzystać z **własnych szablonów** (języki DE/EN/PL według konfiguracji). Szablony **globalne** lub **kliniczne** mogą być ograniczone do administratora — jeśli nie widzisz opcji tworzenia szablonu klinicznego, poproś admina.

### 3.6 Język publikacji PDF

Przy publikacji wybierasz język wersji dokumentu używany do generacji PDF — jest on **trwale** związany z wersją. Upewnij się, że odpowiada językowi ustalonemu z pacjentem, jeśli ma to znaczenie praktyczne.

---

## 4. Szkic vs publikacja

| Akcja | Skutek |
|--------|--------|
| **Zapisz jako szkic** | Możesz wrócić i edytować; **nie** uruchamia generowania PDF ani SMS. |
| **Podgląd PDF** | Otwiera podgląd na podstawie bieżącej treści (przed publikacją zwykle wymagany). |
| **Zatwierdź i wyślij (publikacja)** | Dokument przechodzi w tryb opublikowany; system w tle przygotowuje PDF, zapisuje go w archiwum i wysyła SMS logistyczny. |

![Pasek akcji — szkic i publikacja](/docs/manual/assets/screenshots/doctor-05-actions-draft.png)

### Krok po kroku — pierwsza publikacja

1. Uzupełnij Befund (sekcja 3) i kliknij **Zapisz jako szkic**, jeśli chcesz przerwać pracę.
2. Kliknij **Podgląd PDF** i sprawdź treść.
3. Wybierz język publikacji (jeśli jest wybór).
4. Kliknij **Zatwierdź i wyślij**.
5. Wróć na listę `/doctor/` — kolumny **PDF**, **HiDrive** i **SMS** pokażą postęp (odśwież stronę po chwili).

UI **nie blokuje** przeglądarki na czas generowania — statusy odświeżają się w liście lub w widoku szczegółów.

Jeśli klikniesz publikację kilka razy, system zwykle nie tworzy kilku takich samych publikacji (idempotencja).

---

## 5. Podgląd i statusy PDF · HiDrive · SMS

Po publikacji w szczegółach dokumentu (i na liście) widać stan łańcucha:

| Status | Znaczenie dla Ciebie |
|--------|----------------------|
| **PDF** | Czy plik wyniku został wygenerowany. |
| **HiDrive** | Czy kopia trafiła do archiwum placówki. |
| **SMS** | Czy pacjent dostał powiadomienie logistyczne (bez treści medycznej). |

![Dokument opublikowany — statusy i akcje](/docs/manual/assets/screenshots/doctor-06-published-status.png)

**Podgląd opublikowanego PDF** — użyj przycisku podglądu w trybie opublikowanym (etykieta może brzmieć inaczej niż przy szkicu).

Gdy któryś etap się nie powiedzie:

1. Sprawdź ponownie po kilku minutach.  
2. Jeśli błąd się utrzymuje — zgłoś **administratorowi** (recepcja / IT często sprawdza skrzynkę wyjściową — [SC-006](scenariusze.md#sc-006), [SC-013](scenariusze.md#sc-013)).  
3. Nie publikuj wielokrotnie „w panice” — potwierdź najpierw stan w panelu.

---

## 6. Edycja po publikacji → rewizja → nowa wersja

Gdy wynik jest już opublikowany, a trzeba go poprawić:

1. Otwórz dokument.
2. Kliknij **Rozpocznij rewizję** (lub równoważną etykietę) i potwierdź w oknie dialogowym.
3. Powstaje **wersja robocza korekty**. Na liście widać status opublikowany + etykietę **Rewizja**.
4. Zmień treść Befundu (grupy zmian, oceny, teksty).
5. Zrób **podgląd PDF** rewizji.
6. Kliknij publikację ponownie — powstaje **nowa wersja** PDF; pacjent w portalu zobaczy aktualną, nieunieważnioną wersję.

Dopóki rewizji nie **porzucisz** ani nie **opublikujesz**, system pokazuje otwartą korektę.

### Porzucenie rewizji

Jeśli zacząłeś korektę przez pomyłkę albo wracasz do poprzedniej wersji:

1. Otwórz dokument z otwartą rewizją.
2. Kliknij **Porzuć rewizję** i potwierdź.
3. Opublikowana wersja zostaje; pacjent nadal widzi poprzedni wynik.

Szczegóły i film: [SC-003](scenariusze.md#sc-003).

---

## 7. Wyślij SMS ponownie (`resend_sms`)

Przy **ponownej publikacji** (po rewizji) możesz zaznaczyć checkbox **Wyślij SMS ponownie**.

![Rewizja — checkbox SMS ponownie](/docs/manual/assets/screenshots/doctor-07-revision-resend-sms.png)

| Kiedy zaznaczać | Kiedy nie |
|-----------------|-----------|
| Pacjent ma dostać nowe powiadomienie o zaktualizowanym wyniku (wg procedury placówki). | Cicha korekta bez ponownego kontaktu SMS — zostaw odznaczone. |
| Po cofnięciu publikacji i ponownym opublikowaniu, gdy pacjent ma wrócić do portalu. | Gdy problemem jest tylko błąd techniczny SMS z pierwszej publikacji — często wystarczy ponów w skrzynce wyjściowej ([SC-006](scenariusze.md#sc-006)), bez ponownej publikacji. |

**Uwaga:** treść SMS pozostaje **logistyczna** (bez opisu badania). Stosuj checkbox zgodnie z regulaminem placówki.

Film / scenariusz: [SC-028](scenariusze.md#sc-028).

---

## 8. Cofnij publikację (revoke)

Gdy opublikowano **błędny** wynik albo trzeba **tymczasowo wycofać dostęp** pacjenta do PDF:

1. Otwórz **opublikowany** dokument (bez otwartej rewizji; łańcuch PDF/HiDrive/SMS powinien być zakończony).
2. Kliknij **Cofnij publikację**.
3. Potwierdź w oknie dialogowym.

![Okno potwierdzenia — cofnięcie publikacji](/docs/manual/assets/screenshots/doctor-08-revoke-modal.png)

### Co widzi pacjent

- Po cofnięciu ta wersja **nie pojawia się** na liście dokumentów w portalu wyników.
- SMS, który już wyszedł, **sam się nie cofnie** — pacjent mógł zobaczyć powiadomienie; poinformuj recepcję, jeśli pacjent dzwoni.
- Po korekcie: **opublikuj ponownie**; rozważ **Wyślij SMS ponownie** (sekcja 7).

Administrator **nie** cofa publikacji za lekarza. Nie usuwaj wersji ręcznie w panelu admina.

Szczegóły: [SC-015](scenariusze.md#sc-015). Widok pacjenta przy pustej liście: [SC-022](scenariusze.md#sc-022), [05-pacjent-wyniki.md](05-pacjent-wyniki.md).

---

## 9. Wylogowanie

Użyj opcji wylogowania w panelu lekarza. Kolejne wejście do panelu będzie wymagało ponownego logowania.

---

## 10. Dobre praktyki

- Sprawdzaj **status SMS** tylko jako informację techniczną — treść SMS w systemie jest **logistyczna** (bez opisu badania/wyniku), zgodnie z RODO/BÄK.
- Przed publikacją **przeczytaj** wygenerowany tekst i dostosuj go do siebie; nie polegaj wyłącznie na szablonie automatycznym.
- Przy wielu grupach zmian pilnuj spójności **numerów zmian** z wideodermatoskopu.
- Przy rewizji najpierw **podgląd**, potem publikacja; SMS ponownie — tylko gdy procedura tego wymaga.
- Przy błędzie medycznym w już wysłanym PDF — **revoke**, korekta, ponowna publikacja (nie „cicha” nadpisanie bez świadomości pacjenta, jeśli placówka wymaga ponownego powiadomienia).

Powiązane: [Przegląd](00-przeglad.md), [Administrator](04-administrator.md), [Autoryzacja ścieżki papierowej — szczegóły](04-administrator-paper-intake.md), [Diagram przepływu papierowego](paper_intake_flow.md), [Pacjent — portal wyników](05-pacjent-wyniki.md).

## Typowe problemy (scenariusze)

| Objaw | Scenariusz |
|-------|------------|
| Anulowany wpis nadal na liście / status „—” | [SC-001](scenariusze.md#sc-001), [SC-002](scenariusze.md#sc-002) |
| Porzucenie otwartej rewizji | [SC-003](scenariusze.md#sc-003) |
| Brak PDF labu / HTTP 424 | [SC-005](scenariusze.md#sc-005) |
| Blokada edycji przez kolegę | [SC-014](scenariusze.md#sc-014) |
| Cofnięcie publikacji | [SC-015](scenariusze.md#sc-015) |
| Rewizja + ponowny SMS | [SC-028](scenariusze.md#sc-028) |
| Brak ukończonej ankiety / brak autoryzacji papierowej | [SC-021](scenariusze.md#sc-021), [SC-017](scenariusze.md#sc-017) |
| Pełna lista | [scenariusze.md](scenariusze.md) |
