# Scenariusze operacyjne — FAQ i materiały wideo

Zbiór **codziennych sytuacji** z pracy placówki, opisanych tak, żeby recepcja, lekarz i manager szybko znaleźli rozwiązanie. Przy wielu scenariuszach jest też krótki filmik (WebM).

Powiązane: [README instrukcji](README.md), [nagrywanie filmów](assets/videos/README.md), backlog techniczny [`.ai/TODO.md`](../../.ai/TODO.md).

---

## Jak dopisywać nowy scenariusz

Skopiuj szablon na koniec pliku i uzupełnij:

```markdown
### SC-NNN — Krótki tytuł

| Pole | Treść |
|------|--------|
| **Role** | Recepcja / Lekarz / … |
| **Objaw** | Co widzi użytkownik |
| **Przyczyna** | 1–2 zdania, prostym językiem |
| **Co zrobić dziś** | Kroki operacyjne (co kliknąć, gdzie wejść) |
| **Czego nie robić** | Pułapki |
| **Docelowo** | Planowana poprawka / link do TODO |
| **Film** | `nie nagrany` / `scenariusze/sc-NNN.webm` |
| **Powiązane** | `docs/manual/…` |
```

Pisz dla osób nietechnicznych: nazwy z menu zamiast adresów URL, bez żargonu (OTP, Dead letter, T1…). Jeśli status w systemie jest po angielsku — podaj go i od razu wyjaśnij po polsku.

---

## Indeks

