# Instrukcja: Tablet poczekalni (rola Tablet)

Interfejs pod adresem **`/tablet/`** służy do wyboru **dzisiejszej kolejki**, **pacjenta** i uruchomienia **formularza intake** (ankieta, zgody, schemat ciała, podpis). Dostęp mają konta z grupami **Tablet**, **Reception** lub **Admin** — zalecane jest **dedykowane konto Tablet** na urządzeniu w poczekalni.

## Wymagania wstępne

- Konto z odpowiednią grupą i dostępem do danych wybranej placówki.
- Tablet skonfigurowany jako przeglądarka pełnoekranowa (opcjonalnie kiosk).
- W panelu administracyjnym tablet powinien mieć przypisaną **placówkę**. Bez przypisania lista kolejek na stronie `/tablet/` może być pusta.

![Komunikat o nieprzypisanym tablecie — przykład](/docs/manual/assets/screenshots/tablet-00-unassigned-warning.png)

---

## 1. Logowanie

1. Otwórz **`/tablet/login/`**.
2. Pola: **Login**, **Hasło** — te same co dla konta Tablet (lub wyjątkowo Reception/Admin).
3. System automatycznie rozpoznaje urządzenie po pierwszym logowaniu i przypisuje je do sesji.
4. Kliknij przycisk logowania (np. „Zaloguj”).

![Ekran logowania tabletu](/docs/manual/assets/screenshots/tablet-01-login.png)

**Typowe problemy**

- „Brak dostępu” — konto nie ma grupy Tablet/Reception/Admin albo jest nieaktywne.  
- Pusta lista kolejek po zalogowaniu — sprawdź z administratorem przypisanie tabletu do placówki.

---

## 2. Strona główna — wybór kolejki

Po zalogowaniu widzisz **dzisiejszą datę** oraz listę **kolejek** na dziś dla wybranej placówki (gdy urządzenie jest przypisane do kliniki, lista jest filtrowana).

- Każda pozycja to link: **nazwa placówki – gabinet (zmiana)**.
- Kliknięcie prowadzi do **`/tablet/queue/<id_kolejki>/`**.

![Lista kolejek na dziś](/docs/manual/assets/screenshots/tablet-02-home-queues.png)

**Uwaga:** Dla roli **Tablet** system oczekuje pracy na **dzisiejszych** kolejkach; próba użycia kolejki z innego dnia może skończyć się komunikatem błędu (kolejka nie jest „na dziś”).

---

## 3. Lista pacjentów w kolejce

Na stronie kolejki widzisz pacjentów przypisanych do tej kolejki (kolejność wg `position_no`). Wybierz **konkretnego pacjenta** (link/tap), aby przejść do uruchomienia formularza.

![Lista pacjentów w wybranej kolejce](/docs/manual/assets/screenshots/tablet-03-queue-entries.png)

---

## 4. Start sesji formularza (`/tablet/entry/<queue_entry_id>/`)

1. Zobaczysz dane pacjenta (nazwisko, imię), pozycję w kolejce, status wpisu.
2. Przyciskiem **otwórz formularz** tworzysz lub odnawiasz sesję formularza dla tego wpisu.
3. Jeśli uruchomisz formularz ponownie dla tej samej osoby, system bierze pod uwagę ostatnią aktywną sesję. Dla porządku pracuj zasadą: jeden pacjent, jedna sesja naraz.

Po uruchomieniu zobaczysz ekran pośredni z linkiem do formularza.

![Potwierdzenie startu sesji / przejście do formularza](/docs/manual/assets/screenshots/tablet-04-entry-started.png)

---

## 5. Formularz pacjenta

### 5.1 Język formularza

Pacjent może potrzebować interfejsu w języku **DE / EN / PL**. Przed przekazaniem tabletu ustaw odpowiedni język.

![Formularz — nagłówek i wybór języka (jeśli widoczny)](/docs/manual/assets/screenshots/tablet-05-form-locale.png)

### 5.2 Sekcje formularza (3 kroki)

Formularz ma **trzy kroki** (stepper u góry). Kolejność i etykiety pochodzą z konfiguracji systemu:

1. **Krok 1 — zgody** — na początku kroku pacjent widzi **wyraźną kartę ze swoimi danymi** (nazwisko i imię, data urodzenia, telefon, e-mail) oraz krótką informację, że wynik i dostęp do portalu są powiązane z tymi danymi (SMS). Następnie checkboxy zgód; wymagane zgody blokują przejście dalej bez zaznaczenia. Karta danych **nie** jest widoczna na kolejnych krokach (można wrócić do kroku 1 przyciskiem „Wstecz”).
2. **Krok 2 — schemat ciała i anamneza** — dotyk: zaznaczanie miejsc (przód/tył); pytania jedno- i wielokrotnego wyboru (bez swobodnego opisu medycznego).
3. **Krok 3 — podpis** — odręczny podpis palcem/rysikiem; wymagany przed finalizacją.

![Fragment ankiety / zgód](/docs/manual/assets/screenshots/tablet-06-form-sections.png)

![Schemat ciała](/docs/manual/assets/screenshots/tablet-07-body-map.png)

![Pole podpisu](/docs/manual/assets/screenshots/tablet-08-signature.png)

### 5.3 Wysłanie (submit)

Po zatwierdzeniu formularz jest wysłany. Pacjent **nie powinien** już edytować treści — zwykle widzi ekran „formularz wysłany”.

![Ekran po wysłaniu formularza](/docs/manual/assets/screenshots/tablet-09-form-submitted.png)

---

## 6. Wylogowanie

Otwórz **`/tablet/logout/`** (link w interfejsie, jeśli jest) lub wyloguj się z konta, aby kolejna osoba nie miała dostępu do list pacjentów.

---

## 7. Bezpieczeństwo

- Nie loguj konta **Recepcja** ani **Admin** na tablecie bez potrzeby.
- Tablety pozostają w poczekalni; **nie wysyłaj** pacjentowi bezpośredniego linku do formularza.
- Po sesji z pacjentem upewnij się, że wróciłeś do listy kolejek lub wylogowałeś urządzenie.

---

## 8. Współpraca z recepcją i lekarzem

- Recepcja musi mieć **utworzoną kolejkę i wpis** dla pacjenta — inaczej nie pojawi się on na tablecie.
- Po wysłaniu formularza lekarz może otworzyć dokument w panelu `/doctor/`.

Dalsze informacje: [Przegląd](00-przeglad.md), [Recepcja](01-rejestracja.md), [Lekarz](03-doktor.md).
