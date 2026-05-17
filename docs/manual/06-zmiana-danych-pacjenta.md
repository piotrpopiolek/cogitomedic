# Zmiana danych osobowych pacjenta (panel administracyjny)

Ten rozdział opisuje **korektę danych identyfikacyjnych i kontaktowych pacjenta** w panelu administracyjnym. Operacji nie wykonuje się na tablecie ani w panelu lekarza — wyłącznie w panelu administracyjnym pod `/admin/`, zwykle z konta **Recepcja**; to samo mogą zrobić **Administrator** lub **Manager**, jeśli mają odpowiedni dostęp.

**Powiązane:** ogólny opis modułu recepcji — [01-rejestracja.md](01-rejestracja.md); portal wyników (telefon + data urodzenia) — [05-pacjent-wyniki.md](05-pacjent-wyniki.md); dopasowanie nazw plików PDF z laboratorium — [hidrive_incoming_reception.md](hidrive_incoming_reception.md).

Szczegółowy **przypadek krok po kroku**: zmiana **imienia**, **nazwiska**, **daty urodzenia** i **numeru telefonu** — od wyszukania rekordu do zapisu i komunikatu sukcesu.

---

## Kto może zmieniać dane i czego nie robi lekarz

| Rola | Typowy dostęp do edycji danych pacjenta |
|------|--------------------------------------|
| **Recepcja** | Tak — pełna lista pacjentów oraz zapis zmian w formularzu. |
| **Manager**, **Administrator** | Tak — przy odpowiednim dostępie. |
| **Lekarz** | **Nie** — lekarz nie powinien samodzielnie poprawiać imienia, nazwiska, telefonu, daty urodzenia ani e-maila w tym formularzu; zlecenie idzie do recepcji lub administratora. |

Instrukcja poniżej dotyczy pracy **w panelu administracyjnym przez przeglądarkę**.

---

## Przed rozpoczęciem

1. Upewnij się, że pracujesz na **właściwym środowisku** (adres placówki / VPN zgodnie z procedurą IT).
2. Zaloguj się kontem **Recepcja** (lub **Administrator / Manager**) z dostępem do panelu administracyjnego.
3. Przygotuj **identyfikator rekordu** do wyszukania na liście pacjentów: **nazwisko**, fragment **numeru**, **pełny e-mail**, lub **imię i nazwisko** — pola te są uwzględniane w wyszukiwarce listy.

---

## Krok 1 — Logowanie do panelu administracyjnego

1. Otwórz w przeglądarce **`/admin/`** (z pełnym adresem domeny instalacji).
2. Wpisz **nazwę użytkownika** i **hasło**.
3. Zatwierdź logowanie.

![Logowanie do panelu administracyjnego (personel)](/docs/manual/assets/screenshots/reception-01-admin-login.png)

---

## Krok 2 — Otwarcie listy pacjentów (Patients)

1. Po zalogowaniu znajdź sekcję aplikacji **Reception**.
2. Kliknij **Patients** (w polskiej wersji interfejsu może to być np. **Pacjenci**).
3. Adres listy jest postaci **`/admin/reception/patient/`**.

![Lista pacjentów — Reception → Patients](/docs/manual/assets/screenshots/reception-patient-01-changelist.png)

---

## Krok 3 — Wyszukanie właściwego pacjenta

1. U góry listy wpisz kryterium w polu **Search** (Szukaj).
2. Zatwierdź (przycisk szukania lub Enter).

Na zrzucie demo wyszukiwany jest **adres e-mail** `anna.demo@example.invalid` — to eliminuje pomyłkę przy częstych nazwiskach.

![Wynik wyszukiwania (przykład: jednoznaczny e-mail)](/docs/manual/assets/screenshots/reception-patient-02-search-results.png)

---

## Krok 4 — Otwarcie formularza (stan wyjściowy przed zmianami)

Kliknij **nazwisko** pacjenta w wierszu wyniku (link do widoku zmian).

**Przykład (stan przed zmianą):**

| Pole | Wartość przed korektą |
|------|----------------------|
| **First name** | Anna |
| **Last name** | Demo |
| **Date of birth** | 1985-05-15 |
| **Phone** | 1111111111111 |
| **Email** *(w tym ćwiczeniu bez zmian)* | anna.demo@example.invalid |

![Formularz — tożsamość i kontakt przed edycją (demo)](/docs/manual/assets/screenshots/reception-patient-03-identity-before-edit.png)

---