| ID | Tytuł | Role | Film |
|----|--------|------|------|
| [SC-001](#sc-001) | Anulowany wpis nadal w kolejce lekarza | Recepcja, Lekarz | `scenariusze/sc-001-anulowany-wpis.webm` |
| [SC-002](#sc-002) | Usunięty szkic — wpis ze statusem „—” | Recepcja, Lekarz, Admin | `scenariusze/sc-002-usuniety-szkic.webm` |
| [SC-003](#sc-003) | Otwarta rewizja — porzucenie | Lekarz | `scenariusze/sc-003-porzuc-rewizje.webm` |
| [SC-004](#sc-004) | Pobranie listy tygodniowej dla księgowości | Księgowość, Manager, Admin | `scenariusze/sc-004-raport-ksiegowosci.webm` |
| [SC-005](#sc-005) | Lekarz nie może otworzyć Befundu — brak PDF z laboratorium | Recepcja, Lekarz | `scenariusze/sc-005-brak-pdf-hidrive.webm` |
| [SC-006](#sc-006) | Pacjent nie dostał SMS — powtórka przez skrzynkę wyjściową | Recepcja, Manager, Administrator | `scenariusze/sc-006-sms-outbox.webm` |
| [SC-007](#sc-007) | Po imporcie XLSX w kolejce widać tylko jednego pacjenta | Recepcja | `reception/import-troubleshooting.webm` |
| [SC-008](#sc-008) | Pacjent nie może się zalogować do portalu — błędny telefon lub data urodzenia | Recepcja | `scenariusze/sc-008-portal-login.webm` |
| [SC-009](#sc-009) | Wspólny numer telefonu w rodzinie — portal prosi o nazwisko | Recepcja, Pacjent | `scenariusze/sc-009-wspolny-telefon.webm` |
| [SC-010](#sc-010) | Pacjent nie dostał kodu SMS do logowania w portalu | Recepcja, Manager, Administrator | `scenariusze/sc-010-otp-portal.webm` |
| [SC-011](#sc-011) | HiDrive: dwóch pacjentów o podobnym nazwisku — niejednoznaczna nazwa PDF | Recepcja, Lekarz | `scenariusze/sc-011-homonim-pdf.webm` |
| [SC-012](#sc-012) | HiDrive: plik odrzucony przez lekarza | Recepcja, Lekarz | `scenariusze/sc-012-rejected-pdf.webm` |
| [SC-013](#sc-013) | Błąd wysyłki PDF lub HiDrive — ponowienie z dashboardu | Recepcja, Administrator | `scenariusze/sc-013-outbox-pdf-hidrive.webm` |
| [SC-014](#sc-014) | Dokument zablokowany przez innego użytkownika | Lekarz, Manager | `scenariusze/sc-014-blokada-dokumentu.webm` |
| [SC-015](#sc-015) | Lekarz cofa publikację Befundu | Lekarz | `scenariusze/sc-015-revoke-publikacji.webm` |
| [SC-016](#sc-016) | Autoryzacja papierowa znika po ankiecie z tableta | Admin, Manager, Recepcja | `scenariusze/sc-016-papier-po-tablecie.webm` |
| [SC-017](#sc-017) | Lekarz nie widzi opcji dokumentu papierowego | Admin, Manager, Lekarz | `scenariusze/sc-017-paper-intake-t1.webm` |
| [SC-018](#sc-018) | Tablet: pusta lista kolejek | Recepcja, Administrator | `scenariusze/sc-018-tablet-bez-placowki.webm` |
| [SC-019](#sc-019) | Pacjent wypełnił ankietę przy niewłaściwym wpisie | Recepcja, Tablet, Administrator | `scenariusze/sc-019-zla-ankieta.webm` |
| [SC-020](#sc-020) | Wgranie i publikacja zewnętrznego wyniku PDF | Recepcja, Manager | `scenariusze/sc-020-external-upload.webm` |
| [SC-021](#sc-021) | Lekarz: „brak ukończonej ankiety” | Lekarz, Recepcja | `scenariusze/sc-021-brak-ankiety.webm` |
| [SC-022](#sc-022) | Pacjent: pusta lista dokumentów | Recepcja, Lekarz | `scenariusze/sc-022-pusta-lista-dokumentow.webm` |
| [SC-023](#sc-023) | Pacjent: minęło 60 dni dostępu do PDF | Recepcja, Manager | `scenariusze/sc-023-okno-60-dni.webm` |
| [SC-024](#sc-024) | Niskie saldo SMS / awaria kodów do portalu | Administrator, Recepcja | `scenariusze/sc-024-smsapi-saldo.webm` |
| [SC-025](#sc-025) | Korekta danych pacjenta — skutki dla portalu i HiDrive | Recepcja | `scenariusze/sc-025-korekta-danych.webm` |
| [SC-026](#sc-026) | Skrzynka wyjściowa: zablokowane po wielu błędach | Recepcja, Administrator | `scenariusze/sc-026-dead-letter.webm` |
| [SC-027](#sc-027) | Baner awarii HiDrive na dashboardzie recepcji | Recepcja, Administrator | `scenariusze/sc-027-baner-hidrive.webm` |
| [SC-028](#sc-028) | Rewizja Befundu + Wyślij SMS ponownie | Lekarz | `scenariusze/sc-028-rewizja-resend-sms.webm` |
| [SC-029](#sc-029) | SMS „wynik dostępny” po korekcie telefonu (bez republish) | Recepcja, Manager, Administrator | — |

> Kolumna **Film** = ścieżka względem `docs/manual/assets/videos/`. Pliki `.webm` nie są w gicie — generuj lokalnie (patrz backlog / [README filmów](assets/videos/README.md)).

Kotwice w indeksie to krótkie `#sc-001` … `#sc-029` (stabilne znaczniki HTML przy każdym scenariuszu — nie zależą od tytułu).

---

<a id="sc-001"></a>
### SC-001 — Anulowany wpis nadal w kolejce lekarza

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | W recepcji wizyta ma status **Anulowano**, ale lekarz na swojej liście pacjentów **nadal widzi** tę osobę (często różowe tło). |
| **Przyczyna** | Wcześniej system zostawiał anulowane wizyty na liście lekarza. Po poprawce anulowane wpisy **nie powinny** się tam pojawiać. |
| **Co zrobić dziś** | 1) W recepcji upewnij się, że anulowałaś/eś **właściwą** wizytę (ten sam dzień, ta sama osoba). 2) Poproś lekarza, by **odświeżył** listę (F5 albo ponowne wejście na listę). 3) **Nie otwieraj starego linku** z historii przeglądarki do karty pacjenta — po poprawce taki link nie działa. 4) Jeśli po wdrożeniu poprawki pacjent nadal widać — zgłoś to IT. |
| **Czego nie robić** | Nie traktuj anulowania wizyty jako „zamknięcia” sprawy, gdy pacjent już wypełnił ankietę. W systemie nie ma osobnego przycisku „anuluj ankietę”. |
| **Docelowo** | Poprawka wdrożona: anulowane wizyty nie trafiają na listę lekarza. |
| **Film** | `scenariusze/sc-001-anulowany-wpis.webm` — *„Anulowałem wizytę, a lekarz nadal widzi pacjenta”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md), [03-doktor.md](03-doktor.md) |

---

<a id="sc-002"></a>
### SC-002 — Usunięty szkic — wpis ze statusem „—”

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz, Administrator |
| **Objaw** | Po usunięciu **szkicu** Befundu w panelu admina lekarz nadal widzi wiersz: status **„—”**, puste kolumny PDF/SMS, przycisk **Otwórz**. |
| **Przyczyna** | Usunięcie szkicu nie zamyka wizyty. System traktuje pacjenta jak **osobę do opisania od nowa** (ankieta jest gotowa, a dokumentu jeszcze nie ma). |
| **Co zrobić dziś** | 1) Jeśli wizyta jest nieaktualna: w recepcji **anuluj wpis** — pacjent znika z listy lekarza (SC-001). 2) Jeśli wizyta jest prawdziwa — lekarz ma **opublikować** Befund, a nie usuwać szkicu. 3) Śmieciowe dane testowe można usunąć całym wpisem w panelu admina (po konsultacji z administratorem). |
| **Czego nie robić** | **Nie klikaj „Otwórz”** tylko po to, by „sprawdzić” — system utworzy **nowy** szkic. Nie zmieniaj statusu ankiety ręcznie w adminie bez procedury RODO. |
| **Docelowo** | Anulowanie zamyka listę lekarza (wdrożone). Osobna akcja „zamknij sprawę bez publikacji” — w backlogu. |
| **Film** | `scenariusze/sc-002-usuniety-szkic.webm` — *„Usunąłem szkic — dlaczego pacjent zostaje na liście?”* |
| **Powiązane** | [03-doktor.md](03-doktor.md) |

---

<a id="sc-003"></a>
### SC-003 — Otwarta rewizja — nie chcemy jej kończyć

| Pole | Treść |
|------|--------|
| **Role** | Lekarz |
| **Objaw** | Na liście lekarza: status **Opublikowany** + etykieta **Rewizja**; w kolumnach widać oczekiwanie. Lekarz zaczął korektę wyniku, ale chce wrócić do poprzedniej opublikowanej wersji. |
| **Przyczyna** | Jest otwarta **wersja robocza korekty**. Dopóki jej nie porzucisz ani nie opublikujesz, system pokazuje rewizję. |
| **Co zrobić dziś** | 1) Wejdź w szczegóły Befundu (ten pacjent). 2) Wybierz **Porzuć rewizję** i potwierdź. 3) Opublikowana wersja zostaje; pacjent w portalu nadal widzi poprzedni wynik. |
| **Czego nie robić** | Nie publikuj pustej korekty „żeby zniknęło”. Nie usuwaj wersji ręcznie w panelu admina. |
| **Docelowo** | Już obsłużone w produkcie. |
| **Film** | `scenariusze/sc-003-porzuc-rewizje.webm` — *„Jak anulować rozpoczętą korektę Befundu”* |
| **Powiązane** | [03-doktor.md](03-doktor.md) (sekcja 6), SC-028 |

---

<a id="sc-004"></a>
### SC-004 — Pobranie listy tygodniowej dla księgowości

| Pole | Treść |
|------|--------|
| **Role** | Księgowość, Manager, Administrator |
| **Objaw** | Potrzebna jest **lista pacjentów** z danego tygodnia (wg dnia badania): po pierwszej publikacji Befundu, po stawieniu się, albo lista **Ausfallhonorar** (niezrealizowane wizyty). |
| **Przyczyna** | Raport jest w panelu admina — nie ma go w recepcji ani u lekarza. |
| **Co zrobić dziś** | 1) Zaloguj się jako **Księgowość**, **Manager** lub **Administrator**. 2) W menu: **Księgowość → Raport tygodniowy**. 3) Wybierz wariant: **Opublikowane Befundy**, **Stawili się** albo **Ausfallhonorar**. 4) Ustaw zakres dat (domyślnie bieżący tydzień). 5) Pobierz **CSV** lub **XLSX** — plik ma wszystkie wiersze z zakresu, nie tylko stronę podglądu. |
| **Czego nie robić** | Nie szukaj tej listy w recepcji ani u lekarza. Zwykła korekta Befundu nie tworzy drugiej pozycji — liczy się pierwsza ważna publikacja. Publikacje z **Zewnętrzne badanie** nie wchodzą w wariant „Opublikowane Befundy”. |
| **Docelowo** | Kolumny płatności w eksporcie — backlog [`.ai/TODO.md`](../../.ai/TODO.md). |
| **Film** | `scenariusze/sc-004-raport-ksiegowosci.webm` — *„Jak pobrać tygodniową listę dla księgowości”* |
| **Powiązane** | [08-ksiegowosc-raport.md](08-ksiegowosc-raport.md), [04-administrator.md](04-administrator.md) |

---

<a id="sc-005"></a>
### SC-005 — Lekarz nie może otworzyć Befundu — brak PDF z laboratorium

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | Lekarz widzi komunikat, że **brakuje pliku PDF** z laboratorium i nie może wejść w Befund. |
| **Przyczyna** | W folderze `/incoming/` na HiDrive nie ma właściwego PDF, nazwa jest niejednoznaczna (SC-011), albo jedyny plik został wcześniej odrzucony (SC-012). |
| **Co zrobić dziś** | Recepcja: **`/admin/reception-dashboard/`** → sekcja **Brakujące wyniki HiDrive**. Sprawdź pacjenta i **sugerowaną nazwę pliku**, wgraj PDF lub popraw nazwę wg [hidrive_incoming_reception.md](hidrive_incoming_reception.md). |
| **Czego nie robić** | Przy czerwonym banerze awarii HiDrive (SC-027) **nie zakładaj**, że „wszyscy mają pliki” — lista może być pusta lub nieaktualna. |
| **Docelowo** | Alert przy braku wyniku ≥24 h — plan observability. |
| **Film** | `scenariusze/sc-005-brak-pdf-hidrive.webm` — *„Recepcja: brakujący PDF z laboratorium”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md), [hidrive_incoming_reception.md](hidrive_incoming_reception.md) |

---

<a id="sc-006"></a>
### SC-006 — Pacjent nie dostał SMS — powtórka przez skrzynkę wyjściową

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Manager, Administrator |
| **Objaw** | Befund jest **opublikowany**, a pacjent **nie dostał SMS-a** z dostępem do portalu — albo w systemie widać błąd wysyłki SMS. |
| **Przyczyna** | SMS idzie osobnym krokiem po publikacji. Może się nie udać (zły numer, problem firmy wysyłającej SMS) albo trzeba go wysłać ponownie. **Administrator nie może „opublikować ponownie” za lekarza.** |
| **Co zrobić dziś** | 1) Sprawdź **numer telefonu** pacjenta w karcie pacjenta. 2) Jeśli numer był zły — popraw go i użyj akcji **SMS: Ergebnis verfügbar** ([SC-029](scenariusze.md#sc-029)). 3) Albo wejdź w **Skrzynka wyjściowa → Zdarzenia**. 4) Znajdź zdarzenie **Wysyłka SMS** dla tej publikacji. 5) Przy błędzie: na dashboardzie recepcji kliknij **Ponów** albo w szczegółach zdarzenia ustaw status na **Oczekuje**. 6) Odczekaj chwilę na ponowną wysyłkę. |
| **Czego nie robić** | **Nie** proś lekarza o ponowną publikację tylko po to, by wymusić SMS. Nie zmieniaj statusów zdarzeń PDF/HiDrive bez potrzeby. Nie wysyłaj treści medycznej SMS-em poza systemem. |
| **Docelowo** | Akcja w module Patienten (SC-029). Przy republish lekarz ma checkbox **Wyślij SMS ponownie** ([SC-028](scenariusze.md#sc-028)). |
| **Film** | `scenariusze/sc-006-sms-outbox.webm` — *„Pacjent nie dostał SMS — powtórka ze skrzynki wyjściowej”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md), [04-administrator.md](04-administrator.md), [05-pacjent-wyniki.md](05-pacjent-wyniki.md), SC-029 |

---

<a id="sc-007"></a>
### SC-007 — Po imporcie XLSX w kolejce widać tylko jednego pacjenta

| Pole | Treść |
|------|--------|
| **Role** | Recepcja |
| **Objaw** | Zaimportowano plik z kilkoma pacjentami, ale w kolejce na dziś widać **tylko jedną** osobę; tablet też pokazuje jedną. |
| **Przyczyna** | Import wziął mniej wierszy niż myślisz — albo druga osoba **jest w bazie**, ale **nie dostała wpisu** do dzisiejszej kolejki. Komunikat „Błędy: 0” nie gwarantuje kompletnej listy. |
| **Co zrobić dziś** | 1) Otwórz **widok kolejek z listą pacjentów** i policz wpisy — porównaj z plikiem Excel. 2) Na dashboardzie recepcji wejdź w **Ostatnie importy** i sprawdź szczegóły. 3) Wyszukaj brakującą osobę w **Recepcja → Pacjenci**: jeśli jest → **dodaj wpis kolejki** na dziś. 4) Jeśli nie ma w systemie → popraw plik i importuj ponownie albo dodaj pacjenta ręcznie. 5) Sprawdź tablet przed przyjazdem pacjentów. |
| **Czego nie robić** | Nie zakładaj, że „Błędy: 0” = kompletna lista. Nie czekaj na IT, jeśli pacjent już istnieje — dopisanie do kolejki to zwykła praca recepcji. |
| **Docelowo** | Lepsze raportowanie pominiętych wierszy — backlog. |
| **Film** | `reception/import-troubleshooting.webm` — narracja: [import-troubleshooting-narration.pl.md](assets/videos/reception/import-troubleshooting-narration.pl.md) |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md), [assets/videos/README.md](assets/videos/README.md) |

---

<a id="sc-008"></a>
### SC-008 — Pacjent nie może się zalogować do portalu — błędny telefon lub data urodzenia

| Pole | Treść |
|------|--------|
| **Role** | Recepcja |
| **Objaw** | Pacjent na stronie logowania do portalu wyników dostaje komunikat o **nieprawidłowych danych** albo nie dostaje kodu SMS — mimo że wynik jest opublikowany. |
| **Przyczyna** | Portal sprawdza **telefon + datę urodzenia** tak, jak są zapisane w systemie. Literówka, stary numer albo pomyłka w dacie blokuje logowanie. |
| **Co zrobić dziś** | 1) Wejdź w **Recepcja → Pacjenci** i znajdź pacjenta. 2) Porównaj telefon i **datę urodzenia** z tym, co podaje pacjent (najlepiej z dokumentem tożsamości). 3) Popraw dane wg [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md). 4) **Powiedz pacjentowi ustnie obie** poprawione wartości. 5) Poproś o ponowną próbę logowania. |
| **Czego nie robić** | Nie dawaj pacjentowi hasła do konta personelu. Nie zmieniaj danych „na oko” — sprawdź dokument tożsamości. |
| **Docelowo** | Akcja **SMS: Ergebnis verfügbar** po korekcie telefonu ([SC-029](scenariusze.md#sc-029)). Dłuższy kod „wymuś dostęp” — backlog. |
| **Film** | `scenariusze/sc-008-portal-login.webm` — *„Pacjent nie może wejść na portal — poprawa telefonu i daty urodzenia”* |
| **Powiązane** | [05-pacjent-wyniki.md](05-pacjent-wyniki.md), [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md) |

---

<a id="sc-009"></a>
### SC-009 — Wspólny numer telefonu w rodzinie — portal prosi o nazwisko

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Pacjent (informacyjnie) |
| **Objaw** | Po telefonie i dacie urodzenia portal **prosi jeszcze o nazwisko** — albo (przy błędzie rejestracji) pacjent widzi dokumenty kogoś innego. |
| **Przyczyna** | Rodzina może mieć **jeden wspólny numer**. Gdy dwie osoby mają ten sam telefon i tę samą datę urodzenia, system prosi o **nazwisko**, żeby nie pomylić osób. |
| **Co zrobić dziś** | 1) Recepcja: upewnij się, że każda osoba ma **własną datę urodzenia**; przy wyszukiwaniu nie polegaj tylko na numerze. 2) Pacjent: loguje się swoim telefonem + swoją datą; w razie potrzeby wpisuje nazwisko **tak jak w recepcji**. 3) Jeśli ktoś widzi cudze dokumenty — natychmiast przerwij i zgłoś administratorowi / IT. |
| **Czego nie robić** | Nie wymyślaj sztucznych numerów „na siłę”. Nie udostępniaj kodu SMS między członkami rodziny. |
| **Docelowo** | Wspólny numer jest już obsługiwany. |
| **Film** | `scenariusze/sc-009-wspolny-telefon.webm` — *„Rodzina z jednym telefonem — logowanie do portalu”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md), [05-pacjent-wyniki.md](05-pacjent-wyniki.md), [runbook-patient-shared-phone.md](../runbook-patient-shared-phone.md) |

