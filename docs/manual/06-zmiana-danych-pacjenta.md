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

1. Zaloguj się kontem **Recepcja** (lub **Administrator / Manager**) z dostępem do panelu administracyjnego.
2. Przygotuj **identyfikator rekordu** do wyszukania na liście pacjentów: **nazwisko**, fragment **numeru**, **pełny e-mail**, lub **imię i nazwisko** — pola te są uwzględniane w wyszukiwarce listy.
3. Od wersji **1.5** kilka osób (np. rodzina) może mieć **ten sam numer telefonu**. Przy wspólnym numerze **nie wystarczy** wyszukać wyłącznie po telefonie — doprecyzuj kryterium (**imię + nazwisko**, **e-mail** lub **data urodzenia** na liście), żeby otworzyć **właściwy** rekord.

---

## Krok 1 — Logowanie do panelu administracyjnego

1. Otwórz w przeglądarce **`/admin/`** (z pełnym adresem domeny instalacji).
2. Wpisz **nazwę użytkownika** i **hasło**.
3. Zatwierdź logowanie.

![Logowanie do panelu administracyjnego (personel)](/docs/manual/assets/screenshots/reception-01-admin-login.png)

---

## Krok 2 — Otwarcie listy pacjentów (Patients)

1. Po zalogowaniu znajdź sekcję aplikacji **Reception**.
2. Kliknij **Patients**.
3. Adres listy jest postaci **`/admin/reception/patient/`**.

![Lista pacjentów — Reception → Patients](/docs/manual/assets/screenshots/reception-patient-01-changelist.png)

---

## Krok 3 — Wyszukanie właściwego pacjenta

1. U góry listy wpisz kryterium w polu **Search**.
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

### Reguły ważne przy tej kombinacji pól (od wersji 1.5)

System rozpoznaje pacjenta po **czwórce**: **imię + nazwisko + telefon + data urodzenia**. Tożsamość musi być unikalna — nie sam numer telefonu.

- **Telefon (wspólny numer rodzinny):** **dozwolony** u kilku osób, jeśli różnią się imieniem, nazwiskiem lub datą urodzenia (np. ojciec i syn z jednym telefonem domowym). Zapis w panelu admin **nie jest blokowany** wyłącznie dlatego, że inna osoba ma ten sam numer. **Zablokowany** jest tylko przypadek, gdy po zmianie powstanie **identyczna czwórka** u innego pacjenta (ten sam zestaw czterech pól).
- **Wybór właściwego rekordu:** przy wspólnym numerze zawsze sprawdź na liście **imię, nazwisko i datę urodzenia** przed edycją — łatwo otworzyć niewłaściwą osobę, jeśli szukasz tylko po telefonie.
- **Normalizacja przy zapisie:** system sam ujednolica zapis **numeru telefonu** oraz format **imienia i nazwiska** (np. wielkość liter). Po zapisie wartości w formularzu mogą wyglądać nieco inaczej niż wpisałeś — to oczekiwane.
- **Data urodzenia:** musi się **zgadzać** z logowaniem do [portal wyników](05-pacjent-wyniki.md). **Uwaga krytyczna:** przy zmianie telefonu lub DOB poinformuj pacjenta o **obu** wartościach naraz — stary numer przy nowej dacie (lub odwrotnie) uniemożliwi logowanie.
- **Portal przy wspólnym numerze:** jeśli dwie osoby mają ten sam telefon i tę samą datę urodzenia (rzadko), portal może dodatkowo poprosić o **nazwisko** — wpisane musi być tak jak w recepcji ([szczegóły](05-pacjent-wyniki.md)).
- **Imię i nazwisko:** system przelicza klucze dopasowania nazw PDF z laboratorium; po zmianie upewnij się, że [nazewnictwo plików HiDrive](hidrive_incoming_reception.md) jest spójne z dokumentacją przychodzącą.
- **Email:** w tym przykładzie **nie** jest zmieniany; jeśli poprawiasz adres, wpisz pełny i poprawny e-mail.

Przewiń do dołu formularza i kliknij przycisk zapisu.

---

## Krok 6 — Zapis i potwierdzenie

1. Jeszcze raz porównaj **telefon** i **datę urodzenia** pod kątem portalu wyników.
2. Kliknij **Zapisz**.
3. Upewnij się, że widzisz **komunikat o pomyślnym zapisie** i że pola po przeładowaniu strony pokazują nowe wartości.

![Komunikat sukcesu po zapisie (przykład demo)](/docs/manual/assets/screenshots/reception-patient-05-save-confirmation.png)

**Typowe błędy:**

- **Duplikat czwórki** — po zapisie inny pacjent ma już identyczne imię, nazwisko, telefon i datę urodzenia. Panel admin pokaże błąd unikalności (constraint bazy); zapis się nie uda. Popraw dane lub skonsultuj z administratorem.
- **Wspólny numer z inną tożsamością** — **nie jest błędem**; zapis powinien przejść. Upewnij się tylko, że edytujesz właściwy rekord (patrz Krok 3).
- **Niepoprawny format** — numer telefonu lub data urodzenia poza dopuszczalnym formatem.
- **Brak dostępu** — konto bez uprawnień do zapisu.

**Uwaga:** ostrzeżenie o wspólnym numerze (`shared_phone`) pojawia się w **API recepcji** (integracje), nie w tym formularzu panelu admin.

---

## Pozostałe pola formularza (skrót)

| Pole | Uwagi |
|------|--------|
| **Street / City / Postal code** | Opcjonalnie; osobna korekta adresu bez wpływu na portal jak wyżej, o ile jej nie zestawiasz politycznie z identyfikatorem wizyty. |
| **Country code** | Kod kraju dla numeru telefonu (np. DE). |
| **Clinic sites** | Wiele placówek — stosuj zgodnie z procedurą. |
| **Is active** | To nie anonimizacja RODO. |
| **Id, Created at, Updated at** | Tylko odczyt. |

---

## Po zmianie danych — obowiązki informacyjne

1. **Pacjent portalu:** przekaż **nowy telefon i nową datę urodzenia**, jeżeli zmieniłeś którekolwiek — oba muszą się zgadzać z rekordem przy następnym logowaniu (jeśli zmienisz tylko jedno pole, dostęp się nie uda). Przy **wspólnym numerze rodzinnym** każda osoba loguje się **swoją** datą urodzenia; w skrajnym przypadku (ten sam numer i ta sama data urodzenia u dwóch osób) portal może wymagać także **nazwiska**.
2. **HiDrive / laboratorium:** po zmianie imienia i nazwiska dopasuj wrzutkę lub konwencję nazw plików.
3. **Import Doctolib:** po zmianie tożsamości upewnij się, że kolejny import dopasuje wiersz po **pełnej czwórce**, nie tylko po numerze telefonu.

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
