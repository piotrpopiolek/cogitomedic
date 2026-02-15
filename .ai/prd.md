# Dokument wymagań produktu (PRD) - Cogitomedica Digital Consents

## 1. Przegląd produktu

Cogitomedica Digital Consents to aplikacja internetowa mająca na celu cyfryzację procesu przyjmowania pacjentów, podpisywania zgód oraz dokumentacji medycznej w placówce medycznej. System ma zastąpić obieg papierowy rozwiązaniem tabletowym dla pacjentów oraz panelem zarządzania dla personelu.

Projekt realizowany jest w trzech fazach:
- Faza 1: Obsługa tabletów, cyfrowe zgody, schemat ciała i podpis elektroniczny pacjenta. Zarządzanie kolejką (Poczekalnia) odbywa się ręcznie lub przez import.
- Faza 2: Panel lekarza do uzupełniania danych medycznych, zatwierdzanie dokumentów oraz automatyzacja wysyłki (zapis do archiwum i powiadomienie SMS).
- Faza 3: Usprawnienie procesu importu listy dziennej z plików eksportowanych z Doctolib oraz integracja z API HiDrive (docelowe API archiwizacji).

Głównym celem jest usprawnienie pracy recepcji i lekarzy, zapewnienie bezpieczeństwa danych oraz automatyzacja archiwizacji dokumentacji przy zachowaniu zgodności z wymogami operacyjnymi placówki. Językiem interfejsu dla wszystkich użytkowników jest język niemiecki.

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
- W Fazie 3 lista dzienna jest uzupełniana codziennym importem pliku eksportowanego z Doctolib (bez bezpośredniej integracji API).
- Generowanie unikalnego linku z jednorazowym tokenem dla pacjenta w celu uruchomienia formularza na tablecie.

### 3.2. Interfejs Pacjenta (Tablet)
- Aplikacja dostosowana do obsługi dotykowej na 4 dedykowanych tabletach.
- Formularz zawiera sekcje: Dane osobowe (tylko do odczytu/weryfikacji), Zgody (checkboxy), Schemat ciała (interaktywne zaznaczanie), Podpis (canvas).
- Brak możliwości edycji ankiety medycznej przez pacjenta.
- Interfejs w języku niemieckim.

### 3.3. Interfejs Lekarza i Personelu
- Podgląd uzupełnionych formularzy pacjentów.
- Formularz medyczny dla lekarza (sztywna struktura pól w kodzie: checkboxy, listy rozwijane, pola tekstowe).
- Możliwość zapisu dokumentu jako Szkic lub Opublikowany.
- Opcja edycji opublikowanego dokumentu i ponownej wysyłki (nadpisanie w archiwum).

### 3.4. Przetwarzanie i Archiwizacja (Backend)
- Generowanie dokumentów PDF na podstawie danych z formularzy.
- Mechanizm Transactional Outbox do obsługi procesów asynchronicznych.
- Mockowanie systemu plików HiDrive (Faza 1-2) z zachowaniem docelowej struktury katalogów.
- Integracja z API HiDrive (Faza 3).
- Integracja z SMSApi do powiadamiania pacjentów o dostępności dokumentu.
- Polityka retencji: automatyczne usuwanie plików PDF z serwera aplikacji po 30 dniach, pod warunkiem potwierdzonego zapisu w HiDrive i wysłania SMS.

## 4. Granice produktu

### W zakresie (In-Scope)
- Moduł recepcji do zarządzania listą dzienną (CRUD + Import).
- Aplikacja webowa dla pacjenta (RWD/Tablet) do podpisywania zgód.
- Moduł lekarza do uzupełniania części medycznej.
- Generowanie plików PDF z podpisem i schematem ciała.
- Mock i późniejsza integracja z HiDrive.
- Powiadomienia SMS (link do pobrania).
- Logowanie zdarzeń (OpenTelemetry).
- Język interfejsu: Niemiecki.

### Poza zakresem (Out-of-Scope)
- Zaawansowany system wersjonowania treści zgód w panelu administracyjnym (zmiany wymagają ingerencji deweloperskiej/konfiguracyjnej).
- Wypełnianie ankiety medycznej (wywiadu) przez pacjenta.
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

ID: US-003
Tytuł: Import pacjentów
Opis: Jako recepcjonista, chcę zaimportować listę pacjentów z pliku, aby przyspieszyć tworzenie listy dziennej.
Kryteria akceptacji:
- System przyjmuje plik w formacie .xlsx lub .csv.
- System mapuje kolumny zgodnie ze zdefiniowanym szablonem.
- W przypadku błędów w pliku, import jest przerywany lub błędne wiersze są raportowane.
- Zaimportowani pacjenci są widoczni w Poczekalni.