---

<a id="sc-010"></a>
### SC-010 — Pacjent nie dostał kodu SMS do logowania w portalu

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Manager, Administrator |
| **Objaw** | Pacjent poprawnie podał telefon i datę urodzenia, ale **nie dostał 6-cyfrowego kodu SMS** na telefon. To **inny** problem niż SMS po publikacji Befundu (SC-006). |
| **Przyczyna** | Osobna wysyłka **kodu SMS do logowania**. Możliwe: zły numer, opóźnienie operatora, awaria firmy wysyłającej SMS albo **niskie saldo konta SMS** (SC-024). Kod ważny ok. **15 minut**. |
| **Co zrobić dziś** | 1) Sprawdź numer telefonu w systemie. 2) Poproś pacjenta o **ponowne** żądanie kodu na stronie logowania. 3) Administrator: sprawdź **saldo konta SMS** (SC-024). 4) Jeśli nadal nic — zgłoś IT. 5) Nie proś lekarza o ponowną publikację Befundu — to nie pomoże przy logowaniu. |
| **Czego nie robić** | Nie myl z SC-006 (SMS po publikacji wyniku). Nie edytuj ręcznie sesji kodów w panelu admina bez IT. |
| **Docelowo** | Alerty na nieudane SMS i saldo — backlog. |
| **Film** | `scenariusze/sc-010-otp-portal.webm` — *„Pacjent nie dostał kodu do portalu”* |
| **Powiązane** | [05-pacjent-wyniki.md](05-pacjent-wyniki.md), SC-006, SC-024 |

