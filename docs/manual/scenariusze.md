# Scenariusze operacyjne — FAQ i materiały wideo

Zbiór **realnych przypadków** z produkcji / testów, które warto opisać w instrukcji lub **nagrać krótkim filmikiem** (WebM), żeby recepcja, lekarz i manager szybko znaleźli rozwiązanie.

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
| **Przyczyna (techniczna)** | 1–2 zdania, bez żargonu gdzie możliwe |
| **Co zrobić dziś (obejście)** | Kroki operacyjne |
| **Czego nie robić** | Pułapki |
| **Docelowo (produkt)** | Link do TODO / fix |
| **Film** | `nie nagrany` / `scenariusze/sc-NNN.webm` |
| **Powiązane** | `docs/manual/…`, issue |
```

---

## Indeks

| ID | Tytuł | Role | Film |
|----|--------|------|------|
| [SC-001](#sc-001-anulowany-wpis-nadal-w-kolejce-lekarza) | Anulowany wpis nadal w kolejce lekarza | Recepcja, Lekarz | nie nagrany |
| [SC-002](#sc-002-usunięty-szkic-wpis-z-statusem--) | Usunięty szkic — wpis ze statusem „—” | Recepcja, Lekarz, Admin | nie nagrany |
| [SC-003](#sc-003-otwarta-rewizja-revision-a-nie-chcemy-jej-kończyć) | Otwarta rewizja — porzucenie | Lekarz | nie nagrany |
| [SC-004](#sc-004-pobranie-listy-tygodniowej-dla-księgowości) | Pobranie listy tygodniowej dla księgowości | Księgowość, Manager, Admin | nie nagrany |
| [SC-005](#sc-005-lekarz-nie-może-otworzyć-befundu-brak-pdf-z-laboratorium) | Lekarz nie może otworzyć Befundu — brak PDF z laboratorium | Recepcja, Lekarz | nie nagrany |
| [SC-006](#sc-006-pacjent-nie-dostał-sms-powtórka-przez-outbox) | Pacjent nie dostał SMS — powtórka przez outbox | Recepcja, Manager, Administrator | nie nagrany |
| [SC-007](#sc-007-po-imporcie-xlsx-w-kolejce-widać-tylko-jednego-pacjenta) | Po imporcie XLSX w kolejce widać tylko jednego pacjenta | Recepcja | `reception/import-troubleshooting.webm` |
| [SC-008](#sc-008-pacjent-nie-może-się-zalogować-do-portalu-błędny-telefon-lub-data-urodzenia) | Pacjent nie może się zalogować do portalu — błędny telefon lub data urodzenia | Recepcja | nie nagrany |
| [SC-009](#sc-009-wspólny-numer-telefonu-w-rodzinie-portal-prosi-o-nazwisko) | Wspólny numer telefonu w rodzinie — portal prosi o nazwisko | Recepcja, Pacjent | nie nagrany |
| [SC-010](#sc-010-pacjent-nie-dostał-kodu-otp-logowanie-portalu) | Pacjent nie dostał kodu OTP (logowanie portalu) | Recepcja, Manager, Administrator | nie nagrany |
| [SC-011](#sc-011-hidrive-niejednoznaczna-nazwa-pliku-pdf-homonim) | HiDrive: niejednoznaczna nazwa pliku PDF (homonim) | Recepcja, Lekarz | nie nagrany |
| [SC-012](#sc-012-hidrive-plik-odrzucony-przez-lekarza-prefix-rejected_) | HiDrive: plik odrzucony przez lekarza (prefix `rejected_`) | Recepcja, Lekarz | nie nagrany |
| [SC-013](#sc-013-błąd-outbox-pdf-lub-hidrive-ponowienie-z-dashboardu) | Błąd outbox PDF lub HiDrive — ponowienie z dashboardu | Recepcja, Administrator | nie nagrany |
| [SC-014](#sc-014-dokument-medyczny-zablokowany-przez-innego-użytkownika) | Dokument medyczny zablokowany przez innego użytkownika | Lekarz, Manager | nie nagrany |
| [SC-015](#sc-015-lekarz-cofa-publikację-befundu-revoke) | Lekarz cofa publikację Befundu (revoke) | Lekarz | nie nagrany |
| [SC-016](#sc-016-autoryzacja-papierowa-znika-po-wysłaniu-ankiety-z-tableta) | Autoryzacja papierowa znika po wysłaniu ankiety z tableta | Admin, Manager, Recepcja | nie nagrany |
| [SC-017](#sc-017-lekarz-nie-widzi-opcji-dokumentu-papierowego-brak-t1) | Lekarz nie widzi opcji dokumentu papierowego — brak T1 | Admin, Manager, Lekarz | nie nagrany |
| [SC-018](#sc-018-tablet-pusta-lista-kolejek-nieprzypisane-urządzenie) | Tablet: pusta lista kolejek — nieprzypisane urządzenie | Recepcja, Administrator | nie nagrany |
| [SC-019](#sc-019-pacjent-wypełnił-ankietę-przy-niewłaściwym-wpisie-kolejki) | Pacjent wypełnił ankietę przy niewłaściwym wpisie kolejki | Recepcja, Tablet, Administrator | nie nagrany |
| [SC-020](#sc-020-publikacja-zewnętrznego-pdf-wyniku-badania-external-upload) | Publikacja zewnętrznego PDF wyniku badania (external upload) | Recepcja, Manager | nie nagrany |
| [SC-021](#sc-021-lekarz-komunikat-brak-ukończonej-ankiety) | Lekarz: komunikat „brak ukończonej ankiety” | Lekarz, Recepcja | nie nagrany |
| [SC-022](#sc-022-pacjent-pusta-lista-dokumentów-lub-wycofana-publikacja) | Pacjent: pusta lista dokumentów lub wycofana publikacja | Recepcja, Lekarz | nie nagrany |
| [SC-023](#sc-023-pacjent-minęło-okno-60-dni-dostępu-do-pdf) | Pacjent: minęło okno 60 dni dostępu do PDF | Recepcja, Manager | nie nagrany |
| [SC-024](#sc-024-niskie-saldo-smsapi--awaria-wysyłki-otp) | Niskie saldo SMSAPI / awaria wysyłki OTP | Administrator, Recepcja | nie nagrany |
| [SC-025](#sc-025-korekta-danych-pacjenta-skutki-dla-portalu-i-hidrive) | Korekta danych pacjenta — skutki dla portalu i HiDrive | Recepcja | nie nagrany |
| [SC-026](#sc-026-outbox-dead_letter-ręczne-odblokowanie-zdarzenia) | Outbox `DEAD_LETTER` — ręczne odblokowanie zdarzenia | Recepcja, Administrator | nie nagrany |
| [SC-027](#sc-027-baner-awarii-hidrive-na-dashboardzie-recepcji) | Baner awarii HiDrive na dashboardzie recepcji | Recepcja, Administrator | nie nagrany |

---

### SC-001 — Anulowany wpis nadal w kolejce lekarza

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | W recepcji wpis ma status **Anulowano**, ale na liście lekarza (`/doctor/`) wiersz **nadal jest** (różowe tło, status `—` lub wcześniej SZKIC). |
| **Przyczyna (techniczna)** | Wcześniej: kolejka lekarza kwalifikowała wpis przy ankiecie `SUBMITTED`/`REOPENED` bez wykluczenia `CANCELLED`. **Od wdrożenia fix:** `list_doctor_work_queue` wyklucza `entry_status=CANCELLED`. |
| **Co zrobić dziś (obejście)** | 1) Upewnij się, że anulowałeś **właściwy** wpis (ten ze statusem „Pacjent zakończył”, nie inny slot tego samego dnia). 2) **Nie używaj starego linku** `/doctor/open/{uuid}/` ani zakładki z historii — po wdrożeniu zwracają **404** i nie tworzą szkicu. 3) Odśwież listę lekarza — anulowany wpis nie powinien się pojawiać. 4) Jeśli nadal widać wpis po deployu — zgłoś IT (stara wersja `web`). |
| **Czego nie robić** | Nie traktuj anulowania wpisu jako „zamknięcia przypadku” przy złożonej ankiecie. Nie ma osobnej akcji „anuluj ankietę” w UI. |
| **Docelowo (produkt)** | Wykluczenie `CANCELLED` z listy **oraz** blokada `/doctor/open/` i `POST /api/v1/medical-documents` — wdrożone (`check_doctor_queue_entry_access`, `create_or_get_medical_document`). |
| **Film** | nie nagrany — proponowany tytuł: *„Anulowałem wizytę, a lekarz nadal widzi pacjenta”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md), [03-doktor.md](03-doktor.md) § lista pracy |

---

### SC-002 — Usunięty szkic — wpis ze statusem „—”

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz, Administrator |
| **Objaw** | Po usunięciu **szkicu dokumentu** (`MedicalDocument` w adminie) lekarz nadal widzi wiersz: status **`—`**, kolumny PDF/HiDrive/SMS puste, przycisk **Otwórz**, różowe tło (SLA). |
| **Przyczyna (techniczna)** | Usunięcie szkicu = brak dokumentu. System traktuje to jak **nowego kandydata do opisania** (tier 0: `medical_document IS NULL` + ankieta `SUBMITTED`). To **nie** zamyka wizyty. |
| **Co zrobić dziś (obejście)** | Jeśli wizyta jest nieaktualna: **anuluj wpis w recepcji** — po wdrożeniu fix wpis znika z listy lekarza (SC-001). Dla śmieciowych danych testowych — usunięcie całego wpisu kolejki w adminie. Jeśli wizyta jest realna — lekarz ma **opublikować** Befund, nie usuwać szkicu. |
| **Czego nie robić** | **Nie klikać „Otwórz”** — `create_or_get_medical_document` utworzy **nowy** szkic DRAFT. Nie zmieniać ręcznie statusu ankiety na `IN_PROGRESS` w adminie bez procedury RODO. |
| **Docelowo (produkt)** | Wykluczenie `CANCELLED` — wdrożone; akcja „zamknij przypadek bez publikacji” — backlog. |
| **Film** | nie nagrany — proponowany tytuł: *„Usunąłem szkic w adminie — dlaczego pacjent zostaje na liście?”* |
| **Powiązane** | [03-doktor.md](03-doktor.md) |

---

### SC-003 — Otwarta rewizja (REVISION) — nie chcemy jej kończyć

| Pole | Treść |
|------|--------|
| **Role** | Lekarz |
| **Objaw** | Na liście: **Opublikowany** + etykieta **Rewizja**; kolumny outbox **Oczekuje**. Lekarz otworzył korektę, ale ma wrócić do poprzedniej opublikowanej wersji. |
| **Przyczyna (techniczna)** | `has_pending_revision=True` — dokument w tier 0 (wspólna praca). Istnieje wersja DRAFT rewizji. |
| **Co zrobić dziś (obejście)** | W szczegółach Befundu: **Porzuć rewizję** (`POST …/discard-revision`). Opublikowana wersja zostaje; pacjent w portalu widzi poprzedni wynik. |
| **Czego nie robić** | Nie publikować pustej rewizji „żeby zniknęło”. Nie usuwać ręcznie wersji w adminie bez znajomości outbox. |
| **Docelowo (produkt)** | Już obsłużone w produkcie — brak dodatkowego fixu; ewentualnie krótszy opis w manualu lekarza. |
| **Film** | nie nagrany — proponowany tytuł: *„Jak anulować rozpoczętą korektę Befundu”* |
| **Powiązane** | [03-doktor.md](03-doktor.md), API `discard-revision` |

---

### SC-004 — Pobranie listy tygodniowej dla księgowości

| Pole | Treść |
|------|--------|
| **Role** | Księgowość (`ACCOUNTING`), Manager, Administrator |
| **Objaw** | Księgowość potrzebuje **listy pacjentów** w danym tygodniu **wg daty badania** — po **pierwszej publikacji Befundu**, po **stawieniu się / złożonej ankiecie**, albo listę **Ausfallhonorar** (nie zrealizowali wizyty — do windykacji). |
| **Przyczyna (techniczna)** | Raport jest modułem admina — nie ma go w panelu recepcji ani lekarza. Zakres dat filtruje po `queue_date`. Parametr `report_mode=published|attended|ausfall`. |
| **Co zrobić dziś (instrukcja)** | 1) Zaloguj się na konto z rolą **Accounting**, **Manager** lub **Admin** (np. `https://…/admin/`). 2) W menu po lewej: **Księgowość** → **Raport tygodniowy** (`/admin/accounting/report/`). 3) Wybierz **Wariant raportu**: **Opublikowane Befundy**, **Stawili się** albo **Ausfallhonorar**. 4) **Zakres dat:** domyślnie bieżący tydzień (pon.–niedz.) — dotyczy **dnia badania**; opcjonalnie ustaw **Data od** / **Data do** — tabela odświeży się **automatycznie** po wyborze daty lub wariantu (przycisk „Pokaż raport” jest opcjonalny). 5) Sprawdź podgląd tabeli (przy Ausfallhonorar — kolumna **Ausfallhonorar**=`Ja`; sekcja per lekarz ukryta). 6) Pobierz plik: **Eksport CSV** lub **Eksport XLSX** — zawiera **wszystkie** wiersze z zakresu (nie tylko bieżącą stronę podglądu). Nazwa pliku zawiera wariant: `accounting_report_{published|attended|ausfall}_{data_od}_{data_do}.…`. |
| **Kolumny w pliku** | Nr, Vorname, Nachname, **Straße**, **PLZ/Ort** (kod + miejscowość), Email, Befund-Arzt (lekarz pierwszej publikacji; pusta przy Ausfallhonorar), Untersuchungsdatum (data badania / kolejki); w wariancie Ausfallhonorar dodatkowo **Ausfallhonorar**=`Ja`. Kolumny płatności (Rechnungsbetrag, Überweisung, Kartenzahlung) — **jeszcze niedostępne** w systemie. |
| **Czego nie robić** | Nie szukaj tej listy w recepcji ani u lekarza. Nie licz **rewizji** Befundu jako osobnych wizyt — raport obejmuje tylko **pierwszą** publikację (`version_no = 1`). Publikacje „Zewnętrzne badanie” (EXTERNAL_UPLOAD) nie wchodzą w ten raport. |
| **Docelowo (produkt)** | Kolumny płatności w eksporcie — backlog [`.ai/TODO.md`](../../.ai/TODO.md); ewentualny film instruktażowy — poniżej. |
| **Film** | nie nagrany — proponowany tytuł: *„Jak pobrać tygodniową listę dla księgowości (CSV/XLSX)”* |
| **Powiązane** | [08-ksiegowosc-raport.md](08-ksiegowosc-raport.md) (pełna specyfikacja), [04-administrator.md](04-administrator.md) |

