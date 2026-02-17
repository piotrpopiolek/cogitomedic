# Dokument wymagań produktu (PRD) - Cogitomedica Digital Consents

## 1. Przegląd produktu

Cogitomedica Digital Consents to aplikacja internetowa mająca na celu cyfryzację procesu przyjmowania pacjentów, podpisywania zgód oraz dokumentacji medycznej w placówce medycznej. System ma zastąpić obieg papierowy rozwiązaniem tabletowym dla pacjentów oraz panelem zarządzania dla personelu.

Projekt realizowany jest w trzech fazach:
- Faza 1: Obsługa tabletów, cyfrowe zgody, ankieta anamnestyczna (Anamnesebogen), schemat ciała i podpis elektroniczny pacjenta. Zarządzanie kolejką (Poczekalnia) odbywa się ręcznie lub przez import.
- Faza 2: Panel lekarza do uzupełniania danych medycznych, zatwierdzanie dokumentów oraz automatyzacja wysyłki (zapis do archiwum i powiadomienie SMS).
- Faza 3: Usprawnienie procesu codziennego importu plików eksportowanych z Doctolib oraz integracja z API HiDrive (docelowe API archiwizacji).

Głównym celem jest usprawnienie pracy recepcji i lekarzy, zapewnienie bezpieczeństwa danych oraz automatyzacja archiwizacji dokumentacji przy zachowaniu zgodności z wymogami operacyjnymi placówki. Językami interfejsu portalu są angielski i niemiecki (użytkownik może wybrać preferowany język).

### 1.1. Aktualna baza technologiczna backendu
- Backend jest utrzymywany na **Django 6.0.x**.
- Zadania asynchroniczne są definiowane i uruchamiane przez natywny framework **Django Tasks** (`django.tasks`), a nie przez `django-cron`.
- Kontrakty i statusy procesu asynchronicznego (Outbox) pozostają bez zmian względem wymagań domenowych.

## 2. Problem użytkownika

Obecny proces obsługi pacjenta opiera się na dokumentacji papierowej, co generuje następujące problemy:
- Czasochłonne ręczne wprowadzanie danych pacjentów do systemu.
- Ryzyko błędów przy przepisywaniu danych oraz ryzyko zgubienia dokumentów papierowych.
- Trudności w archiwizacji i wyszukiwaniu historycznych zgód.
- Brak natychmiastowej dostępności cyfrowej kopii dokumentu dla pacjenta i lekarza.
- Konieczność fizycznego przechowywania dużej ilości papieru.
- Skomplikowany proces udostępniania wyników i dokumentacji pacjentowi po wizycie.

Rozwiązanie ma wyeliminować te niedogodności poprzez wprowadzenie w pełni cyfrowego obiegu, od momentu rejestracji, przez podpis na tablecie, aż po bezpieczną archiwizację w chmurze i powiadomienie pacjenta.

## 3. Wymagania funkcjonalne

### 3.1. Zarządzanie pacjentami i Poczekalnia
- System umożliwia ręczne dodawanie pacjenta do listy dziennej (Poczekalni).
- Obsługa importu listy pacjentów z pliku (format zdefiniowany: imię, nazwisko, data urodzenia, telefon, e-mail).
- W Fazie 3 lista dzienna jest uzupełniana codziennym importem plików eksportowanych z Doctolib (bez bezpośredniej integracji API).
- Generowanie unikalnego linku z jednorazowym tokenem dla pacjenta w celu uruchomienia formularza na tablecie.
- Dopuszczony jest tryb tymczasowy rekordu pacjenta bez `Doctolib Patient ID` wyłącznie dla ręcznego dodania; system musi automatycznie wygenerować alert dla administratora o konieczności pilnego uzupełnienia identyfikatora.
- System dopuszcza więcej niż jedną wizytę tego samego pacjenta tego samego dnia w tym samym gabinecie (osobne wpisy kolejki/wizyty).