---

<a id="sc-011"></a>
### SC-011 — HiDrive: dwóch pacjentów o podobnym nazwisku — niejednoznaczna nazwa PDF

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | Na dashboardzie recepcji status **Niejednoznaczna nazwa**; lekarz nie może otworzyć Befundu (jak w SC-005). Plik w folderze przychodzących wyników jest, ale system **nie wie**, do którego pacjenta należy. |
| **Przyczyna** | Jest **więcej niż jeden pacjent** pasujący do krótkiej nazwy pliku (np. bez daty urodzenia). System celowo **nie zgaduje**. |
| **Co zrobić dziś** | 1) Na HiDrive zmień nazwę pliku, dopisując **datę urodzenia**: `Nazwisko_Imie_RRRR_MM_DD.pdf`. 2) Użyj pełnego imienia i nazwiska jak w rejestracji. 3) Odśwież listę **Brakujące wyniki HiDrive** po ok. 1 minucie — status powinien zniknąć. 4) Poproś lekarza o ponowną próbę. |
| **Czego nie robić** | Nie przypisuj „na ślepo” jednego pliku do dwóch osób. Nie wrzucaj pliku z laboratorium do ścieżki **Zewnętrzne badanie**. |
| **Docelowo** | Alert przy długotrwałym braku wyniku. |
| **Film** | `scenariusze/sc-011-homonim-pdf.webm` — *„Dwóch pacjentów o podobnym nazwisku — data urodzenia w nazwie pliku”* |
| **Powiązane** | SC-005, [hidrive_incoming_reception.md](hidrive_incoming_reception.md) |

---

<a id="sc-012"></a>
### SC-012 — HiDrive: plik odrzucony przez lekarza

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | Na dashboardzie status **Tylko odrzucone pliki**; w folderze przychodzących wyników widać plik zaczynający się od `rejected_…`; lekarz nie może otworzyć Befundu. |
| **Przyczyna** | Lekarz **odrzucił** dopasowany plik (zła osoba, zły PDF). System pomija takie pliki przy kolejnym dopasowaniu. |
| **Co zrobić dziś** | 1) Ustal z lekarzem powód odrzucenia. 2) Usuń z nazwy pliku początek `rejected_` **albo** wgraj **nowy** PDF pod właściwą nazwą. 3) Przy otwartym szkicu — zamknij i otwórz kartę pacjenta ponownie. 4) Przy już opublikowanym dokumencie — zacznij korektę (rewizję) i otwórz kartę ponownie. |
| **Czego nie robić** | Nie usuwaj plików `rejected_…` bez wiedzy, który plik był błędny. Nie używaj **Zewnętrzne badanie** do podpięcia zwykłego pliku z laboratorium. |
| **Docelowo** | Ewentualny opis powodu odrzucenia w UI — backlog. |
| **Film** | `scenariusze/sc-012-rejected-pdf.webm` — *„Plik PDF odrzucony przez lekarza — co wgrać ponownie”* |
| **Powiązane** | SC-005, [hidrive_incoming_reception.md](hidrive_incoming_reception.md) |

---

<a id="sc-013"></a>
### SC-013 — Błąd wysyłki PDF lub HiDrive — ponowienie z dashboardu

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Administrator |
| **Objaw** | Befund **opublikowany**, ale kolumna **PDF** lub **HiDrive** pokazuje błąd; na dashboardzie recepcji widać zaległe zdarzenie. SMS mógł jeszcze nie wyjść. |
| **Przyczyna** | Po publikacji system kolejno: robi PDF → wysyła na HiDrive → wysyła SMS. Jeden krok mógł się nie udać (awaria, przekroczenie czasu, wygasły dostęp do chmury). |
| **Co zrobić dziś** | 1) Dashboard recepcji → sekcja **Zaległe zdarzenia** — przeczytaj komunikat. 2) Kliknij **Ponów** albo w **Skrzynka wyjściowa → Zdarzenia** ustaw status na **Oczekuje**. 3) Odczekaj 5–15 minut. 4) Przy problemie z dostępem do HiDrive — administrator + IT. 5) **Nie** publikuj Befundu ponownie, jeśli już jest opublikowany. |
| **Czego nie robić** | Nie myl z samym brakiem SMS (SC-006). Nie usuwaj wersji dokumentu w panelu admina. |
| **Docelowo** | Lepsze alerty monitoringu — backlog. |
| **Film** | `scenariusze/sc-013-outbox-pdf-hidrive.webm` — *„Dashboard: błąd PDF lub HiDrive — przycisk Ponów”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md), [INTEGRATION_ERROR.md](../runbooks/INTEGRATION_ERROR.md) |