### SC-005 — Lekarz nie może otworzyć Befundu — brak PDF z laboratorium

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | Lekarz widzi komunikat o braku dopasowanego pliku PDF w HiDrive (blokada wejścia w Befund / HTTP 424). |
| **Przyczyna (techniczna)** | W folderze `/incoming/` na HiDrive nie ma pliku PDF o nazwie zgodnej z pacjentem, nazwa jest niejednoznaczna (homonim), albo jedyny pasujący plik ma prefix `rejected_`. |
| **Co zrobić dziś (obejście)** | Recepcja otwiera **`/admin/reception-dashboard/`** → sekcja **Brakujące wyniki HiDrive**. Sprawdza pacjenta, status i **sugerowaną nazwę pliku**; wgrywa PDF do `/incoming/` lub poprawia nazwę wg [hidrive_incoming_reception.md](hidrive_incoming_reception.md). |
| **Czego nie robić** | Nie udostępniać dashboardu roli bez uprawnień recepcji (TABLET, księgowość). Przy banerze awarii HiDrive na dashboardzie — nie traktować pustej listy jako „wszyscy mają pliki”. |
| **Docelowo (produkt)** | Alert operacyjny ≥24 h — observability ([`.cursor/plans/observability_stack_upgrade.plan.md`](../../.cursor/plans/observability_stack_upgrade.plan.md)). |
| **Film** | nie nagrany — proponowany tytuł: *„Recepcja: brakujący PDF z laboratorium na HiDrive”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md) §2, [hidrive_incoming_reception.md](hidrive_incoming_reception.md) |

