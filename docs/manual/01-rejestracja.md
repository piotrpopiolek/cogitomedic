# Instrukcja: Recepcja (rola Reception)

Dokument dla pracowników recepcji z grupą **Reception** w systemie. Główne narzędzie to **Django Admin** pod adresem `/admin/` oraz dedykowane strony pod `/admin/reception-dashboard/` i `/admin/intake-documents/`.

## Wymagania wstępne

- Konto użytkownika z grupą **Reception**, flagą **staff** (dostęp do panelu administracyjnego) oraz przypisaniem do odpowiednich **placówek (klinik)** — widoczność danych jest ograniczona do placówek przypisanych do konta.
- Przeglądarka aktualna (Chrome/Edge/Firefox), bezpieczne połączenie HTTPS w produkcji.
- Znajomość adresu serwera (np. `https://przyklad.pl/admin/`).

---

## 1. Logowanie do panelu administracyjnego

1. Otwórz w przeglądarce **`/admin/`** (pełny URL zależy od instalacji).
2. Wprowadź **nazwę użytkownika** i **hasło** przyznane przez administratora.
3. Po zalogowaniu zobaczysz stronę główną Django Admin (Unfold) z listą aplikacji (Reception, Users, Medical, itd.).

![Logowanie do Django Admin](/docs/manual/assets/screenshots/reception-01-admin-login.png)

**Typowe problemy**

- Błąd logowania bez szczegółów — sprawdź pisownię, wielkość liter, klawiaturę (np. układ DE).  
- Brak dostępu do konkretnych modeli — zgłoś administratorowi; może być potrzebne dopisanie uprawnień lub placówki.

---

## 2. Dashboard operacyjny recepcji

Adres: **`/admin/reception-dashboard/`**

Strona pokazuje m.in.:

- **Zaległe zdarzenia (błędy)** — wpisy outbox ze statusem błędu (np. problem z generowaniem PDF, uploadem lub SMS). Link „Zobacz szczegóły” prowadzi do rekordu w module Outbox.
- **Ostatnie importy** — pliki importu pacjentów (nazwa pliku, liczba dodanych wierszy, błędy, status wsadu).

**Kiedy tu zaglądać:** codziennie na początku zmiany oraz gdy pacjent zgłasza brak SMS lub dokumentu — aby szybko zobaczyć, czy w systemie nie ma zablokowanych zadań.

![Dashboard recepcji — zaległe zdarzenia i importy](/docs/manual/assets/screenshots/reception-02-reception-dashboard.png)

---

## 3. Kolejki dzienne (Daily queue)

Ścieżka w menu admina: **Reception → Daily queues** (nazwa może być przetłumaczona w interfejsie).

### 3.1 Lista kolejek

Na liście widzisz m.in.:

- datę kolejki (`queue_date`),
- placówkę (`clinic_site`),
- gabinet (`consulting_room`),
- przypisanego lekarza (`assigned_doctor`) — ważne przy współdzieleniu gabinetu w czasie,
- kod zmiany (`shift_code`),
- status kolejki,
- liczbę wpisów / pacjentów (kolumny pomocnicze).

Możesz **filtrować** i **wyszukiwać** po standardowych polach listy Django Admin.

![Lista kolejek dziennych](/docs/manual/assets/screenshots/reception-03-daily-queue-changelist.png)

### 3.2 Widok master/detail (lista pacjentów w kolejkach)

Na liście kolejek dostępny jest link do widoku **master-detail** (ścieżka zawiera `master-detail/` — zależnie od wersji, np. z poziomu listy lub konfiguracji admina).

W tym widoku:

1. Wybierz **datę** w polu filtra i kliknij **Filtruj** (lub odpowiedni przycisk).
2. Rozwiń kolejne **kolejki** (elementy `<details>`) — zobaczysz tabelę: pozycja, pacjent, status wpisu, godzina wizyty.
3. Linki **Edytuj kolejkę**, **Wszystkie wpisy tej kolejki**, **Wpis**, **Pacjent** prowadzą do konkretnych rekordów w adminie.

![Widok master-detail kolejek](/docs/manual/assets/screenshots/reception-04-master-detail.png)

### 3.3 Tworzenie lub edycja kolejki