---

<a id="sc-014"></a>
### SC-014 — Dokument zablokowany przez innego użytkownika

| Pole | Treść |
|------|--------|
| **Role** | Lekarz, Manager |
| **Objaw** | Na liście `/doctor/` wiersz jest **żółty**, w Statusie chip **W edycji / In Bearbeitung**, pod pacjentem **Edytuje: …**; przycisk **Otwórz** zablokowany, gdy edytuje **inna** osoba. Przy wejściu w szczegóły — komunikat o blokadzie. |
| **Przyczyna** | Tylko **jedna osoba** naraz może edytować szkic. Blokada trwa do zamknięcia karty / publikacji albo max. ok. **6 h** (`DOCUMENT_LOCK_TIMEOUT_HOURS`). |
| **Co zrobić dziś** | 1) Poproś kolegę/koleżankę o **zapisanie i zamknięcie** karty albo o publikację. 2) Po ok. 6 h blokada wygasa sama — wiersz przestaje być żółty; może zostać etykieta **Ostatnio edytował: …** (otwarcie dozwolone). 3) W nagłych przypadkach — IT. |
| **Czego nie robić** | Nie pracuj na tym samym szkicu w dwóch kartach przeglądarki jednocześnie. |
| **Docelowo** | Funkcja listy (chip + legenda) — wdrożona; rozszerzenie blokady przy korektach PUBLISHED — backlog M7. |
| **Film** | `scenariusze/sc-014-blokada-dokumentu.webm` — *„Dokument zablokowany — kolega ma otwarty szkic”* |
| **Powiązane** | [03-doktor.md](03-doktor.md) |

---

<a id="sc-015"></a>
### SC-015 — Lekarz cofa publikację Befundu

| Pole | Treść |
|------|--------|
| **Role** | Lekarz |
| **Objaw** | Opublikowano **błędny** Befund; pacjent mógł już dostać SMS. Trzeba **wycofać dostęp** do PDF w portalu. |
| **Przyczyna** | **Cofnięcie publikacji** oznacza, że pacjent po zalogowaniu **nie zobaczy** tej wersji wyniku na liście dokumentów. |
| **Co zrobić dziś** | 1) Na liście `/doctor/` otwórz **opublikowany** dokument (bez otwartej rewizji). 2) Upewnij się, że statusy PDF / HiDrive / SMS są zakończone (przycisk cofnięcia pojawia się dopiero wtedy). 3) Kliknij **Cofnij publikację** i potwierdź w oknie. 4) Poinformuj recepcję, jeśli pacjent dzwoni. 5) Po korekcie — **opublikuj ponownie**; jeśli pacjent ma dostać nowe powiadomienie, zaznacz **Wyślij SMS ponownie** (SC-028). |
| **Czego nie robić** | Nie usuwaj wersji ręcznie w panelu admina. Administrator **nie** cofa publikacji za lekarza. SMS „sam się nie cofnie” — pacjent mógł już zobaczyć powiadomienie. Nie zaczynaj rewizji zamiast revoke, jeśli celem jest natychmiastowe ukrycie błędnego PDF. |
| **Docelowo** | Funkcja jest w UI lekarza. |
| **Film** | `scenariusze/sc-015-revoke-publikacji.webm` — *„Cofnięcie publikacji — pacjent nie zobaczy błędnego PDF”* |
| **Powiązane** | [03-doktor.md](03-doktor.md) (sekcja 8), [05-pacjent-wyniki.md](05-pacjent-wyniki.md), SC-022, SC-028 |

---

<a id="sc-016"></a>
### SC-016 — Autoryzacja papierowa znika po ankiecie z tableta

| Pole | Treść |
|------|--------|
| **Role** | Admin, Manager, Recepcja |
| **Objaw** | Zrobiono **autoryzację ścieżki papierowej**, ale pacjent potem **wypełnił ankietę na tablecie** — opcja papierowa znika; w panelu **Autoryzacja papieru** autoryzacja jest nieaktywna. |
| **Przyczyna** | System **automatycznie unieważnia** ścieżkę papierową, gdy ankieta cyfrowa została wysłana. Preferuje ścieżkę cyfrową. |
| **Co zrobić dziś** | 1) Zaakceptuj ścieżkę cyfrową (zalecane). 2) Jeśli ankieta była pomyłką (SC-019) — zgłoś IT; nie planuj równolegle papier + tablet na ten sam wpis. |
| **Czego nie robić** | Nie autoryzuj papieru „na zapas”, jeśli pacjent i tak pójdzie na tablet. |
| **Docelowo** | Opisane w [paper_intake_flow.md](paper_intake_flow.md). |
| **Film** | `scenariusze/sc-016-papier-po-tablecie.webm` — *„Ścieżka papierowa: co gdy pacjent mimo to wypełni tablet”* |
| **Powiązane** | [04-administrator-paper-intake.md](04-administrator-paper-intake.md), [paper_intake_flow.md](paper_intake_flow.md) |

---

<a id="sc-017"></a>
### SC-017 — Lekarz nie widzi opcji dokumentu papierowego

| Pole | Treść |
|------|--------|
| **Role** | Admin, Manager, Lekarz |
| **Objaw** | Pacjent **nie** wypełnił tableta; lekarz widzi „brak ukończonej ankiety” i **nie ma** przycisku utworzenia dokumentu papierowego. |
| **Przyczyna** | Brak **autoryzacji ścieżki papierowej** (robi to admin/manager w panelu **Autoryzacja papieru**) albo warunki nie są spełnione (za wcześnie po godzinie wizyty, ankieta już wysłana, wizyta anulowana). |
| **Co zrobić dziś** | 1) **Administrator lub Manager** (nie recepcja): menu **Autoryzacja papieru** → **Autoryzuj ścieżkę papierową** z podaniem powodu. 2) Sprawdź godzinę wizyty. 3) Odśwież listę lekarza — powinna pojawić się akcja **utworzenia dokumentu papierowego**. 4) Lekarz tworzy dokument i prowadzi dalej jak zwykle. |
| **Czego nie robić** | Recepcja **nie** wykonuje autoryzacji ścieżki papierowej. Nie omijaj tej autoryzacji ręcznym tworzeniem dokumentu w panelu admina. |
| **Docelowo** | Procedura w [04-administrator-paper-intake.md](04-administrator-paper-intake.md). |
| **Film** | `scenariusze/sc-017-paper-intake-t1.webm` — *„Od autoryzacji papierowej do listy lekarza”* |
| **Powiązane** | [04-administrator-paper-intake.md](04-administrator-paper-intake.md), [03-doktor.md](03-doktor.md) |

---