---

### SC-006 — Pacjent nie dostał SMS — powtórka przez outbox

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Manager, Administrator |
| **Objaw** | Befund jest **opublikowany**, w panelu lekarza kolumna **SMS** wygląda na zakończoną (sukces), ale pacjent **nie otrzymał** SMS-a z kodem do portalu — albo zdarzenie outbox ma status błędu (`Nieudane` / `Dead letter`). |
| **Przyczyna (techniczna)** | Wysyłka SMS jest **osobnym zdarzeniem outbox** (`SMS_SEND`) w łańcuchu po publikacji. Może się nie powieść (brak numeru, błąd bramki SMS), zostać pominięta przy rewizji bez flagi `resend_sms`, albo SMS mógł nie dotrzeć mimo statusu „Przetworzono” po stronie systemu. **Administrator nie może ponownie opublikować Befundu** — publikacja należy wyłącznie do lekarza. |
| **Co zrobić dziś (obejście)** | **Przed ponowieniem:** sprawdź w adminie **numer telefonu pacjenta** (poprawny format, obsługiwany kraj SMS). **1)** Wejdź na **`/admin/outbox/outboxevent/`** (menu **Skrzynka wyjściowa → Zdarzenia skrzynki wyjściowej**). **2)** Filtruj po **Typ zdarzenia: Wysyłka SMS** i znajdź wiersz powiązany z **właściwą wersją dokumentu medycznego** (kolumna „Wersja dokumentu medycznego”). **3a)** Gdy status to **`Nieudane`** lub **`Dead letter`**: na **`/admin/reception-dashboard/`** użyj **Ponów** przy błędzie outbox **albo** w edycji zdarzenia ustaw status na **`Oczekuje`** (`PENDING`). **3b)** Gdy status to **`Przetworzono`**, a SMS trzeba wysłać **ponownie** (np. pacjent potwierdza brak wiadomości): otwórz rekord zdarzenia `SMS_SEND` dla tej wersji i **cofnij status** z **`Przetworzono`** na **`Oczekuje`**. Opcjonalnie wyczyść pole **Przetworzono** (`processed_at`) i upewnij się, że **Dostępne od** (`available_at`) jest w przeszłości. **4)** Poczekaj na worker (`scheduler`) lub — po konsultacji z IT — uruchom ręcznie: `python manage.py enqueue_tasks`. **5)** Odśwież dashboard recepcji i listę lekarza — brak nowego błędu outbox oznacza ponowną próbę. |
| **Czego nie robić** | **Nie** proś lekarza o „republikację” Befundu tylko po to, żeby admin wymusił SMS — admin **nie ma** tej akcji. Nie zmieniaj statusu zdarzeń **PDF** ani **HiDrive** bez potrzeby. Nie wysyłaj SMS poza systemem z treścią medyczną (RODO/BÄK). Przy **Zewnętrznym badaniu** (`EXTERNAL_UPLOAD`) rozważ ponowną publikację z checkboxem **Wyślij SMS ponownie** zamiast ręcznej edycji outbox — patrz [07-wgranie-zewnetrznego-badania.md](07-wgranie-zewnetrznego-badania.md). |
| **Docelowo (produkt)** | Osobna akcja „wyślij SMS ponownie” bez edycji statusu w adminie — backlog [`.ai/TODO.md`](../../.ai/TODO.md). |
| **Film** | nie nagrany — proponowany tytuł: *„Recepcja: pacjent nie dostał SMS — cofnięcie statusu zdarzenia outbox”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md) § dashboard recepcji, [04-administrator.md](04-administrator.md) §8, [05-pacjent-wyniki.md](05-pacjent-wyniki.md), runbook [OUTBOX_BACKLOG_AGE.md](../runbooks/OUTBOX_BACKLOG_AGE.md) |

---

### SC-007 — Po imporcie XLSX w kolejce widać tylko jednego pacjenta

| Pole | Treść |
|------|--------|
| **Role** | Recepcja |
| **Objaw** | Zaimportowano plik z Doctolib / XLSX z **dwoma** (lub więcej) pacjentami, ale w widoku master/detail na dziś w kolejce widać **jedną** osobę; tablet pokazuje tylko jednego pacjenta. |
| **Przyczyna (techniczna)** | Import przetworzył mniej wierszy niż oczekiwano (`Total rows = 1` w szczegółach batcha) — np. zły plik, brak wymaganych kolumn w drugim wierszu, albo drugi pacjent **jest w bazie**, ale **nie dostał wpisu kolejki** z tego importu. Dashboard pokazuje „Dodano: 1, Błędy: 0” — brak błędu ≠ pełny sukces biznesowy. |
| **Co zrobić dziś (obejście)** | 1) **Master/detail** — policz wpisy na dziś vs oczekiwana liczba z Excela. 2) **Dashboard recepcji → Ostatnie importy** — sprawdź `Total rows`, `Dodano`, `Błędy`; wejdź w **szczegóły importu**. 3) **Patients** — wyszukaj brakującą osobę po nazwisku: jeśli **jest** w bazie → **Queue entries → Add** — dopisz do dzisiejszej kolejki (status Waiting, kolejna pozycja). 4) Jeśli **nie ma** w bazie → popraw plik XLSX (wymagane: imię, nazwisko, telefon, e-mail, data urodzenia) i **importuj ponownie** albo dodaj pacjenta ręcznie + wpis kolejki. 5) Zweryfikuj na **tablecie** przed przyjazdem pacjentów. |
| **Czego nie robić** | Nie zakładaj, że „Błędy: 0” oznacza komplet listy — zawsze porównaj liczbę wierszy importu z liczbą wpisów w kolejce. Nie czekaj na IT, jeśli pacjent już istnieje — dopisanie wpisu kolejki to standardowa operacja recepcji. |
| **Docelowo (produkt)** | Lepsze raportowanie „wiersze pominięte / pominięte z powodu” w UI importu — backlog dokumentacji w [`.ai/TODO.md`](../../.ai/TODO.md). |
| **Film** | `reception/import-troubleshooting.webm` — narracja: [assets/videos/reception/import-troubleshooting-narration.pl.md](assets/videos/reception/import-troubleshooting-narration.pl.md) |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md) §5, [assets/videos/README.md](assets/videos/README.md) |

---

### SC-008 — Pacjent nie może się zalogować do portalu — błędny telefon lub data urodzenia

| Pole | Treść |
|------|--------|
| **Role** | Recepcja |
| **Objaw** | Pacjent na stronie logowania portalu (`/`) dostaje komunikat o **nieprawidłowych danych** albo system **nie wysyła** kodu OTP — mimo że Befund jest opublikowany. |
| **Przyczyna (techniczna)** | Portal weryfikuje **numer telefonu + datę urodzenia** względem rekordu pacjenta w DB. Literówka przy rejestracji, stary numer po zmianie karty SIM, pomyłka dnia/miesiąca urodzenia, albo pacient wpisuje dane sprzed korekty w recepcji. |
| **Co zrobić dziś (obejście)** | 1) W **`/admin/reception/patient/`** wyszukaj pacjenta (przy wspólnym numerze — po **imię + nazwisko**, nie sam telefon). 2) Porównaj **Phone** i **Date of birth** z tym, co podaje pacjent. 3) Popraw wg [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md). 4) **Poinformuj pacjenta ustnie** o **obu** wartościach po korekcie. 5) Poproś o ponowną próbę logowania. |
| **Czego nie robić** | Nie podawaj pacjentowi hasła do kont staff. Nie wysyłaj treści medycznej SMS-em poza systemem bez procedury RODO. Nie zmieniaj danych „na oko” — sprawdź dokument tożsamości pacjenta. |
| **Docelowo (produkt)** | Akcja „wymuś wysłanie dostępu” z dłuższym OTP — backlog [`.ai/TODO.md`](../../.ai/TODO.md). |
| **Film** | nie nagrany — proponowany tytuł: *„Recepcja: pacjent nie może wejść na portal — poprawa telefonu i daty urodzenia”* |
| **Powiązane** | [05-pacjent-wyniki.md](05-pacjent-wyniki.md), [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md) |