Przy dodawaniu/edycji rekordu **Daily queue** ustawiasz m.in.:

- placówkę i gabinet,
- datę,
- **lekarza przypisanego do zmiany** (jeśli dotyczy),
- zmianę (`shift_code`),
- status.

Zapisuj zmiany przyciskiem na dole formularza. **Błędne dane** (np. brak wymaganego pola) są zaznaczone przy polach.

---

## 4. Pacjenci i wpisy kolejki

### 4.1 Pacjent (`Patient`)

**Reception → Patients** — dodawanie i edycja pacjentów ręcznie.

Wymagane są m.in.:

- imię, nazwisko,
- data urodzenia,
- telefon (format numeryczny zgodny z walidacją systemu),
- e-mail.

System pilnuje unikalności **numeru telefonu**. Pacjent może być powiązany z wieloma placówkami (relacja M2M) — zależnie od procedury placówki.

### 4.2 Wpis kolejki (`Queue entry`)

**Reception → Queue entries** — wpis łączy **pacjenta** z **kolejką dzienną**, ma pozycję (`position_no`), status (`entry_status`), opcjonalnie godzinę wizyty.

Dodając wpis, wybierz istniejącą kolejkę i pacjenta (lub utwórz pacjenta wcześniej).

![Formularz dodawania wpisu kolejki](/docs/manual/assets/screenshots/reception-05-queue-entry-add.png)

---

## 5. Import pacjentów

### 5.1 Import XLSX z poziomu kolejek

Na liście **Daily queues** dostępny jest link do **importu XLSX** (ścieżka typu `import-xlsx/`). Otwiera się formularz z polem pliku **`.xlsx`**.

1. Przygotuj plik zgodny z wymaganiami systemu (kolumny i format — wg procedury placówki i dokumentacji technicznej).
2. Wybierz plik i wyślij formularz.
3. Import jest przetwarzany **asynchronicznie** — wynik zobaczysz w batchach importu oraz na dashboardzie recepcji.

![Import XLSX — wybór pliku](/docs/manual/assets/screenshots/reception-06-import-xlsx.png)

**Uwaga:** import PDF z eksportu Doctolib (jeśli włączony w danej instalacji) jest osobną procedurą — stosuj się do instrukcji administratora i PRD.

### 5.2 Śledzenie importów

W module **Patient import batches** (lub podobna nazwa) przeglądasz statusy: przetwarzanie, zakończone, błędy. Błędne wiersze mogą być w **Patient import errors**.

---

## 6. Dokumenty intake (PDF) — podgląd

Adres: **`/admin/intake-documents/`**

- Lista wersji dokumentów intake z filtrowaniem (np. placówka).
- Wejście w szczegóły rekordu pokazuje metadane i **podgląd PDF** (inline) lub link do pliku — zależnie od szablonu.

Dostęp mają tylko **Reception** i **Admin** (nie lekarz w tym widoku).

![Lista dokumentów intake](/docs/manual/assets/screenshots/reception-07-intake-documents-list.png)

![Szczegóły dokumentu intake z podglądem PDF](/docs/manual/assets/screenshots/reception-08-intake-document-detail.png)

---

## 7. Dobre praktyki (bezpieczeństwo i RODO)

- **Wyloguj się** z panelu administracyjnego po skończonej pracy na współdzielonym stanowisku (`/admin/logout/` lub menu użytkownika).
- Nie udostępniaj hasła. Sesja może wygasnąć po bezczynności — zaloguj się ponownie.
- Telefon i data urodzenia pacjenta muszą być **zgodne z danymi w systemie**, jeśli pacjent ma później korzystać z portalu wyników — błędy przy rejestracji utrudnią logowanie pacjenta.

---

## 8. Szybki kontakt z administratorem

Zgłaszaj:

- brak widoczności kolejki lub placówki,
- powtarzające się błędy outbox na dashboardzie,
- potrzebę nowego konta lub resetu hasła,
- problemy z importem plików (załącznik z błędem lub numer batcha).

Powiązane dokumenty: [Przegląd](00-przeglad.md), [Tablet](02-tablet.md) (współpraca recepcja–tablet), [Administrator](04-administrator.md).