### 3.2. Interfejs Pacjenta (Tablet)
- Aplikacja dostosowana do obsługi dotykowej na 4 dedykowanych tabletach.
- Formularz zawiera sekcje: Dane osobowe (tylko do odczytu/weryfikacji), Ankieta anamnestyczna (Anamnesebogen), Zgody (checkboxy), Schemat ciała (interaktywne zaznaczanie), Podpis (canvas).
- Pacjent może wypełniać ustrukturyzowaną ankietę anamnestyczną (pytania jednokrotnego wyboru i wielokrotnego wyboru, bez swobodnego opisu medycznego).
- Dla pytania o lokalizację nowych zmian system wspiera warianty: wybór predefiniowanych obszarów ciała, oznaczenie na schemacie ciała oraz opcjonalne pole "Inna lokalizacja".
- Interfejs dostępny w języku angielskim lub niemieckim (wybór zgodnie z preferencją użytkownika lub ustawieniem sesji/urządzenia).

### 3.3. Interfejs Lekarza i Personelu
- Podgląd uzupełnionych formularzy pacjentów.
- Formularz medyczny dla lekarza (sztywna struktura pól w kodzie: checkboxy, listy rozwijane, pola tekstowe).
- **Opis lekarski (Befund) – zasada „baza, nie klatka”:** To, co system przygotowuje (np. teksty z checkboxów), ma być **bazą wyjściową**, a nie jedynym, sztywnym tekstem. Lekarz musi móc dopasować język i styl opisu do siebie. System działa tak, że lekarz wybiera opcje (np. checkboxy), a system generuje z tego gotowy tekst – **który lekarz może i powinien móc edytować przed zatwierdzeniem**. Lekarz ma swobodę dopisywania własnych tekstów (np. własne szablony, wolne pole). Nie zamykamy lekarzy w jednym, sztywnym tekście.
- Struktura Befund obejmuje co najmniej: zakres badania, typ skóry Fitzpatrick, ocenę globalną, listę zmian (Läsionen), cechy dermatoskopowe per zmiana, ocenę kliniczno-dermatoskopową per zmiana, ocenę ryzyka złośliwości per zmiana, rekomendacje oraz końcową ocenę lekarską.
- System generuje tekst automatycznie na dwóch poziomach: (1) tekst per zmiana, (2) podsumowanie zbiorcze; oba teksty są edytowalne przed publikacją.
- Możliwość zapisu dokumentu jako Szkic lub Opublikowany.
- Opcja edycji opublikowanego dokumentu i ponownej wysyłki (nadpisanie w archiwum).

### 3.4. Przetwarzanie i Archiwizacja (Backend)
- Generowanie dokumentów PDF na podstawie danych z formularzy.
- **Idempotentność publikacji:** Serwer przed utworzeniem nowej wersji publikowanej i wpisów outbox sprawdza, czy dla danego dokumentu nie ma już publikacji w toku (wersja w trakcie generowania PDF / uploadu); w takim przypadku zwraca sukces bez duplikowania zadań. Dopuszczalne jest uzupełnienie o klucz idempotentności z klienta (`publish_request_id`).
- Mechanizm Transactional Outbox do obsługi procesów asynchronicznych.
- Mockowanie systemu plików HiDrive (Faza 1-2) z zachowaniem docelowej struktury katalogów.
- Integracja z API HiDrive (Faza 3).
- Integracja z SMSApi do powiadamiania pacjentów o dostępności dokumentu.
- Polityka retencji: automatyczne usuwanie plików PDF z serwera aplikacji po 30 dniach, pod warunkiem potwierdzonego zapisu w HiDrive i wysłania SMS.

### 3.5. Observability i gotowość operacyjna (wymaganie obowiązkowe)
- System musi emitować metryki techniczne i operacyjne (nie tylko logi), minimum:
  - Outbox: `pending_count`, `failed_count`, `dead_letter_count`, `oldest_pending_age_seconds`, `processing_latency_p95/p99`.
  - Integracje: skuteczność `HiDrive` i `SMS` (success ratio), liczba błędów per provider i per typ błędu.
  - Import: liczba importów udanych/nieudanych, `row_error_rate`, czas przetwarzania importu.
  - Dokumenty: czas od publikacji do `hidrive_sent=true`, czas od publikacji do `sms_sent=true`.
- Muszą istnieć dashboardy operacyjne:
  - Dashboard recepcji (status importu, zaległe dokumenty, awarie krytyczne).
  - Dashboard utrzymaniowy (SLO/SLI, retry, dead letter, trend 24h/7d).