<a id="sc-018"></a>
### SC-018 — Tablet: pusta lista kolejek

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Administrator |
| **Objaw** | Po zalogowaniu na tablecie **brak kolejek** na dziś — mimo że w panelu admina kolejki istnieją. |
| **Przyczyna** | Tablet nie ma przypisanej **placówki**, albo nie ma kolejki na dziś dla tej placówki. |
| **Co zrobić dziś** | 1) Administrator: **Recepcja → Urządzenia tablet** — ustaw placówkę dla tego urządzenia. 2) Recepcja: sprawdź, czy jest kolejka na dziś. 3) Na tablecie **wyloguj i zaloguj** ponownie. |
| **Czego nie robić** | Nie zostawiaj konta Administrator / Recepcja na tablecie na stałe w poczekalni — używaj dedykowanego konta tablet. |
| **Docelowo** | Konfiguracja operacyjna — bez zmiany produktu. |
| **Film** | `scenariusze/sc-018-tablet-bez-placowki.webm` — *„Tablet nie widzi pacjentów — przypisanie placówki”* |
| **Powiązane** | [02-tablet.md](02-tablet.md), [04-administrator.md](04-administrator.md) |

---

<a id="sc-019"></a>
### SC-019 — Pacjent wypełnił ankietę przy niewłaściwym wpisie

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Tablet, Administrator |
| **Objaw** | Ankieta jest przypisana do **innej** osoby niż ta, która wypełniała formularz. Lekarz u „właściwego” pacjenta widzi pustą ankietę; u „złego” — cudzą treść. |
| **Przyczyna** | Na tablecie wybrano **złego pacjenta** z listy. To poważny błąd operacyjny — wymaga pomocy IT. |
| **Co zrobić dziś** | 1) **Zatrzymaj** pracę lekarza nad oboma wpisami — **nie publikuj**. 2) **Zgłoś IT / administratorowi** — potrzebne bezpieczne przeniesienie ankiety. 3) Po naprawie — ponowne potwierdzenie zgód u właściwej osoby. 4) Na tablecie **zawsze** sprawdź kartę tożsamości przed oddaniem urządzenia. |
| **Czego nie robić** | **Nigdy** nie przepisuj ręcznie powiązań ankiety w panelu admina „na własną rękę”. Nie kasuj ankiety bez audytu. Nie publikuj „żeby zamknąć sprawę”. |
| **Docelowo** | Dedykowana akcja „przepnij ankietę” — backlog [`.ai/TODO.md`](../../.ai/TODO.md). |
| **Film** | `scenariusze/sc-019-zla-ankieta.webm` — *„Pomyłka na tablecie — jak rozpoznać złego pacjenta”* |
| **Powiązane** | [02-tablet.md](02-tablet.md), [01-rejestracja.md](01-rejestracja.md) |

---

<a id="sc-020"></a>
### SC-020 — Wgranie i publikacja zewnętrznego wyniku PDF

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Manager |
| **Objaw** | Wynik jest **gotowym PDF** (laboratorium zewnętrzne / inna placówka) — trzeba go opublikować pacjentowi z SMS, bez formularza skórnego lekarza. |
| **Przyczyna** | Do tego służy moduł **Zewnętrzne badanie**, nie zwykły folder wyników z laboratorium. |
| **Co zrobić dziś** | 1) Dashboard recepcji → skrót **Zewnętrzne badanie** (albo ta sama pozycja w menu). 2) Wybierz wpis kolejki. 3) Wgraj PDF. 4) Wybierz załącznik i **potwierdź tożsamość** pacjenta. 5) Opublikuj (język DE/EN/PL). 6) Śledź status jak przy zwykłym Befundzie (PDF, HiDrive, SMS). |
| **Czego nie robić** | Nie wrzucaj tego pliku do zwykłego folderu wyników z laboratorium. Nie publikuj bez weryfikacji tożsamości. **Wgranie zewnętrznego wyniku** nie wchodzi w raport księgowości „Opublikowane Befundy” (SC-004). |
| **Docelowo** | MVP wdrożone. |
| **Film** | `scenariusze/sc-020-external-upload.webm` — *„Wgranie i publikacja zewnętrznego PDF wyniku”* |
| **Powiązane** | [07-wgranie-zewnetrznego-badania.md](07-wgranie-zewnetrznego-badania.md), [01-rejestracja.md](01-rejestracja.md) |

---

<a id="sc-021"></a>
### SC-021 — Lekarz: „brak ukończonej ankiety”

| Pole | Treść |
|------|--------|
| **Role** | Lekarz, Recepcja |
| **Objaw** | Lekarz klika **Otwórz** — komunikat, że **ankieta nie została ukończona**. |
| **Przyczyna** | Pacjent nie wysłał formularza na tablecie, sesja trwa, wizyta anulowana, albo planowana jest ścieżka papierowa (SC-017). |
| **Co zrobić dziś** | 1) Upewnij się, że pacjent **dokończył i wysłał** formularz na tablecie. 2) Sprawdź, czy wizyta nie jest anulowana. 3) Jeśli tablet niemożliwy → SC-017 (autoryzacja ścieżki papierowej). 4) Odśwież listę lekarza. |
| **Czego nie robić** | Nie twórz dokumentu ręcznie w panelu admina bez procedury. |
| **Docelowo** | Operacja standardowa. |
| **Film** | `scenariusze/sc-021-brak-ankiety.webm` — *„Lekarz nie może otworzyć pacjenta — najpierw ankieta na tablecie”* |
| **Powiązane** | [03-doktor.md](03-doktor.md), [02-tablet.md](02-tablet.md), SC-017 |

---

<a id="sc-022"></a>
### SC-022 — Pacjent: pusta lista dokumentów

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | Pacjent przeszedł kod SMS do logowania, ale lista dokumentów jest **pusta** — albo plik wcześniej był, a teraz zniknął. |
| **Przyczyna** | Befund jeszcze nieopublikowany / wysyłka w toku; lekarz **cofnął publikację** (SC-015); albo pacjent zalogował się na **zły rekord** (wspólny telefon, SC-009). |
| **Co zrobić dziś** | 1) Sprawdź u lekarza status (publikacja, PDF, SMS). 2) Przy cofnięciu publikacji — poczekaj na korektę i ponowną publikację. 3) Przy wspólnym numerze — zweryfikuj datę urodzenia i nazwisko. |
| **Czego nie robić** | Nie wysyłaj PDF mailem bez procedury RODO. |
| **Docelowo** | Lepszy status „w przygotowaniu” w portalu — backlog. |
| **Film** | `scenariusze/sc-022-pusta-lista-dokumentow.webm` — *„Dlaczego lista wyników jest pusta po kodzie SMS”* |
| **Powiązane** | [05-pacjent-wyniki.md](05-pacjent-wyniki.md), SC-015, SC-013 |

---