---

### SC-009 — Wspólny numer telefonu w rodzinie — portal prosi o nazwisko

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Pacjent (informacyjnie) |
| **Objaw** | Po wpisaniu telefonu i daty urodzenia portal **prosi dodatkowo o nazwisko** — albo pacjent widzi **dokumenty innej osoby** (błąd operacyjny przy rejestracji). |
| **Przyczyna (techniczna)** | Od wersji 1.5 **wspólny numer** jest dozwolony u wielu pacjentów (unikalna **czwórka**: imię + nazwisko + telefon + DOB). Przy **kolizji phone+DOB** u dwóch osób portal wymaga **nazwiska** jako doprecyzowania. Przy pomyłce DOB między członkami rodziny pacjent może trafić na zły rekord. |
| **Co zrobić dziś (obejście)** | **Recepcja:** 1) Upewnij się, że każda osoba ma **własną datę urodzenia** w systemie (nawet przy wspólnym telefonie). 2) Przy rejestracji/edycji wybieraj właściwy rekord — nie szukaj wyłącznie po numerze. 3) Poinformuj pacjenta: logowanie po **własnym** telefonie + **własnej** dacie urodzenia; w skrajnym przypadku (ten sam numer i ta sama DOB u dwóch osób) — wpisz **nazwisko** jak w recepcji. **Pacjent:** wpisz nazwisko dokładnie (wielkość liter zwykle nie ma znaczenia po normalizacji). |
| **Czego nie robić** | Nie twórz sztucznie różnych numerów „na siłę”, jeśli rodzina ma jeden telefon — system to obsługuje. Nie udostępniaj OTP między członkami rodziny. |
| **Docelowo (produkt)** | Wdrożone (wspólny numer + doprecyzowanie nazwiskiem); ewentualnie ostrzeżenie w UI tableta przy wyborze pacjenta z numerem współdzielonym. |
| **Film** | nie nagrany — proponowany tytuł: *„Rodzina z jednym telefonem — jak logować się do portalu wyników”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md) §4.1, [05-pacjent-wyniki.md](05-pacjent-wyniki.md), [docs/runbook-patient-shared-phone.md](../runbook-patient-shared-phone.md) |

---

### SC-010 — Pacjent nie dostał kodu OTP (logowanie portalu)

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Manager, Administrator |
| **Objaw** | Pacjent poprawnie przeszedł krok 1 (telefon + DOB), ale **nie otrzymał SMS-a z 6-cyfrowym kodem OTP** na `/otp/` — albo portal pokazuje błąd wysyłki. **To nie jest** ten sam problem co SC-006 (SMS **po publikacji Befundu**). |
| **Przyczyna (techniczna)** | Osobny kanał SMS dla **OTP portalu** (`PatientResultsOtpSession`). Możliwe: błąd bramki SMSApi, **niskie saldo konta**, zły format numeru, opóźnienie operatora, lub incydent prod (`sms_failed` w audycie zamiast HTTP 500). Kod OTP ważny ~**15 min** (`OTP_VALID_MINUTES`). |
| **Co zrobić dziś (obejście)** | 1) Zweryfikuj **numer telefonu** pacjenta w adminie (format, kraj — DE/PL/GB). 2) Poproś pacjenta o **ponowne żądanie kodu** (wróć do kroku 1 logowania). 3) **Administrator:** sprawdź saldo SMSApi, logi/Sentry (`PATIENT_RESULTS_OTP_REQUEST`, `outcome=sms_failed`), runbook [INTEGRATION_ERROR.md](../runbooks/INTEGRATION_ERROR.md). 4) Jeśli publikacja Befundu jest OK, a problem dotyczy tylko OTP — **nie** proś lekarza o republikację (SC-006). 5) Przy awarii trwałej — procedura awaryjna Google Drive (backlog [`.ai/TODO.md`](../../.ai/TODO.md)). |
| **Czego nie robić** | Nie myl z SC-006 (zdarzenie outbox `SMS_SEND` po publikacji). Nie edytuj ręcznie rekordów OTP w adminie bez konsultacji IT. |
| **Docelowo (produkt)** | Alert na `sms_failed` i saldo SMSApi — backlog [`.ai/TODO.md`](../../.ai/TODO.md); akcja „wymuś wysłanie dostępu” z OTP 24 h. |
| **Film** | nie nagrany — proponowany tytuł: *„Pacjent nie dostał kodu OTP — odróżnienie od SMS po Befundzie”* |
| **Powiązane** | [05-pacjent-wyniki.md](05-pacjent-wyniki.md), SC-006, SC-024 |

---

### SC-011 — HiDrive: niejednoznaczna nazwa pliku PDF (homonim)

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | Dashboard recepcji: status **AMBIGUOUS** / niejednoznaczna nazwa; lekarz nie może otworzyć Befundu (SC-005). W `/incoming/` jest plik PDF, ale system **nie dopasowuje** go do jednego pacjenta. |
| **Przyczyna (techniczna)** | W bazie jest **więcej niż jeden pacjent** pasujący do krótkiej nazwy pliku (np. `Muller_Hans.pdf`) bez daty urodzenia w nazwie. System celowo **nie zgaduje** — wymaga doprecyzowania. |
| **Co zrobić dziś (obejście)** | 1) Dashboard → **Sugerowana nazwa pliku** lub [hidrive_incoming_reception.md](hidrive_incoming_reception.md). 2) **Zmień nazwę pliku** na HiDrive, dopisując datę urodzenia: `Nazwisko_Imie_RRRR_MM_DD.pdf` (np. `Muller_Hans_1985_03_12.pdf`). 3) Użyj **wszystkich członów** imienia i nazwiska jak w rejestracji. 4) Odśwież listę lekarza / dashboard po ~1 min. |
| **Czego nie robić** | Nie dopasowuj „na ślepo” jednego pliku do dwóch pacjentów. Nie wrzucaj pliku do `external-upload/` — to inna ścieżka ([07-wgranie-zewnetrznego-badania.md](07-wgranie-zewnetrznego-badania.md)). |
| **Docelowo (produkt)** | Alert ≥24 h na brakujące wyniki — observability. |
| **Film** | nie nagrany — proponowany tytuł: *„HiDrive: dwóch pacjentów o podobnym nazwisku — dopisanie daty urodzenia do nazwy pliku”* |
| **Powiązane** | SC-005, [hidrive_incoming_reception.md](hidrive_incoming_reception.md) §Kolizje |

---

### SC-012 — HiDrive: plik odrzucony przez lekarza (prefix `rejected_`)

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | W `/incoming/` jest plik `rejected_Imie_Nazwisko.pdf`; dashboard: **REJECTED_ONLY**; lekarz nie może otworzyć Befundu. |
| **Przyczyna (techniczna)** | Lekarz **odrzucił** dopasowany plik (zła osoba, zły PDF, uszkodzony plik). System dodaje prefix `rejected_` i **ignoruje** taki plik przy kolejnym dopasowaniu. |
| **Co zrobić dziś (obejście)** | 1) Ustal z lekarzem **powód odrzucenia** (pomyłka labu vs zła nazwa). 2) Wgraj **nowy, poprawny PDF** pod **właściwą nazwą** (bez `rejected_`) — stary plik zostaw w `/incoming/` lub przenieś do archiwum po uzgodnieniu z IT. 3) Sprawdź zgodność nazwy z danymi pacjenta w rejestracji. 4) Zweryfikuj na dashboardzie, że status zmienił się z REJECTED_ONLY. |
| **Czego nie robić** | Nie usuwaj `rejected_*` bez wiedzy, który plik był błędny — to ślad audytowy operacji. Nie zmieniaj tylko nazwy z `rejected_` na poprawną bez weryfikacji treści PDF. |
| **Docelowo (produkt)** | Ewentualny opis powodu odrzucenia w UI lekarza — backlog produktowy. |
| **Film** | nie nagrany — proponowany tytuł: *„Recepcja: plik PDF odrzucony przez lekarza — co wgrać ponownie”* |
| **Powiązane** | SC-005, [hidrive_incoming_reception.md](hidrive_incoming_reception.md) §Pliki odrzucone |