- Musi istnieć alerting 24/7 z progami i eskalacją:
  - Alert krytyczny: `oldest_pending_age_seconds > 900` w godzinach pracy.
  - Alert krytyczny: `failed_count > 0` przez ponad 10 min dla `HIDRIVE_UPLOAD` lub `SMS_SEND`.
  - Alert ostrzegawczy: skuteczność SMS lub HiDrive poniżej 98% w oknie 1h.
- Każdy alert ma mieć runbook z instrukcją diagnostyki i obejścia awaryjnego.
- Alerting i runbook są częścią Definition of Done dla funkcji, które modyfikują outbox/import/integracje.

## 4. Granice produktu

### W zakresie (In-Scope)
- Moduł recepcji do zarządzania listą dzienną (CRUD + Import).
- Aplikacja webowa dla pacjenta (RWD/Tablet) do wypełnienia ankiety anamnestycznej, podpisywania zgód i podpisu elektronicznego.
- Moduł lekarza do uzupełniania części medycznej.
- Generowanie plików PDF z podpisem i schematem ciała.
- Mock i późniejsza integracja z HiDrive.
- Powiadomienia SMS (link do pobrania).
- Logowanie zdarzeń (OpenTelemetry).
- Języki interfejsu: angielski i niemiecki.

### Poza zakresem (Out-of-Scope)
- Zaawansowany system wersjonowania treści zgód w panelu administracyjnym (zmiany wymagają ingerencji deweloperskiej/konfiguracyjnej).
- Swobodny opis medyczny (narracyjny) tworzony przez pacjenta bez struktury pytań.
- Skomplikowane raportowanie biznesowe (BI).
- Bezpośrednia integracja API z Doctolib.
- Integracja z innymi systemami niż HiDrive i SMSApi.

## 5. Historyjki użytkowników

### Uwierzytelnianie i Dostęp
ID: US-001
Tytuł: Logowanie personelu
Opis: Jako pracownik recepcji lub lekarz, chcę bezpiecznie zalogować się do systemu za pomocą loginu i hasła, aby uzyskać dostęp do danych pacjentów.
Kryteria akceptacji:
- System wymaga podania loginu i hasła.
- Błędne logowanie wyświetla ogólny komunikat błędu.
- Sesja wygasa po określonym czasie bezczynności.
- Dostęp jest ograniczony do zdefiniowanych ról (Recepcja, Lekarz, Administrator).

### Zarządzanie Listą Dzienną (Recepcja)
ID: US-002
Tytuł: Ręczne dodawanie pacjenta
Opis: Jako recepcjonista, chcę ręcznie dodać pacjenta do listy dziennej, wprowadzając jego podstawowe dane, aby umożliwić mu wypełnienie formularza.
Kryteria akceptacji:
- Formularz wymaga podania: imienia, nazwiska, daty urodzenia, telefonu, adresu e-mail.
- System waliduje poprawność adresu e-mail i numeru telefonu.
- Nowy pacjent pojawia się na liście w widoku Poczekalnia.
- Jeśli rekord tworzony jest bez `Doctolib Patient ID`, otrzymuje status tymczasowy i automatycznie tworzony jest alert dla administratora.

ID: US-003
Tytuł: Import pacjentów
Opis: Jako recepcjonista, chcę zaimportować listę pacjentów z pliku, aby przyspieszyć tworzenie listy dziennej.
Kryteria akceptacji:
- System przyjmuje plik w formacie .xlsx lub .csv.
- System mapuje kolumny zgodnie ze zdefiniowanym szablonem.
- `Doctolib Patient ID` jest polem wymaganym dla każdego rekordu importowanego.
- W przypadku błędów w pliku, import jest przerywany lub błędne wiersze są raportowane.
- Zaimportowani pacjenci są widoczni w Poczekalni.