ID: US-004
Tytuł: Uruchomienie formularza na tablecie
Opis: Jako recepcjonista, chcę wygenerować i otworzyć unikalny link dla pacjenta na tablecie, aby mógł on rozpocząć proces podpisywania.
Kryteria akceptacji:
- Kliknięcie przycisku przy pacjencie generuje unikalny URL z tokenem.
- Link otwiera formularz w trybie pacjenta (bez menu nawigacyjnego personelu).
- Token jest ważny do momentu pierwszego skutecznego zapisu formularza przez pacjenta.

### Proces Pacjenta (Tablet)
ID: US-005
Tytuł: Akceptacja zgód
Opis: Jako pacjent, chcę zapoznać się z treścią zgód i zaakceptować je za pomocą checkboxów, aby wyrazić zgodę na procedury.
Kryteria akceptacji:
- Lista zgód jest wyświetlana czytelnie na tablecie.
- Wymagane zgody są oznaczone i blokują przejście dalej, jeśli nie są zaznaczone.
- Interfejs jest w języku niemieckim.

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
- Walidacja wymaganych pól medycznych przed publikacją.

ID: US-009
Tytuł: Zapis szkicu i publikacja
Opis: Jako lekarz, chcę mieć możliwość zapisu pracy jako szkic lub ostatecznej publikacji dokumentu.
Kryteria akceptacji:
- Opcja Zapisz jako szkic pozwala na późniejszą edycję i nie uruchamia wysyłki.
- Opcja Zatwierdź i wyślij blokuje edycję (chyba że wywołana zostanie akcja edycji specjalnej), generuje PDF i dodaje zadania do kolejki Outbox.

ID: US-010
Tytuł: Edycja opublikowanego dokumentu
Opis: Jako lekarz, chcę poprawić błąd w już opublikowanym dokumencie i wysłać go ponownie.
Kryteria akceptacji:
- Możliwość edycji zatwierdzonego formularza.
- Ponowne zatwierdzenie tworzy nową wersję PDF.
- Nowa wersja nadpisuje plik w HiDrive (zachowanie tej samej ścieżki/nazwy).
- System pozwala zdecydować, czy ponownie wysłać SMS do pacjenta.

### System i Backend
ID: US-011
Tytuł: Codzienny import listy wizyt z pliku (Faza 3)
Opis: System codziennie importuje listę wizyt z pliku wyeksportowanego z Doctolib, aby wyeliminować ręczne wprowadzanie danych.
Kryteria akceptacji:
- System przyjmuje plik .xlsx lub .csv zgodny z ustalonym szablonem eksportu.
- Import może być uruchamiany ręcznie przez recepcję oraz automatycznie według harmonogramu dziennego.
- Dane (imię, nazwisko, data urodzenia, kontakt) są mapowane do struktury pacjenta w systemie.
- Błędy importu są raportowane na poziomie wiersza.

ID: US-012
Tytuł: Przetwarzanie Outbox (HiDrive i SMS)
Opis: System automatycznie przetwarza kolejkę zadań, aby zapisać pliki w chmurze i powiadomić pacjenta.
Kryteria akceptacji:
- Cron uruchamia przetwarzanie tabeli Outbox.
- Krok 1: Zapis pliku PDF do HiDrive (lub Mocka w F. 1-2) w ustalonej strukturze folderów.
- Krok 2: Po sukcesie Kroku 1, wysyłka SMS z linkiem do pacjenta.
- W przypadku błędu, zadanie otrzymuje status błędu i jest ponawiane w kolejnym cyklu (zgodnie z polityką retry).
- Dokument ma status Opublikowany, ale flagi hidrive_sent/sms_sent odzwierciedlają stan faktyczny.

ID: US-013
Tytuł: Polityka retencji (30 dni)
Opis: System automatycznie usuwa pliki PDF z lokalnego serwera po 30 dniach, aby oszczędzać miejsce i dbać o bezpieczeństwo, ale tylko jeśli są bezpieczne w archiwum.
Kryteria akceptacji:
- Cron sprawdza dokumenty starsze niż 30 dni od publikacji.
- Usunięcie następuje TYLKO GDY: flaga zapisu do HiDrive == true ORAZ flaga wysyłki SMS == true.
- Zdarzenie usunięcia jest logowane w systemie.

## 6. Metryki sukcesu

Jako wskaźniki operacyjne (niewymagane w raportowaniu biznesowym, ale kluczowe dla monitoringu technicznego):
- Dostępność systemu (Uptime) na poziomie 99.9% w godzinach pracy placówki.
- Skuteczność zapisu do HiDrive (procent udanych transferów vs błędy).
- Skuteczność dostarczania SMS (procent dostarczonych wiadomości).
- Liczba dokumentów w stanie błędu (stuck in Outbox) > 0.
- Czas ładowania formularza na tablecie < 2 sekundy.