---

### SC-013 — Błąd outbox PDF lub HiDrive — ponowienie z dashboardu

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Administrator |
| **Objaw** | Befund **opublikowany**, ale w liście lekarza kolumna **PDF** lub **HiDrive** ma status błędu; dashboard recepcji pokazuje zdarzenie outbox typu **`GENERATE_PDF`** lub **`HIDRIVE_UPLOAD`** ze statusem `Nieudane` / `Dead letter`. SMS mógł jeszcze nie pójść (kolejność łańcucha). |
| **Przyczyna (techniczna)** | Asynchroniczny pipeline outbox: `GENERATE_PDF` → `HIDRIVE_UPLOAD` → `SMS_SEND`. Błąd WeasyPrint, timeout HiDrive, wygasły token OAuth, chwilowa awaria chmury. Scheduler odpala co ~300 s; po 3 retry → `DEAD_LETTER`. |
| **Co zrobić dziś (obejście)** | 1) **`/admin/reception-dashboard/`** → sekcja **Zaległe zdarzenia** — przeczytaj typ i komunikat błędu. 2) **Ponów** przy wierszu błędu **albo** w `/admin/outbox/outboxevent/` ustaw status na **`Oczekuje`**. 3) Poczekaj 5–15 min lub po konsultacji z IT: `python manage.py enqueue_tasks`. 4) Przy **401 HiDrive** — administrator: odśwież `HIDRIVE_REFRESH_TOKEN`, restart `web` + `scheduler` (runbook [INTEGRATION_ERROR.md](../runbooks/INTEGRATION_ERROR.md)). 5) **Nie** publikuj Befundu ponownie, jeśli wersja jest już `PUBLISHED`. |
| **Czego nie robić** | Nie myl z SC-006 (tylko SMS). Nie restartuj produkcji w szczycie bez IT. Nie usuwaj wersji dokumentu w adminie. |
| **Docelowo (produkt)** | Naprawa alertów Prometheus (scheduler vs scrape web) — [`.ai/TODO.md`](../../.ai/TODO.md). |
| **Film** | nie nagrany — proponowany tytuł: *„Dashboard recepcji: błąd PDF lub HiDrive — przycisk Ponów”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md) §2, [INTEGRATION_ERROR.md](../runbooks/INTEGRATION_ERROR.md), [OUTBOX_BACKLOG_AGE.md](../runbooks/OUTBOX_BACKLOG_AGE.md) |

---

### SC-014 — Dokument medyczny zablokowany przez innego użytkownika

| Pole | Treść |
|------|--------|
| **Role** | Lekarz, Manager |
| **Objaw** | Na liście `/doctor/` wiersz ma oznaczenie **blokady**; przy wejściu w szczegóły komunikat, że dokument edytuje **inna osoba** (imię użytkownika). Nie można zapisać szkicu. |
| **Przyczyna (techniczna)** | Semaphore edycji DRAFT: jeden aktywny edytor na dokument, blokada do **24 h** lub do publikacji / zamknięcia karty przeglądarki przez edytora. |
| **Co zrobić dziś (obejście)** | 1) Skontaktuj się z osobą na blokadzie — niech **zapisze szkic i zamknie kartę** lub **opublikuje**. 2) Manager może sprawdzić, kto ma otwarty dokument (komunikat na liście). 3) Po 24 h blokada wygasa automatycznie. 4) W nagłych przypadkach — zgłoś IT (ręczne zwolnienie w adminie tylko z procedurą). |
| **Czego nie robić** | Nie pracuj równolegle na tym samym szkicu w dwóch kartach — nadpiszesz zmiany (last-write-wins poza lockiem DRAFT). Nie publikuj „w panice” duplikatów. |
| **Docelowo (produkt)** | Rozszerzenie locka na amend PUBLISHED — backlog code review M7 w [`.ai/TODO.md`](../../.ai/TODO.md). |
| **Film** | nie nagrany — proponowany tytuł: *„Lekarz: dokument zablokowany — co zrobić, gdy kolega ma otwarty szkic”* |
| **Powiązane** | [03-doktor.md](03-doktor.md) §2, §3 |

---

### SC-015 — Lekarz cofa publikację Befundu (revoke)

| Pole | Treść |
|------|--------|
| **Role** | Lekarz |
| **Objaw** | Opublikowano **błędny** Befund; pacjent mógł już dostać SMS. Lekarz musi **wycofać dostęp** do PDF w portalu (np. pomyłka w treści, zły pacjent). |
| **Przyczyna (techniczna)** | `POST /api/v1/medical-documents/{id}/revoke` ustawia `revoked_at` na bieżącej opublikowanej wersji. Portal pacjenta **wyklucza** wersje z `revoked_at` — po OTP pacjent nie zobaczy ani nie pobierze wycofanego pliku. |
| **Co zrobić dziś (instrukcja)** | 1) Wejdź w **szczegóły Befundu** (`/doctor/detail/…`). 2) Użyj **Cofnij publikację** (modal z potwierdzeniem). 3) Po revoke — baner w UI; wpis może wrócić do pracy (nowy szkic / poprawka). 4) **Poinformuj recepcję**, jeśli pacjent dzwoni — po revoke lista dokumentów w portalu będzie pusta dla tej wersji. 5) Po korekcie — **ponowna publikacja** (nowa wersja); rozważ `resend_sms` według procedury placówki. |
| **Czego nie robić** | Nie usuwaj wersji ręcznie w adminie. Administrator **nie** może revoke za lekarza — tylko lekarz (lub rola z uprawnieniem klinicznym wg konfiguracji). Nie zakładaj, że SMS „cofnie się” — pacjent mógł już zobaczyć powiadomienie logistyczne. |
| **Docelowo (produkt)** | Wdrożone w UI (`befund-form.js`); uwaga księgowości: revoke v1 + publish v2 może zaniżać raport — backlog M8 w [`.ai/TODO.md`](../../.ai/TODO.md). |
| **Film** | nie nagrany — proponowany tytuł: *„Lekarz: cofnięcie publikacji — pacjent nie zobaczy błędnego PDF”* |
| **Powiązane** | [03-doktor.md](03-doktor.md), [05-pacjent-wyniki.md](05-pacjent-wyniki.md) §Wycofanie publikacji |

---

### SC-016 — Autoryzacja papierowa znika po wysłaniu ankiety z tableta