ID: US-004
Tytuł: Uruchomienie formularza na tablecie
Opis: Jako recepcjonista, chcę wygenerować i otworzyć unikalny link dla pacjenta na tablecie, aby mógł on rozpocząć proces podpisywania.
Kryteria akceptacji:
- Kliknięcie przycisku przy pacjencie generuje unikalny URL z tokenem.
- Link otwiera formularz w trybie pacjenta (bez menu nawigacyjnego personelu).
- System działa w modelu `latest-wins`: wygenerowanie nowego linku dla tego samego wpisu kolejki unieważnia poprzedni link.
- Token jest akceptowany tylko gdy jednocześnie: jest aktywną sesją wpisu kolejki, nie został zużyty (`consumed_at IS NULL`) i nie wygasł (`expires_at > now()`).
- Po pierwszym skutecznym zapisie formularza token traci ważność.

### Proces Pacjenta (Tablet)
ID: US-005
Tytuł: Akceptacja zgód
Opis: Jako pacjent, chcę zapoznać się z treścią zgód i zaakceptować je za pomocą checkboxów, aby wyrazić zgodę na procedury.
Kryteria akceptacji:
- Lista zgód jest wyświetlana czytelnie na tablecie.
- Wymagane zgody są oznaczone i blokują przejście dalej, jeśli nie są zaznaczone.
- Interfejs jest dostępny w języku angielskim lub niemieckim.

ID: US-006
Tytuł: Oznaczenie schematu ciała
Opis: Jako pacjent, chcę zaznaczyć na schemacie ciała miejsca bólu lub dolegliwości, aby lekarz wiedział, gdzie występuje problem.
Kryteria akceptacji:
- Wyświetlany jest schemat sylwetki (przód i tył).
- Dotknięcie ekranu nanosi znacznik w wybranym miejscu.
- Możliwość cofnięcia/usunięcia znacznika.

ID: US-007
Tytuł: Podpis elektroniczny
Opis: Jako pacjent, chcę złożyć odręczny podpis na ekranie tabletu, aby autoryzować dokument.
Kryteria akceptacji:
- Pole podpisu obsługuje wprowadzanie dotykowe (rysik/palec).
- Wymagane jest złożenie podpisu przed finalizacją.
- Po zatwierdzeniu formularz jest zapisywany, a token traci ważność (nie można cofnąć się do edycji).

### Proces Lekarza
ID: US-008
Tytuł: Wypełnianie części medycznej
Opis: Jako lekarz, chcę uzupełnić formularz o dane medyczne (rozpoznanie, procedura) dla pacjenta, który zakończył proces na tablecie.
Kryteria akceptacji:
- Dostęp do formularza pacjenta z widocznymi zgodami i schematem ciała.
- Sekcja medyczna zawiera zdefiniowane pola (listy, checkboxy, pola tekstowe).
- Sekcja medyczna obsługuje model zmian skórnych (lista zmian 1..N) i dane per zmiana: cechy dermatoskopowe, ocena kliniczna oraz ryzyko złośliwości.
- **Generowanie tekstu z checkboxów:** Wybór opcji (checkboxy/listy) powoduje wygenerowanie przez system gotowego tekstu opisu (np. Textbausteine); ten wygenerowany tekst jest **edytowalny** – lekarz może go poprawić, skrócić lub rozwinąć przed zatwierdzeniem.
- **Generowanie zbiorcze:** Po opisie poszczególnych zmian system generuje podsumowanie globalne Befund (edytowalne).
- **Swoboda dopisywania:** Lekarz może dopisywać własne teksty (pole wolne, własne szablony), a nie tylko wybierać z gotowych opcji. Język i styl opisu zależą od lekarza.
- Walidacja wymaganych pól medycznych przed publikacją.

