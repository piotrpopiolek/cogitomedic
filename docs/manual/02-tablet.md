# Instrukcja: Tablet poczekalni (rola Tablet)

Interfejs pod adresem **`/tablet/`** służy do wyboru **dzisiejszej kolejki**, **pacjenta** i uruchomienia **formularza intake** (ankieta, zgody, schemat ciała, podpis). Dostęp mają konta z grupami **Tablet**, **Reception** lub **Admin** — zalecane jest **dedykowane konto Tablet** na urządzeniu w poczekalni.

## Wymagania wstępne

- Konto z odpowiednią grupą i dostępem do danych wybranej placówki.
- Tablet skonfigurowany jako przeglądarka pełnoekranowa (opcjonalnie kiosk).
- **Tablet device** w Django Admin: urządzenie powinno mieć przypisaną **placówkę (Clinic site)**. Bez przypisania lista kolejek na stronie głównej `/tablet/` może być **pusta**, a komunikat wskaże kontakt z administratorem (zgodnie z README projektu).

![Komunikat o nieprzypisanym tablecie — przykład](/docs/manual/assets/screenshots/tablet-00-unassigned-warning.png)

---

## 1. Logowanie

1. Otwórz **`/tablet/login/`**.
2. Pola: **Login**, **Hasło** — te same co dla konta Tablet (lub wyjątkowo Reception/Admin).
3. Formularz wysyła ukryte pole **`android_id`**: przeglądarka generuje identyfikator w `localStorage` (pierwsze logowanie tworzy nowy UUID). Służy to powiązaniu sesji z urządzeniem w systemie.
4. Kliknij przycisk logowania (etykieta zależy od języka interfejsu personelu, np. „Zaloguj”).

![Ekran logowania tabletu](/docs/manual/assets/screenshots/tablet-01-login.png)

**Typowe problemy**

- „Brak dostępu” — konto nie ma grupy Tablet/Reception/Admin albo jest nieaktywne.  
- Pusta lista kolejek po zalogowaniu — sprawdź przypisanie **Tablet device** do placówki (administrator).

---

## 2. Strona główna — wybór kolejki (`/tablet/`)

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
2. Przyciskiem **otwórz formularz** (tekst z szablonu `staff_ui`) tworzysz lub odnawiasz **sesję** formularza intake dla tego wpisu.
3. Model **„latest-wins”:** jeśli dla tego samego wpisu ponownie wybierzesz innego pacjenta lub ponownie uruchomisz sesję, aktywna sesja może zostać zaktualizowana zgodnie z regułami backendu — personel powinien unikać chaosu (jeden pacjent, jedna sesja naraz na stanowisku).

Po sukcesie zobaczysz ekran pośredni z identyfikatorem formularza (`intake_form_id`) i linkiem dalej do formularza.

![Potwierdzenie startu sesji / przejście do formularza](/docs/manual/assets/screenshots/tablet-04-entry-started.png)

---

## 5. Formularz pacjenta (`/tablet/form/<intake_form_id>/`)

### 5.1 Język formularza

Pacjent może potrzebować interfejsu w języku **DE / EN / PL**. Zmiana jest realizowana parametrem **`?locale=`** (`de`, `en`, `pl`) — po pierwszym ustawieniu locale może być zapisane w sesji formularza. Personel przed przekazaniem tableta powinien ustawić język zgodnie z preferencją pacjenta (np. link z odpowiednim `locale`).

![Formularz — nagłówek i wybór języka (jeśli widoczny)](/docs/manual/assets/screenshots/tablet-05-form-locale.png)

### 5.2 Sekcje formularza (zgodnie z PRD)

Kolejność i etykiety pochodzą z konfiguracji systemu; typowo obejmuje:

1. **Dane osobowe** — do weryfikacji (tryb tylko do odczytu lub zgodnie z implementacją).
2. **Ankieta anamnestyczna** — pytania jedno- i wielokrotnego wyboru (bez swobodnego opisu medycznego).
3. **Zgody** — checkboxy; wymagane zgody blokują przejście dalej bez zaznaczenia.
4. **Schemat ciała** — dotyk: zaznaczanie miejsc (przód/tył); możliwość cofnięcia znacznika.
5. **Podpis** — odręczny podpis palcem/rysikiem; wymagany przed finalizacją.

![Fragment ankiety / zgód](/docs/manual/assets/screenshots/tablet-06-form-sections.png)

![Schemat ciała](/docs/manual/assets/screenshots/tablet-07-body-map.png)

![Pole podpisu](/docs/manual/assets/screenshots/tablet-08-signature.png)

### 5.3 Wysłanie (submit)

Po zatwierdzeniu formularz przechodzi w stan **SUBMITTED**. Pacjent **nie powinien** już edytować treści — interfejs może pokazać ekran „formularz wysłany”.

![Ekran po wysłaniu formularza](/docs/manual/assets/screenshots/tablet-09-form-submitted.png)

---

## 6. Wylogowanie

Otwórz **`/tablet/logout/`** (link w interfejsie, jeśli jest) lub wyloguj się z konta, aby kolejna osoba nie miała dostępu do list pacjentów.

---

## 7. Bezpieczeństwo

- Nie loguj konta **Recepcja** ani **Admin** na tablecie bez potrzeby — wyższe uprawnienia w Django Admin.
- Tablety pozostają w poczekalni; **nie wysyłaj** pacjentowi linku z tokenem do formularza — sesja opiera się na zalogowanym koncie i wyborze w UI (zgodnie z PRD).
- Po sesji z pacjentem upewnij się, że wróciłeś do listy kolejek lub wylogowałeś urządzenie.

---

## 8. Współpraca z recepcją i lekarzem

- Recepcja musi mieć **utworzoną kolejkę i wpis** dla pacjenta — inaczej nie pojawi się on na tablecie.
- Po **SUBMITTED** lekarz może otworzyć dokument w panelu `/doctor/` (gdy intake jest zakończone).

Dalsze informacje: [Przegląd](00-przeglad.md), [Recepcja](01-rejestracja.md), [Lekarz](03-doktor.md).