| Pole | Treść |
|------|--------|
| **Role** | Admin, Manager, Recepcja |
| **Objaw** | Wykonano **T1** (autoryzacja ścieżki papierowej), ale po tym pacjent **wypełnił ankietę na tablecie** — na liście lekarza znika opcja dokumentu papierowego; w `/admin/paper-intake/` autoryzacja jest nieaktywna. |
| **Przyczyna (techniczna)** | **Auto-revoke:** wysłanie cyfrowej ankiety (`SUBMITTED`) automatycznie **unieważnia** `PaperIntakeAuthorization`. System preferuje ścieżkę **cyfrową**. |
| **Co zrobić dziś (obejście)** | 1) **Zaakceptuj ścieżkę cyfrową** — lekarz pracuje normalnie na ankiecie z tableta (zalecane). 2) Jeśli ankieta cyfrowa jest **nieważna** (np. pomyłka SC-019) — skontaktuj się z IT/adminem; **nie** planuj równolegle papier + tablet na ten sam wpis. 3) Odśwież `/doctor/` i `/admin/paper-intake/`. |
| **Czego nie robić** | Nie autoryzuj papieru „na zapas”, jeśli pacjent i tak pójdzie na tablet. Nie cofaj ankiety ręcznie w adminie bez procedury RODO. |
| **Docelowo (produkt)** | Udokumentowane w [paper_intake_flow.md](paper_intake_flow.md) — brak zmiany produktowej. |
| **Film** | nie nagrany — proponowany tytuł: *„Ścieżka papierowa: co się dzieje, gdy pacjent mimo to wypełni tablet”* |
| **Powiązane** | [04-administrator-paper-intake.md](04-administrator-paper-intake.md) §6, [paper_intake_flow.md](paper_intake_flow.md) |

---

### SC-017 — Lekarz nie widzi opcji dokumentu papierowego — brak T1

| Pole | Treść |
|------|--------|
| **Role** | Admin, Manager, Lekarz |
| **Objaw** | Pacjent **nie** wypełnił tableta; lekarz widzi komunikat **„brak ukończonej ankiety”** i **nie ma** przycisku utworzenia dokumentu papierowego na `/doctor/`. |
| **Przyczyna (techniczna)** | Brak **T1** (autoryzacji w `/admin/paper-intake/`) **albo** warunki T1 niespełnione: cyfrowa ankieta już wysłana, brak godziny wizyty, za wcześnie po godzinie wizyty (`PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT`), istnieje już dokument medyczny, wpis anulowany. |
| **Co zrobić dziś (obejście)** | 1) **Admin/Manager:** wejdź w **`/admin/paper-intake/`** → wybierz wpis → **Autoryzuj** z powodem (awaria tabletu, pacjent bez cyfryzacji). 2) Sprawdź **godzinę wizyty** na wpisie kolejki. 3) Po T1 odśwież listę lekarza — pojawi się **wyróżniona akcja** utworzenia dokumentu papierowego (T2). 4) Lekarz wykonuje T2 wg [03-doktor.md](03-doktor.md) §ścieżka papierowa. |
| **Czego nie robić** | Recepcja **nie** wykonuje T1 — tylko Admin/Manager. Nie omijaj T1 „ręcznym” tworzeniem dokumentu w adminie. |
| **Docelowo (produkt)** | Procedura kompletna w [04-administrator-paper-intake.md](04-administrator-paper-intake.md). |
| **Film** | nie nagrany — proponowany tytuł: *„Od autoryzacji papierowej do listy lekarza — krok T1 i T2”* |
| **Powiązane** | [04-administrator-paper-intake.md](04-administrator-paper-intake.md), [03-doktor.md](03-doktor.md) §2 |

---

### SC-018 — Tablet: pusta lista kolejek — nieprzypisane urządzenie

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Administrator |
| **Objaw** | Po zalogowaniu na `/tablet/` **brak kolejek** na dziś — komunikat o **nieprzypisanym tablecie** lub pusta strona główna mimo istniejących kolejek w adminie. |
| **Przyczyna (techniczna)** | Rekord **TabletDevice** nie ma przypisanej **Clinic site** — lista kolejek jest filtrowana do placówki urządzenia. Alternatywnie: brak kolejki na **dzisiejszą datę** dla tej placówki. |
| **Co zrobić dziś (obejście)** | 1) **Administrator:** **Reception → Tablet devices** — znajdź urządzenie (po pierwszym logowaniu) i ustaw **Clinic site**. 2) **Recepcja:** upewnij się, że istnieje **Daily queue** na dziś z wpisami dla tej placówki. 3) Wyloguj i zaloguj tablet ponownie. 4) Tymczasowo (awaria): recepcja może zalogować konto **Reception** na tablecie — tylko do czasu naprawy. |
| **Czego nie robić** | Nie zostawiaj konta Admin/Reception na tablecie na stałe w poczekalni. Nie wysyłaj pacjentowi linku do formularza — sesja wymaga wyboru z listy personelu. |
| **Docelowo (produkt)** | Brak — konfiguracja operacyjna. |
| **Film** | nie nagrany — proponowany tytuł: *„Tablet nie widzi pacjentów — przypisanie placówki do urządzenia”* |
| **Powiązane** | [02-tablet.md](02-tablet.md) §Wymagania, [04-administrator.md](04-administrator.md) §4 |

---

### SC-019 — Pacjent wypełnił ankietę przy niewłaściwym wpisie kolejki

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Tablet, Administrator |
| **Objaw** | Ankieta **SUBMITTED** jest przypisana do **innego** pacjenta niż ten, który faktycznie wypełniał formularz (pomyłka przy wyborze na tablecie). Lekarz otwierając „właściwego” pacjenta widzi pustą ankietę; przy „złym” — cudzą treść. Możliwy **HTTP 500** przy próbie utworzenia dokumentu (kolizja `intake_form`). |
| **Przyczyna (techniczna)** | Sesja tabletu (`TabletSession`) powiązana z **błędnym** `queue_entry`. Inwariant: `intake_form.queue_entry == session.queue_entry`. Ręczna zmiana FK w adminie bez procedury rozjechała dane (incydent prod 04.06.2026). |
| **Co zrobić dziś (obejście)** | 1) **Zatrzymaj** pracę lekarza nad oboma wpisami — **nie** publikuj Befundu na złym pacjencie. 2) **Zgłoś IT / administratorowi** — wymagane **atomowe przeniesienie** sesji + ankiety (+ ewentualny pusty DRAFT) na właściwy wpis; **nie** edytuj samodzielnie pola `queue_entry` w `PatientIntakeForm`. 3) Po naprawie — **ponowne potwierdzenie zgód** u właściwego pacjenta (RODO). 4) Operacyjnie: na tablecie **zawsze** weryfikuj kartę tożsamości na kroku 1 formularza przed przekazaniem urządzenia. |
| **Czego nie robić** | **Nigdy** nie zmieniaj ręcznie `queue_entry` ankiety w Django Admin bez procedury IT. Nie kasuj ankiety bez audytu. Nie publikuj „żeby zamknąć sprawę”. |
| **Docelowo (produkt)** | Dedykowana akcja recepcji „przepnij ankietę” + walidacja inwariantu — backlog [`.ai/TODO.md`](../../.ai/TODO.md) (linia „Pacjent wypełnił nie swoją ankietę”). |
| **Film** | nie nagrany — proponowany tytuł: *„Pomyłka na tablecie — jak rozpoznać złego pacjenta na liście lekarza”* |
| **Powiązane** | [02-tablet.md](02-tablet.md) §5.2 (karta tożsamości), [01-rejestracja.md](01-rejestracja.md) |

---

### SC-020 — Publikacja zewnętrznego PDF wyniku badania (external upload)

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Manager |
| **Objaw** | Wynik badania jest **gotowym PDF** spoza panelu Befund (lab zewnętrzny, inna placówka) — trzeba go opublikować pacjentowi z SMS, bez wypełniania formularza skórnego przez lekarza. |
| **Przyczyna (techniczna)** | Moduł **EXTERNAL_UPLOAD**: hub `/admin/external-upload/`, upload do `/incoming/external-upload/{queue_entry_id}/`, wybór załącznika, publikacja z potwierdzeniem tożsamości pacjenta. Wymaga ankiety `SUBMITTED`/`REOPENED` i numeru telefonu. |
| **Co zrobić dziś (instrukcja)** | 1) Dashboard recepcji → skrót **Zewnętrzne badanie** lub `/admin/external-upload/`. 2) Wybierz wpis kolejki (filtr statusu ankiety). 3) **Upload PDF** (max 250 MB, tylko PDF). 4) **Wybierz załącznik**, podgląd, **drugie potwierdzenie** (checkbox tożsamości). 5) **Publikuj** z `publish_locale` (DE/EN/PL). 6) Śledź outbox jak przy Befundzie. Przy korekcie: rewizja + opcjonalnie **`resend_sms`**. |
| **Czego nie robić** | Nie wrzucaj tego pliku do „gołego” `/incoming/` — to ścieżka labu dla Befundu ([07-wgranie-zewnetrznego-badania.md](07-wgranie-zewnetrznego-badania.md)). Nie publikuj bez weryfikacji tożsamości pacjenta przy recepcji. External upload **nie wchodzi** w raport księgowości v1 (SC-004). |
| **Docelowo (produkt)** | MVP wdrożone; observability i progress bar — backlog planu external upload. |
| **Film** | nie nagrany — proponowany tytuł: *„Recepcja: wgranie i publikacja zewnętrznego PDF wyniku”* |
| **Powiązane** | [07-wgranie-zewnetrznego-badania.md](07-wgranie-zewnetrznego-badania.md), [01-rejestracja.md](01-rejestracja.md) §7 |