ID: US-009
Tytuł: Zapis szkicu i publikacja
Opis: Jako lekarz, chcę mieć możliwość zapisu pracy jako szkic lub ostatecznej publikacji dokumentu.
Kryteria akceptacji:
- Opcja Zapisz jako szkic pozwala na późniejszą edycję i nie uruchamia wysyłki.
- Opcja Zatwierdź i wyślij blokuje edycję, zmienia status na Opublikowany i kolejkuje zadanie generowania PDF w tle (asynchronicznie).
- UI lekarza nie jest blokowane przez proces generowania PDF, uploadu czy wysyłki SMS.
- Status generowania dokumentu jest widoczny w systemie (np. "Przetwarzanie...").
- Akcja "Zatwierdź i wyślij" jest idempotentna: wielokrotne kliknięcie dla tego samego dokumentu nie tworzy wielu publikacji ani wielu łańcuchów zadań.
- **Mechanizm po stronie serwera:** Przed utworzeniem nowej publikacji serwis sprawdza, czy dla danego dokumentu medycznego istnieje już wersja w stanie „publikacja w toku” (np. wersja ze statusem PUBLISHED, dla której w outbox istnieje zdarzenie `GENERATE_PDF` w statusie PENDING lub PROCESSING). W takim przypadku żądanie publikacji zwraca sukces bez tworzenia nowej wersji ani nowych wpisów outbox (idempotentna odpowiedź). Alternatywnie lub uzupełniająco: żądanie może przekazywać klucz idempotentności (np. `publish_request_id` z frontu); serwer traktuje ten sam klucz dla tego samego dokumentu jako powtórzenie i nie tworzy duplikatów.

ID: US-010
Tytuł: Edycja opublikowanego dokumentu
Opis: Jako lekarz, chcę poprawić błąd w już opublikowanym dokumencie i wysłać go ponownie.
Kryteria akceptacji:
- Możliwość edycji zatwierdzonego formularza.
- Ponowne zatwierdzenie tworzy nową wersję PDF.
- Nowa wersja nadpisuje plik w HiDrive (zachowanie tej samej ścieżki/nazwy).
- System pozwala zdecydować, czy ponownie wysłać SMS do pacjenta.

ID: US-019
Tytuł: Własne szablony tekstu lekarza (DE/EN)
Opis: Jako lekarz, chcę tworzyć i używać własnych szablonów opisu, aby zachować swój styl dokumentacji.
Kryteria akceptacji:
- Lekarz może utworzyć, edytować, aktywować/dezaktywować własny szablon tekstu (co najmniej dla języka niemieckiego i angielskiego).
- Przy generowaniu tekstu z checkboxów lekarz może wskazać szablon bazowy.
- System zapisuje zarówno tekst wygenerowany automatycznie, jak i tekst końcowy po edycji lekarza.
- Zmiana szablonu po publikacji nie modyfikuje historycznych wersji dokumentu.
- Szablony globalne (kliniki) i prywatne (per lekarz) są rozróżnione w uprawnieniach.

### System i Backend
ID: US-011
Tytuł: Codzienny import plików z listą wizyt (Faza 3)
Opis: System codziennie importuje listę wizyt z plików eksportowanych z Doctolib, aby wyeliminować ręczne wprowadzanie danych.
Kryteria akceptacji:
- System przyjmuje plik .xlsx lub .csv zgodny z ustalonym szablonem eksportu.
- Import może być uruchamiany ręcznie przez recepcję oraz automatycznie według harmonogramu dziennego.
- `Doctolib Patient ID` jest polem obowiązkowym i podstawą mapowania tożsamości pacjenta.
- Dane (imię, nazwisko, data urodzenia, kontakt) są mapowane do struktury pacjenta jako dane uzupełniające.
- Błędy importu są raportowane na poziomie wiersza.

ID: US-012
Tytuł: Przetwarzanie Outbox (HiDrive i SMS)
Opis: System automatycznie przetwarza kolejkę zadań, aby zapisać pliki w chmurze i powiadomić pacjenta.
Kryteria akceptacji:
- Cron uruchamia przetwarzanie tabeli Outbox.
- Krok 1: Generowanie pliku PDF (operacja CPU-bound) realizowane przez worker zasilany przez Django Tasks, a nie w żądaniu HTTP.
- Krok 2: Zapis pliku PDF do HiDrive (lub Mocka w F. 1-2) w ustalonej strukturze folderów.
- Krok 3: Po sukcesie Kroku 2, wysyłka SMS z linkiem do pacjenta.
- W przypadku błędu, zadanie otrzymuje status błędu i jest ponawiane w kolejnym cyklu (zgodnie z polityką retry).
- Dokument ma status Opublikowany, ale flagi hidrive_sent/sms_sent odzwierciedlają stan faktyczny.