## Krok 5 — Wprowadzenie nowych wartości: imię, nazwisko, data urodzenia, telefon

Wpisz nowe wartości w polach formularza. W tym przykładzie datę wpisujemy jako **`RRRR-MM-DD`**.

**Przykład końcowy (demo po korekcie, przed przyciskiem Save):**

| Pole | Wartość docelowa w zrzucie |
|------|----------------------------|
| **First name** | Marianna |
| **Last name** | Kowalska |
| **Date of birth** | 1992-08-14 |
| **Phone** | 1222222222222 |

Sprawdź pola **bez literówek** — szczególnie dzień i miesiąc urodzenia oraz pełny numer telefonu.

![Te same pola po wpisaniu nowych wartości (jeszcze przed zapisem)](/docs/manual/assets/screenshots/reception-patient-04-identity-after-edit.png)

### Reguły ważne przy tej kombinacji pól

- **Telefon:** nie może być już przypisany do innego pacjenta. Jeśli ten sam numer jest zapisany przy dwóch osobach, system nie pozwoli zapisać zmian i trzeba to wyjaśnić z administratorem.
- **Data urodzenia:** musi się **zgadzać** z logowaniem do [portal wyników](05-pacjent-wyniki.md). **Uwaga krytyczna:** przy takiej zmianie **oba** pola wejściowe pacjenta (telefon **i** DOB na portalu) muszą być zaktualizowane jednocześnie w komunikacie do pacjenta — nadal stare DOB przy nowym numerze lub odwrotnie doprowadzą do blokady logowania.
- **Imię i nazwisko:** system przelicza klucze dopasowania nazw PDF z laboratorium; po zmianie upewnij się, że [nazewnictwo plików HiDrive](hidrive_incoming_reception.md) jest spójne z dokumentacją przychodzącą.
- **Email:** w tym przykładzie **nie** jest zmieniany; jeśli poprawiasz adres, wpisz pełny i poprawny e-mail.

Przewiń do dołu formularza i kliknij przycisk zapisu (np. **Save** lub **Zapisz**).

---

## Krok 6 — Zapis i potwierdzenie

1. Jeszcze raz porównaj **telefon** i **datę urodzenia** pod kątem portalu wyników.
2. Kliknij **Save / Zapisz**.
3. Upewnij się, że widzisz **komunikat o pomyślnym zapisie** i że pola po przeładowaniu strony pokazują nowe wartości.

![Komunikat sukcesu po zapisie (przykład demo)](/docs/manual/assets/screenshots/reception-patient-05-save-confirmation.png)

**Typowe błędy:** numer telefonu zajęty przez innego pacjenta, niepoprawny zapis numeru lub daty, brak dostępu do zapisu.

---

## Pozostałe pola formularza (skrót)

| Pole | Uwagi |
|------|--------|
| **Street / City / Postal code** | Opcjonalnie; osobna korekta adresu bez wpływu na portal jak wyżej, o ile jej nie zestawiasz politycznie z identyfikatorem wizyty. |
| **Country code** | Kod kraju dla numeru telefonu (np. DE). |
| **Clinic sites** | Wiele placówek — stosuj zgodnie z procedurą. |
| **Is active** | To nie anonimizacja RODO. |
| **Id, Created at, Updated at** | Tylko odczyt. |

**Identyfikator Doctolib pacjenta:** pole jest ukryte; w razie potrzeby zgłoś zmianę do działu IT.

---

## Po zmianie danych — obowiązki informacyjne

1. **Pacjent portalu:** przekaż **nowy telefon i nową datę urodzenia**, jeżeli zmieniłeś którekolwiek — oba muszą się zgadzać z rekordem przy następnym logowaniu (jeśli zmienisz tylko jedno pole, dostęp się nie uda).
2. **HiDrive / laboratorium:** po zmianie imienia i nazwiska dopasuj wrzutkę lub konwencję nazw plików.
3. Audyt — postępuj zgodnie z polityką placówki i IT.

---

## Alternatywa: wejście z widoku „master-detail” kolejki

Z [widoku master-detail kolejek](01-rejestracja.md) przejdź przez link **Pacjent** przy wpisie — formularz i zapis są takie same.

---

## Adresy

| Cel | Ścieżka |
|-----|---------|
| Lista | `/admin/reception/patient/` |
| Edycja | `/admin/reception/patient/.../change/` |

---

Lista użytych zrzutów ekranu znajduje się tutaj: [screenshot-checklist.md](screenshot-checklist.md).