---

### SC-021 — Lekarz: komunikat „brak ukończonej ankiety”

| Pole | Treść |
|------|--------|
| **Role** | Lekarz, Recepcja |
| **Objaw** | Lekarz klika **Otwórz** — komunikat, że **ankieta nie została ukończona**; brak możliwości utworzenia dokumentu cyfrowego. |
| **Przyczyna (techniczna)** | `PatientIntakeForm` nie ma statusu `SUBMITTED`/`REOPENED` — pacjent nie wysłał formularza, sesja tabletu w toku, anulowany wpis, albo oczekiwana ścieżka papierowa (SC-017). |
| **Co zrobić dziś (obejście)** | 1) **Recepcja / tablet:** upewnij się, że pacjent **dokończył i wysłał** formularz (ekran „formularz wysłany”). 2) Sprawdź **status wpisu kolejki** — czy nie `CANCELLED`. 3) Jeśli tablet niemożliwy → **ścieżka papierowa** SC-017 (T1 + T2). 4) Odśwież listę lekarza po wysłaniu ankiety. |
| **Czego nie robić** | Nie twórz dokumentu medycznego ręcznie w adminie bez procedury. Nie otwieraj starego linku `/doctor/open/{uuid}/` dla anulowanego wpisu. |
| **Docelowo (produkt)** | Brak — operacja standardowa. |
| **Film** | nie nagrany — proponowany tytuł: *„Lekarz nie może otworzyć pacjenta — ankietę trzeba najpierw wysłać na tablecie”* |
| **Powiązane** | [03-doktor.md](03-doktor.md), [02-tablet.md](02-tablet.md) §5.3, SC-017 |

---

### SC-022 — Pacjent: pusta lista dokumentów lub wycofana publikacja

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Lekarz |
| **Objaw** | Pacjent przeszedł OTP, ale na **`/documents/`** lista jest **pusta** — albo wcześniej widział plik, a teraz zniknął. |
| **Przyczyna (techniczna)** | (a) Befund **jeszcze nie opublikowany** lub outbox w toku; (b) lekarz wykonał **revoke** (SC-015); (c) opóźnienie pipeline (~15 min max przy schedulerze); (d) pacjent zalogował się na **zły rekord** (wspólny telefon, SC-009). |
| **Co zrobić dziś (obejście)** | 1) W panelu lekarza sprawdź **status publikacji** i kolumny PDF/HiDrive/SMS. 2) Jeśli **Opublikowany** i outbox OK — sprawdź, czy nie było **revoke**. 3) Jeśli w toku — poproś pacjenta o cierpliwość 15–30 min. 4) Przy wspólnym numerze — zweryfikuj **datę urodzenia** i ewentualnie **nazwisko** pacjenta. 5) Jeśli revoke był słuszny — poczekaj na **ponowną publikację** po korekcie. |
| **Czego nie robić** | Nie wysyłaj PDF mailem bez procedury RODO. Nie proś o republikację bez ustalenia przyczyny revoke. |
| **Docelowo (produkt)** | Lepszy status „w przygotowaniu” w portalu pacjenta — backlog produktowy. |
| **Film** | nie nagrany — proponowany tytuł: *„Pacjent: dlaczego lista wyników jest pusta po kodzie SMS”* |
| **Powiązane** | [05-pacjent-wyniki.md](05-pacjent-wyniki.md), SC-015, SC-013 |

---

### SC-023 — Pacjent: minęło okno 60 dni dostępu do PDF

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Manager |
| **Objaw** | Pacjent loguje się poprawnie, widzi dokument na liście lub próbuje pobrać — błąd **niedostępny** / pusty plik; minęło **ponad 60 dni** od publikacji (`PDF_RETENTION_DAYS=60`). |
| **Przyczyna (techniczna)** | Lokalna kopia PDF na serwerze aplikacji jest **usuwana** po 60 dniach, gdy `hidrive_sent` i `sms_sent` są spełnione. Portal serwuje plik z lokalnego storage / HiDrive — po retencji lokalnej pobranie przez portal może być niemożliwe. Archiwum **HiDrive** (`/patients/{uuid}/`) nadal może istnieć. |
| **Co zrobić dziś (obejście)** | 1) Potwierdź datę publikacji w systemie. 2) **Manager / IT:** pobierz kopię z **HiDrive** `/patients/` lub procedury archiwum placówki. 3) Udostępnij pacjentowi zgodnie z **procedurą RODO** placówki (nie ad hoc mailem). 4) Backlog: instrukcja awaryjna Google Drive + SMS z hasłem ([`.ai/TODO.md`](../../.ai/TODO.md)). |
| **Czego nie robić** | Nie obiecuj stałego dostępu przez portal powyżej okna retencji. Nie używaj prywatnego konta Google/Dropbox. |
| **Docelowo (produkt)** | Runbook `EMERGENCY_GOOGLE_DRIVE_RESULT.md` — backlog. |
| **Film** | nie nagrany — proponowany tytuł: *„Pacjent prosi o wynik po 2 miesiącach — skąd wziąć kopię z archiwum”* |
| **Powiązane** | [05-pacjent-wyniki.md](05-pacjent-wyniki.md) §Okno dostępu |

---

### SC-024 — Niskie saldo SMSAPI / awaria wysyłki OTP

| Pole | Treść |
|------|--------|
| **Role** | Administrator, Recepcja |
| **Objaw** | **Wielu** pacjentów naraz nie dostaje OTP; w logach/Sentry: `SendException: account balance is low` lub wzrost audytu `PATIENT_RESULTS_OTP_REQUEST` z `outcome=sms_failed`. Outbox `SMS_SEND` też może padać (SC-006). |
| **Przyczyna (techniczna)** | **Wyczerpane saldo** konta SMSApi lub awaria dostawcy. Fix w kodzie zwraca kontrolowany błąd zamiast HTTP 500, ale **bez alertu** recepcja dowiaduje się od pacjentów. |
| **Co zrobić dziś (obejście)** | 1) **Administrator:** doładuj konto SMSApi, sprawdź panel dostawcy. 2) Po doładowaniu — pacjenci mogą **ponownie prosić o OTP**; recepcja może resetować zdarzenia outbox SMS (SC-006). 3) Poinformuj recepcję o incydencie — przygotuj procedurę tłumaczenia dla dzwoniących pacjentów. 4) Eskaluj do IT weryfikację alertów (backlog monitoringu w [`.ai/TODO.md`](../../.ai/TODO.md)). |
| **Czego nie robić** | Nie ignoruj pierwszego zgłoszenia — może dotyczyć wszystkich SMS. Nie wysyłaj kodów OTP ręcznie SMS-em z prywatnego telefonu. |
| **Docelowo (produkt)** | Alert operacyjny + baner na dashboardzie recepcji; runbook `SMS_DELIVERY_FAILURE.md`. |
| **Film** | nie nagrany — proponowany tytuł: *„Awaria SMS — co robi recepcja, gdy nikt nie dostaje kodów”* |
| **Powiązane** | SC-006, SC-010, [INTEGRATION_ERROR.md](../runbooks/INTEGRATION_ERROR.md) |