ID: US-013
Tytuł: Polityka retencji (30 dni)
Opis: System automatycznie usuwa pliki PDF z lokalnego serwera po 30 dniach, aby oszczędzać miejsce i dbać o bezpieczeństwo, ale tylko jeśli są bezpieczne w archiwum.
Kryteria akceptacji:
- Cron sprawdza dokumenty starsze niż 30 dni od publikacji.
- Usunięcie następuje TYLKO GDY: flaga zapisu do HiDrive == true ORAZ flaga wysyłki SMS == true.
- Zdarzenie usunięcia jest logowane w systemie.

ID: US-014
Tytuł: Monitoring outbox i integracji
Opis: Jako zespół utrzymania, chcę widzieć metryki i alerty dla outbox oraz integracji, aby wykrywać awarie zanim zgłosi je recepcja.
Kryteria akceptacji:
- Dostępne są dwa dashboardy:
  - prosty dashboard recepcji/lekarza (status dokumentów i błędów wymagających interwencji),
  - zaawansowany dashboard administracyjno-utrzymaniowy (metryki p95/p99, success ratio, queue depth, oldest pending).
- Alerty krytyczne/ostrzegawcze działają zgodnie z progami z sekcji 3.5.
- Do każdego alertu istnieje runbook i osoba dyżurna wie, jak wykonać procedurę.
- Jeśli generowanie PDF (`medical_document_version`) wejdzie w stan `FAILED` lub zdarzenie outbox wejdzie w stan `DEAD_LETTER`, na dashboardzie recepcji/lekarza i dashboardzie administracyjnym pojawia się wyraźne powiadomienie (czerwona lampka/toast) o błędzie przetwarzania.

ID: US-015
Tytuł: Idempotentny import wieloźródłowy
Opis: Jako recepcja, chcę aby ręczne dodanie, import pliku i autoimport nie tworzyły duplikatów wizyt i pacjentów.
Kryteria akceptacji:
- Wszystkie ścieżki wejścia korzystają z jednej warstwy ingestii i tych samych walidacji.
- Import jest idempotentny na podstawie klucza zewnętrznego wizyty/pacjenta.
- Dla danych importowanych kluczem tożsamości pacjenta jest wyłącznie `Doctolib Patient ID`; rekordy ręczne bez tego ID są traktowane jako tymczasowe i wymagają domknięcia alertu administracyjnego.

ID: US-016
Tytuł: Wypełnienie ankiety anamnestycznej przez pacjenta (DE/EN)
Opis: Jako pacjent, chcę wypełnić na tablecie ankietę anamnestyczną przed wizytą, aby lekarz otrzymał ustrukturyzowany wywiad.
Kryteria akceptacji:
- Ankieta zawiera predefiniowane pytania i odpowiedzi (m.in. `Ja/Nein/Weiß nicht` oraz odpowiedniki EN) mapowane do stabilnych kodów technicznych.
- Treść pytań i odpowiedzi wyświetla się w języku interfejsu pacjenta (angielski lub niemiecki), bez zmiany modelu danych.
- Odpowiedzi są zapisywane jako dane ustrukturyzowane (kody pytań/opcji), a nie jako wolny tekst.
- Dla pytania o lokalizację zmian pacjent może wskazać obszar na schemacie ciała i/lub wybrać predefiniowany region; opcjonalnie może wpisać "inną lokalizację".
- Walidacja blokuje finalizację formularza, jeśli nie udzielono odpowiedzi na pytania oznaczone jako wymagane.
- Po finalizacji formularza lekarz widzi odpowiedzi anamnestyczne razem ze zgodami i schematem ciała.

ID: US-018
Tytuł: Scalanie pacjentów (Merge Temporary to Confirmed)
Opis: Jako administrator, chcę połączyć rekord pacjenta tymczasowego (bez ID) z rekordem potwierdzonym (z importu), aby przenieść historię zgód i zamknąć alert tożsamości.
Kryteria akceptacji:
- Dostępna jest funkcja "Scal z potwierdzonym" dla rekordów o statusie `TEMPORARY`.
- System pozwala wskazać docelowy rekord `CONFIRMED` (wyszukiwanie po nazwisku/ID).
- Po zatwierdzeniu: historia (zgody, dokumenty, wizyty) jest przepinana na rekord docelowy.
- Rekord źródłowy (`TEMPORARY`) jest archiwizowany lub usuwany.
- Alert dotyczący braku tożsamości dla rekordu źródłowego jest automatycznie zamykany.