<a id="sc-023"></a>
### SC-023 — Pacjent: minęło 60 dni dostępu do PDF

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Manager |
| **Objaw** | Pacjent loguje się poprawnie, ale wynik jest **niedostępny** — minęło **ponad 60 dni** od publikacji. |
| **Przyczyna** | Lokalna kopia PDF na serwerze jest usuwana po 60 dniach. Archiwum na HiDrive może nadal istnieć. |
| **Co zrobić dziś** | 1) Potwierdź datę publikacji. 2) Manager / IT: pobierz kopię z HiDrive (folder pacjentów) lub z archiwum placówki. 3) Udostępnij pacjentowi **zgodnie z procedurą RODO**. |
| **Czego nie robić** | Nie obiecuj stałego dostępu przez portal powyżej 60 dni. Nie używaj prywatnego Dysku Google. |
| **Docelowo** | Runbook awaryjny — backlog. |
| **Film** | `scenariusze/sc-023-okno-60-dni.webm` — *„Wynik po 2 miesiącach — skąd wziąć kopię z archiwum”* |
| **Powiązane** | [05-pacjent-wyniki.md](05-pacjent-wyniki.md) |

---

<a id="sc-024"></a>
### SC-024 — Niskie saldo SMS / awaria kodów do portalu

| Pole | Treść |
|------|--------|
| **Role** | Administrator, Recepcja |
| **Objaw** | **Wielu** pacjentów naraz nie dostaje kodów SMS do logowania w portalu; bywa też problem z SMS po Befundzie (SC-006). |
| **Przyczyna** | Wyczerpane **saldo konta SMS** (firma wysyłająca SMS) albo awaria dostawcy. |
| **Co zrobić dziś** | 1) Administrator: **doładuj konto SMS**. 2) Pacjenci mogą ponownie prosić o kod na stronie logowania. 3) Poinformuj recepcję — przygotuj komunikat dla dzwoniących. |
| **Czego nie robić** | Nie ignoruj pierwszego zgłoszenia. Nie wysyłaj kodów z prywatnego telefonu. |
| **Docelowo** | Alert + baner na dashboardzie — backlog. |
| **Film** | `scenariusze/sc-024-smsapi-saldo.webm` — *„Awaria SMS — co robi recepcja”* |
| **Powiązane** | SC-006, SC-010, [INTEGRATION_ERROR.md](../runbooks/INTEGRATION_ERROR.md) |

---

<a id="sc-025"></a>
### SC-025 — Korekta danych pacjenta — skutki dla portalu i HiDrive

| Pole | Treść |
|------|--------|
| **Role** | Recepcja |
| **Objaw** | Po zmianie imienia, nazwiska, telefonu lub daty urodzenia pacjent nie loguje się **albo** lekarz traci dopasowanie PDF z laboratorium. |
| **Przyczyna** | Portal i dopasowanie plików z laboratorium korzystają z tych samych danych pacjenta. |
| **Co zrobić dziś** | 1) Edytuj dane wg [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md). 2) Po zapisie powiedz pacjentowi nowe dane do logowania. 3) Po korekcie telefonu przy opublikowanym wyniku — **SMS: Ergebnis verfügbar** ([SC-029](scenariusze.md#sc-029)). 4) Jeśli trzeba — popraw nazwę pliku z laboratorium wg [hidrive_incoming_reception.md](hidrive_incoming_reception.md). |
| **Czego nie robić** | Nie zmieniaj danych „dla wygody” bez weryfikacji tożsamości. |
| **Docelowo** | Procedura operacyjna + akcja SMS (SC-029). |
| **Film** | `scenariusze/sc-025-korekta-danych.webm` — *„Zmiana nazwiska — portal, SMS i plik z laboratorium”* |
| **Powiązane** | [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md), SC-008, SC-011, SC-029 |

---

<a id="sc-026"></a>
### SC-026 — Skrzynka wyjściowa: zablokowane po wielu błędach

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Administrator |
| **Objaw** | Zdarzenie w **Skrzynka wyjściowa → Zdarzenia** ma status **Dead letter** (czyli: **zablokowane po wielu błędach**). Wysyłka PDF, HiDrive lub SMS „utknęła”. |
| **Przyczyna** | System **przestał próbować automatycznie** po serii nieudanych prób (trwały błąd). |
| **Co zrobić dziś** | 1) Przeczytaj komunikat błędu przy zdarzeniu. 2) Usuń przyczynę (zły telefon, brak dostępu do HiDrive itd.). 3) Ustaw status z **Dead letter** na **Oczekuje** albo użyj **Ponów** na dashboardzie. 4) Odczekaj na ponowną próbę. |
| **Czego nie robić** | Nie oznaczaj jako **Przetworzono** bez realnego sukcesu. Nie kasuj zdarzeń bez IT. |
| **Docelowo** | Alert na zdarzenia zablokowane po wielu błędach — backlog. |
| **Film** | `scenariusze/sc-026-dead-letter.webm` — *„Zablokowane po wielu błędach — kiedy ręcznie ustawić Oczekuje”* |
| **Powiązane** | [OUTBOX_BACKLOG_AGE.md](../runbooks/OUTBOX_BACKLOG_AGE.md), SC-006, SC-013 |

---

<a id="sc-027"></a>
### SC-027 — Baner awarii HiDrive na dashboardzie recepcji

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Administrator |
| **Objaw** | Na **Dashboardzie operacyjnym** recepcji widać **baner awarii HiDrive** (ostrzeżenie); sekcja brakujących wyników pusta lub nieaktualna; lekarze masowo zgłaszają blokadę Befundu. |
| **Przyczyna** | Chwilowa niedostępność HiDrive, wygasły dostęp albo problem sieci. Reszta dashboardu (importy, skrzynka wyjściowa) może działać. |
| **Co zrobić dziś** | 1) **Nie** ufaj pustej liście brakujących plików. 2) Administrator / IT: sprawdź status HiDrive i odśwież dostęp. 3) Po powrocie — odśwież dashboard i uzupełnij brakujące PDF (SC-005). 4) Informuj lekarzy o znanym incydencie. |
| **Czego nie robić** | Nie publikuj zewnętrznych wyników w szczycie awarii. Nie porządkuj plików w folderze przychodzących wyników „na zaś” w trakcie awarii. |
| **Docelowo** | Alert operacyjny HiDrive — plan observability. |
| **Film** | `scenariusze/sc-027-baner-hidrive.webm` — *„Baner awarii HiDrive — co recepcja robi inaczej”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md), SC-005, [INTEGRATION_ERROR.md](../runbooks/INTEGRATION_ERROR.md) |

---

<a id="sc-028"></a>
### SC-028 — Rewizja Befundu + Wyślij SMS ponownie