---

### SC-025 — Korekta danych pacjenta — skutki dla portalu i HiDrive

| Pole | Treść |
|------|--------|
| **Role** | Recepcja |
| **Objaw** | Po zmianie **imienia, nazwiska, telefonu lub daty urodzenia** pacjent nie loguje się do portalu **albo** lekarz traci dopasowanie PDF z laboratorium. |
| **Przyczyna (techniczna)** | Portal: login = telefon + DOB (± nazwisko). HiDrive: klucze dopasowania nazw plików przeliczane z pól pacjenta. Import Doctolib: dopasowanie po **czwórce** tożsamości. |
| **Co zrobić dziś (instrukcja)** | 1) Edycja wg [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md). 2) **Po zapisie:** poinformuj pacjenta o **nowym telefonie i DOB** (oba naraz, jeśli zmienione oba). 3) **HiDrive:** popraw nazwę pliku labu lub wgraj ponownie wg [hidrive_incoming_reception.md](hidrive_incoming_reception.md). 4) Przy wspólnym numerze — upewnij się, że edytowałeś **właściwy** rekord (Krok 3 w instrukcji 06). |
| **Czego nie robić** | Nie zmieniaj danych „dla wygody portalu” bez weryfikacji tożsamości. Nie zostawiaj starego pliku PDF pod starą nazwiskową konwencją. |
| **Docelowo (produkt)** | Brak — procedura operacyjna. |
| **Film** | nie nagrany — proponowany tytuł: *„Zmiana nazwiska pacjenta — portal, SMS i plik z laboratorium”* |
| **Powiązane** | [06-zmiana-danych-pacjenta.md](06-zmiana-danych-pacjenta.md), SC-008, SC-011 |

---

### SC-026 — Outbox `DEAD_LETTER` — ręczne odblokowanie zdarzenia

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Administrator |
| **Objaw** | Zdarzenie outbox ma status **`Dead letter`** po **3 nieudanych próbach** (`max_retries=3`). Pipeline **nie retryuje** automatycznie. Kolumny PDF/HiDrive/SMS u lekarza utknęły w błędzie. |
| **Przyczyna (techniczna)** | Trwały błąd (zły numer, trwała awaria HiDrive, uszkodzony payload) lub seria chwilowych błędów 5xx. Metryka backlog age **nie** obejmuje DEAD_LETTER — alert mógł nie wystąpić. |
| **Co zrobić dziś (obejście)** | 1) **`/admin/outbox/outboxevent/`** — znajdź zdarzenie, przeczytaj **`error_message`**. 2) **Usuń przyczynę** (np. popraw telefon SC-008, token HiDrive SC-013). 3) Ustaw status z **`Dead letter`** na **`Oczekuje`**, wyczyść `processed_at` jeśli trzeba; **Ponów** z dashboardu. 4) `enqueue_tasks` po naprawie. 5) Przy duplikacie SMS po deployu — uwaga runbook H8 ([`.ai/TODO.md`](../../.ai/TODO.md)). |
| **Czego nie robić** | Nie ustawiaj DEAD_LETTER na PROCESSED bez realnego sukcesu. Nie kasuj zdarzeń outbox bez IT. |
| **Docelowo (produkt)** | Alert `OutboxDeadLetterPresent` — backlog observability. |
| **Film** | nie nagrany — proponowany tytuł: *„Dead letter w outbox — kiedy ręcznie cofnąć status na Oczekuje”* |
| **Powiązane** | [OUTBOX_BACKLOG_AGE.md](../runbooks/OUTBOX_BACKLOG_AGE.md), SC-006, SC-013 |

---

### SC-027 — Baner awarii HiDrive na dashboardzie recepcji

| Pole | Treść |
|------|--------|
| **Role** | Recepcja, Administrator |
| **Objaw** | Na **`/admin/reception-dashboard/`** czerwony **baner awarii HiDrive**; sekcja **Brakujące wyniki HiDrive** pusta lub nieaktualna; lekarze masowo zgłaszają blokadę Befundu. |
| **Przyczyna (techniczna)** | Timeout 8 s listowania `/incoming/` — chwilowa niedostępność Strato HiDrive, wygasły refresh token, lub błąd sieci VPS → HiDrive. Reszta dashboardu (importy, outbox) **działa**. |
| **Co zrobić dziś (obejście)** | 1) **Nie** zakładaj, że „wszyscy mają pliki” — lista brakujących wyników jest **niewiarygodna** przy banerze. 2) **Administrator:** status Strato/HiDrive, token OAuth ([INTEGRATION_ERROR.md](../runbooks/INTEGRATION_ERROR.md)), restart `scheduler`/`web`. 3) Po powrocie HiDrive — odśwież dashboard; uzupełnij brakujące PDF **proaktywnie** (SC-005). 4) Recepcja: informuj lekarzy o znanym incydencie. |
| **Czego nie robić** | Nie publikuj external upload w szczycie awarii HiDrive (upload też padnie). Nie usuwaj plików z `/incoming/` „dla porządku” w trakcie awarii. |
| **Docelowo (produkt)** | Alert operacyjny HiDrive ≥24 h — observability plan. |
| **Film** | nie nagrany — proponowany tytuł: *„Czerwony baner HiDrive — co recepcja robi inaczej tego dnia”* |
| **Powiązane** | [01-rejestracja.md](01-rejestracja.md) §2, SC-005, [INTEGRATION_ERROR.md](../runbooks/INTEGRATION_ERROR.md) |

---

## Backlog filmów (propozycje)

| Priorytet | SC | Czas ~ | Odbiorca | Uwagi |
|-----------|-----|--------|----------|--------|
| Wysoki | SC-001 | 2–3 min | Recepcja + lekarz | |
| Wysoki | SC-002 | 2 min | Admin / recepcja | |
| Wysoki | SC-006 | 2–3 min | Recepcja / admin | SMS po publikacji Befundu |
| Wysoki | SC-007 | 3–4 min | Recepcja | **Nagrany:** `reception/import-troubleshooting.webm` |
| Wysoki | SC-008 | 2 min | Recepcja | Portal — błędne dane logowania |
| Wysoki | SC-010 | 2–3 min | Recepcja / admin | OTP portalu ≠ SC-006 |
| Wysoki | SC-019 | 2–3 min | Tablet + recepcja | Incydent prod — rozpoznanie pomyłki |
| Średni | SC-003 | 2 min | Lekarz | |
| Średni | SC-004 | 2–3 min | Księgowość / manager | |
| Średni | SC-005 | 2–3 min | Recepcja | Brak PDF labu (ogólny) |
| Średni | SC-011 | 2 min | Recepcja | Homonim — DOB w nazwie pliku |
| Średni | SC-013 | 2 min | Recepcja | Outbox PDF/HiDrive |
| Średni | SC-015 | 2 min | Lekarz | Revoke publikacji |
| Średni | SC-017 | 3 min | Admin/Manager + lekarz | T1 → T2 papier |
| Średni | SC-020 | 3–4 min | Recepcja | External upload end-to-end |
| Niski | SC-009 | 2 min | Recepcja / pacjent | Wspólny numer rodzinny |
| Niski | SC-012 | 1–2 min | Recepcja | `rejected_` prefix |
| Niski | SC-014 | 1–2 min | Lekarz | Blokada edycji |
| Niski | SC-016 | 2 min | Admin/Manager | Auto-revoke papieru |
| Niski | SC-018 | 2 min | Admin | Tablet nieprzypisany |
| Niski | SC-021–SC-027 | 1–3 min | Różne | FAQ uzupełniające |

Po nagraniu: plik w `docs/manual/assets/videos/scenariusze/` (np. `sc-008-portal-login.webm`), aktualizacja kolumny **Film** w tabeli indeksu i ewentualny link z rozdziału manuala. SC-007 pozostaje w `reception/import-troubleshooting.webm` (osobny skrypt nagrywania).