ID: US-017
Tytuł: Awaryjny import z szablonu (Excel Template Fallback)
Opis: Jako administrator, chcę mieć możliwość pobrania awaryjnego szablonu Excel i zaimportowania go, aby utrzymać ciągłość pracy recepcji w przypadku nagłej zmiany formatu pliku Doctolib.
Kryteria akceptacji:
- System udostępnia do pobrania stały szablon `.xlsx` z kolumnami: `doctolib_id`, `first_name`, `last_name`, `dob`, `phone`, `email`.
- Dostępny jest dedykowany importer "Awaryjny", który akceptuje wyłącznie pliki zgodne z tym szablonem (sztywna walidacja).
- Procedura awaryjna (kopiuj-wklej z zepsutego pliku do szablonu) jest udokumentowana w runbooku dla administratora/recepcji.
- Użycie importera awaryjnego jest logowane jako incydent operacyjny.

## 6. Metryki sukcesu

Jako wskaźniki operacyjne (niewymagane w raportowaniu biznesowym, ale kluczowe dla monitoringu technicznego):
- Dostępność systemu (Uptime) na poziomie >= 99.9% w godzinach pracy placówki.
- Skuteczność zapisu do HiDrive >= 99.0% (okno 24h).
- Skuteczność wysyłki SMS >= 98.0% (okno 24h).
- `oldest_pending_age_seconds` dla outbox < 900 s w godzinach pracy.
- Czas od publikacji dokumentu do zakończenia ścieżki `HiDrive+SMS` p95 < 5 minut.
- Czas ładowania formularza na tablecie p95 < 2 sekundy.
- MTTR dla alertów krytycznych (integracje/outbox/import) <= 30 minut.

## 7. Zasady ograniczania złożoności (MVP)

- Faza 1 ma ograniczoną maszynę stanów:
  - `queue_entry`: `WAITING -> IN_PROGRESS -> PATIENT_COMPLETED -> DOCTOR_IN_PROGRESS -> PUBLISHED` (+ `CANCELLED`).
  - `outbox_event`: `PENDING -> PROCESSING -> PROCESSED` (+ `FAILED`, `DEAD_LETTER`).
- Logika domenowa jest implementowana w warstwie aplikacyjnej (serwisy domenowe), a nie przez triggery DB.
- Każde przejście stanu musi mieć testy pozytywne i negatywne.
- Nowe stany, tabele i integracje są dodawane etapowo po walidacji użycia produkcyjnego.

## 8. Kontrakt danych JSON i pola krytyczne

- Każdy JSON przechowywany w DB (`body_map_data`, `anamnesis_payload`, `medical_payload`, `outbox payload`) musi mieć wersję schematu (`schema_version`).
- Walidacja JSON odbywa się przy zapisie (Pydantic/JSON Schema) i jest obowiązkowa dla API oraz zadań background.
- Zmiana kontraktu JSON wymaga:
  - nowej wersji schematu,
  - migracji danych historycznych,
  - testów kompatybilności wstecznej.
- Dane klinicznie/prawnie krytyczne (np. rozpoznanie/procedura) muszą być zapisane w kolumnach relacyjnych i mogą być duplikowane w JSON tylko pomocniczo.
- `anamnesis_payload` przechowuje neutralne językowo kody pytań i opcji; lokalizacja DE/EN jest odpowiedzialnością warstwy prezentacji/słowników.
- **Opis lekarski (Befund):** W `medical_payload` zapisywany jest zarówno wybór strukturyzowany (checkboxy, opcje – do ewentualnego ponownego wygenerowania tekstu), jak i **końcowy tekst opisu po edycji przez lekarza**. Do PDF i archiwum trafia wersja zatwierdzona przez lekarza (po ewentualnych poprawkach wygenerowanego tekstu lub dopisaniach własnych).
- `medical_payload` dla Befund v1 zawiera część globalną i per-zmiana (`lesions[]`) oraz pary pól `generated_text` / `edited_text` (per zmiana i dla podsumowania globalnego).