| Pole | Treść |
|------|--------|
| **Role** | Lekarz |
| **Objaw** | Opublikowany wynik wymaga **korekty**; po nowej publikacji pacjent ma dostać **kolejne powiadomienie SMS** (logistyczne). |
| **Przyczyna** | Przy republish system domyślnie **nie** wysyła SMS ponownie — trzeba zaznaczyć **Wyślij SMS ponownie**. |
| **Co zrobić dziś** | 1) Otwórz opublikowany Befund → **Rozpocznij rewizję**. 2) Popraw treść (grupy zmian, oceny, teksty). 3) **Podgląd PDF** rewizji. 4) Zaznacz checkbox **Wyślij SMS ponownie**. 5) Opublikuj ponownie. 6) Na liście sprawdź status SMS. |
| **Czego nie robić** | Nie myl z SC-006 (ponów SMS z skrzynki wyjściowej bez nowej publikacji). Nie zaznaczaj checkboxa „na zapas”, jeśli placówka nie chce ponownego kontaktu. Nie publikuj bez podglądu. |
| **Docelowo** | Już w UI lekarza. |
| **Film** | `scenariusze/sc-028-rewizja-resend-sms.webm` — *„Rewizja i ponowny SMS po publikacji”* |
| **Powiązane** | [03-doktor.md](03-doktor.md) (sekcje 6–7), SC-003, SC-006, SC-015, SC-029 |

---

<a id="sc-029"></a>
### SC-029 — SMS „wynik dostępny” po korekcie telefonu (bez republish)

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Manager, Administrator |
| **Objaw** | Befund jest **opublikowany**, pacjent miał **zły numer** — po poprawie w kartotece trzeba wysłać SMS z dostępem do portalu, **bez** ponownego opisu / publikacji. |
| **Przyczyna** | SMS po publikacji poszedł na stary numer albo wcale. Numer w systemie jest już poprawiony; pacjent ma sam wejść na portal. |
| **Co zrobić dziś** | 1) Popraw telefon wg [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md). 2) Na karcie pacjenta (lub na liście — akcja masowa) kliknij **SMS: Ergebnis verfügbar**. 3) Odczekaj na wysyłkę (scheduler / skrzynka wyjściowa). 4) Poproś pacjenta o sprawdzenie SMS i logowanie do portalu. |
| **Czego nie robić** | Nie proś lekarza o republish tylko dla SMS. Nie myl z kodem OTP do logowania (SC-010) ani z checkboxem lekarza przy rewizji (SC-028). |
| **Docelowo** | Już w module Patienten. |
| **Film** | — (manual wystarczy; nagranie opcjonalne) |
| **Powiązane** | [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md), SC-006, SC-008, SC-025 |

---

## Backlog filmów

| Priorytet | SC | Czas ~ | Odbiorca | Status |
|-----------|-----|--------|----------|--------|
| Wysoki | SC-001 | 2–3 min | Recepcja + lekarz | **Nagrany** `scenariusze/sc-001-anulowany-wpis.webm` |
| Wysoki | SC-002 | 2 min | Admin / recepcja | **Nagrany** `scenariusze/sc-002-usuniety-szkic.webm` |
| Wysoki | SC-006 | 2–3 min | Recepcja / admin | **Nagrany** `scenariusze/sc-006-sms-outbox.webm` |
| Wysoki | SC-007 | 3–4 min | Recepcja | **Nagrany** `reception/import-troubleshooting.webm` |
| Wysoki | SC-008 | 2 min | Recepcja | **Nagrany** `scenariusze/sc-008-portal-login.webm` |
| Wysoki | SC-010 | 2–3 min | Recepcja / admin | **Nagrany** `scenariusze/sc-010-otp-portal.webm` |
| Wysoki | SC-019 | 2–3 min | Tablet + recepcja | **Nagrany** `scenariusze/sc-019-zla-ankieta.webm` |
| Średni | SC-003 | 2 min | Lekarz | **Nagrany** `scenariusze/sc-003-porzuc-rewizje.webm` |
| Średni | SC-004 | 2–3 min | Księgowość | **Nagrany** `scenariusze/sc-004-raport-ksiegowosci.webm` |
| Średni | SC-005 | 2–3 min | Recepcja | **Nagrany** `scenariusze/sc-005-brak-pdf-hidrive.webm` |
| Średni | SC-011 | 2 min | Recepcja | **Nagrany** `scenariusze/sc-011-homonim-pdf.webm` |
| Średni | SC-013 | 2 min | Recepcja | **Nagrany** `scenariusze/sc-013-outbox-pdf-hidrive.webm` |
| Średni | SC-015 | 2 min | Lekarz | **Nagrany** `scenariusze/sc-015-revoke-publikacji.webm` |
| Średni | SC-017 | 3 min | Admin + lekarz | **Nagrany** `scenariusze/sc-017-paper-intake-t1.webm` |
| Średni | SC-020 | 3–4 min | Recepcja | **Nagrany** `scenariusze/sc-020-external-upload.webm` |
| Średni | SC-028 | 2 min | Lekarz | **Nagrany** `scenariusze/sc-028-rewizja-resend-sms.webm` |
| Niski | SC-009, SC-012, SC-014, SC-016, SC-018, SC-021–SC-027 | 1–3 min | Różne | **Nagrane** — ścieżki w indeksie powyżej |

### Ponowne nagranie

```powershell
# 1) Seed (Docker) — HiDrive mock trafia do wspólnego JSON
#    docs/manual/_build/hidrive-mock-state.json (widoczny dla procesu web)
docker compose exec -w /app -e PYTHONPATH=/app web `
  python scripts/manual_demo/seed_scenarios.py --scenario sc-011 --write-ctx

# 2) Nagranie (obraz Playwright) — SC-011/012/027 ustawiają mock ponownie na starcie
docker compose --profile manual-videos run --rm --no-deps `
  -e PYTHONPATH=/app -e SCREENSHOT_SKIP_DJANGO=1 `
  -e HIDRIVE_INCOMING_PATH=/public/incoming `
  manual-videos python scripts/record_scenario_videos.py `
  --scenario sc-011 --base-url http://web:8000 --slow-mo 500

# Priorytet / wszystkie:
# --priority high | medium | low | high+medium
# --all
```

**SC-011 / SC-012 / SC-027 (HiDrive mock → web):** stan mocka jest w pliku JSON współdzielonym przez volume `.:/app`, nie w ClassVar procesu recordera. Przy nagraniu ustaw `HIDRIVE_INCOMING_PATH` tak jak w `.env` web (u nas `/public/incoming`). Przykład trzech filmów:

```powershell
foreach ($s in 'sc-011','sc-012','sc-027') {
  docker compose exec -w /app -e PYTHONPATH=/app web `
    python scripts/manual_demo/seed_scenarios.py --scenario $s --write-ctx
}
docker compose --profile manual-videos run --rm --no-deps `
  -e PYTHONPATH=/app -e SCREENSHOT_SKIP_DJANGO=1 `
  -e HIDRIVE_INCOMING_PATH=/public/incoming `
  manual-videos python scripts/record_scenario_videos.py `
  --scenario sc-011 --scenario sc-012 --scenario sc-027 `
  --base-url http://web:8000 --slow-mo 500
```

SC-007: `python scripts/record_import_troubleshooting_video.py --base-url http://127.0.0.1:8000` (lub ten sam obraz `manual-videos`).

Pliki `.webm` nie są w gicie — generuj lokalnie. Po nagraniu ścieżki w indeksie i backlogu powinny wskazywać pliki w `docs/manual/assets/videos/`.
