---
name: ""
overview: ""
todos: []
isProject: false
---

# Proces poczekalni – uproszczony (tablet na wyposażeniu rejestracji)

Tablety są na wyposażeniu rejestracji. Tablet jest **zalogowany na stałe** na specjalną rolę z dostępem **wyłącznie do jednego widoku: poczekalnia**. W tym widoku rejestracja widzi listę pacjentów **jednej kolejki** (jedna kolejka = jeden lekarz) i wybiera pacjenta, któremu przekazuje tablet do wypełnienia ankiety. Brak linków z tokenem i osobnej „aplikacji pacjenta” – jeden ekran tabletu, jedna rola, jeden flow. **Pacjent wypełnia ankietę wyłącznie w poczekalni na tablecie od rejestracji – brak dostępu z zewnątrz.**

---

## 1. Założenia


| Aspekt                | Decyzja                                                                                                                                                                                                               |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Tablet**            | Urządzenie rejestracji, stale zalogowane (sesja/cookie). **Jeden tablet = jedna kolejka** (jedna kolejka = jeden lekarz). Na recepcji np. 2–4 tablety; każdy tablet jest przypisany do jednej kolejki na dany dzień.  |
| **Rola tabletu**      | Dedykowana rola (np. `TABLET` lub `WAITING_ROOM`) z dostępem **tylko** do: lista pacjentów w danej kolejce, formularz intake (z walidacją na końcu: wszystkie pola + podpis). Tablet nie potrzebuje więcej uprawnień. |
| **Widok poczekalnia** | Lista pacjentów **tej jednej kolejki** (tego jednego lekarza); po wyborze pacjenta – ekran z danymi pacjenta do weryfikacji, potem formularz intake. Brak wyboru „która lista” – mniej pomyłek, szybsza praca.        |
| **Aktor wyboru**      | Rejestracja wybiera pacjenta na tablecie z listy; przekazuje tablet pacjentowi; pacjent **sprawdza poprawność swoich danych**, potem wypełnia ankietę (zgody, anamneza, podpis) i wysyła.                             |
| **Uwierzytelnianie**  | Sesja (cookie) lub Bearer – ten sam użytkownik tabletu. **Brak** tokenów jednorazowych w URL. Sesja tabletu: **kilka godzin** (na tabletach nie edytuje się danych pacjenta – korekty tylko z kont RECEPTION).        |
| **TabletDevice**      | Każdy tablet ma **własne konto** (rola TABLET). Rejestracja urządzenia: jeśli w systemie nie ma jeszcze tabletu o danym `android_id`, dopisuje się go automatycznie (np. `Build.SERIAL`).                             |


---

## 1b. Decyzje (audyt, bezpieczeństwo, dowody)


| Ryzyko / wątpliwość                                                    | Decyzja                                                                                                                                                         |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Wspólna tożsamość w audycie** (wszystkie akcje = użytkownik tabletu) | **Podpis pacjenta na zakończenie ankiety jest dowodem.** Dodatkowo można zapisywać `android_id`, `Build.SERIAL`, aby identyfikować, który tablet został wydany. |
| **Kradzież / przejęcie sesji**                                         | Rejestracja ma nadzór nad tabletem; **wystarczy blokada ekranu** (np. po wyjściu z aplikacji / po czasie bezczynności).                                         |
| **Brak izolacji „pacjent vs personel”**                                | **Podpis pacjenta – tego nikt nie podrobi.** Identyfikacja tabletu (`android_id`, `Build.SERIAL`) pozwala powiązać wypełnienie z konkretnym urządzeniem.        |
| **Pacjent wypełnił w domu**                                            | Nie dotyczy: **pacjent wypełnia tylko w poczekalni na tablecie** od rejestracji; nie ma dostępu z zewnątrz.                                                     |
| **Wiele placówek / wiele tabletów**                                    | **Początkowa wersja systemu obsługuje tylko jedną przychodnię.**                                                                                                |


---

## 2. Przepływ krok po kroku

### 2.1 Przygotowanie (panel recepcji – RECEPTION/ADMIN)

Wykonywane na stanowisku recepcji (panel staff), nie na tablecie:

1. **Kolejka dzienna** – utworzenie lub wybór kolejki na dziś: `POST/GET /api/v1/daily-queues` (data, placówka, gabinet, zmiana).
2. **Pacjenci w kolejce** – dodawanie pacjentów: wyszukanie/utworzenie pacjenta (`GET/POST /api/v1/patients`), potem `POST /api/v1/daily-queues/{id}/entries` z `patient_id`. Lista wpisów: `GET /api/v1/daily-queues/{id}/entries`.
3. **Przypisanie tabletu do kolejki** – na dany dzień każdy tablet obsługuje **jedną** kolejkę (np. tablet 1 → dr Kowalski, tablet 2 → dr Nowak).

### 2.2 Tablet: zalogowany użytkownik z rolą „poczekalnia”

1. **Logowanie tabletu** (jednorazowo lub po wygaśnięciu sesji)
  Konto typu „tablet poczekalni” (np. użytkownik z rolą `TABLET`). Po zalogowaniu tablet ma dostęp **tylko** do:
  - widoku **lista pacjentów w danej kolejce** (poczekalnia dla tego lekarza),
  - oraz po wyborze pacjenta – **ekranu weryfikacji danych pacjenta**, a potem **formularza intake** (zgody, anamneza, podpis, submit).
2. **Widok poczekalnia na tablecie**
  - Tablet wywołuje API zwracające **listę pacjentów w przypisanej kolejce** (np. `GET /api/v1/daily-queues/{id}/entries` dla kolejki powiązanej z tym tabletem, lub dedykowany endpoint typu `GET /api/v1/waiting-room/my-queue-entries`).  
  - Na ekranie: lista (imię, nazwisko, pozycja, status); rejestracja **wybiera jednego pacjenta** (tap).

### 2.3 Wybór pacjenta → weryfikacja danych → formularz

1. **Wybór pacjenta = rozpoczęcie sesji formularza**
  - Po tapnięciu pacjenta tablet wywołuje **POST /api/v1/queue-entries/{queue_entry_id}/sessions** (z opcjonalnym `form_locale`, `tablet_device_id`; `tablet_device_id` / `android_id` / `Build.SERIAL` do identyfikacji urządzenia).  
  - Backend tworzy/aktualizuje sesję, tworzy lub wiąże formularz intake, zwraca `**intake_form_id`**.  
  - Tablet **zaciąga dane pacjenta** i pokazuje **ekran weryfikacji**: pacjent sprawdza, czy wszystkie jego dane są poprawne. Na tej podstawie łączy się formularz X z pacjentem (znane id).  
  - Następnie tablet przechodzi do **widoku formularza** dla tego `intake_form_id`.
2. **Przekazanie tabletu pacjentowi**
  - Pacjent ma przed sobą (po weryfikacji danych) formularz intake. Wypełnia ankietę (zgody, anamneza, podpis) i wysyła.

### 2.4 Wypełnienie ankiety i submit (na tablecie)

1. **Formularz intake** (zgody, anamneza, opcjonalnie mapa ciała, podpis)
  - Zapis zgód: docelowo `PUT /api/v1/intake-forms/{id}/consents`.  
  - Zapis anamnezy: `PUT /api/v1/intake-forms/{id}/anamnesis` (już w API).  
  - Podpis: upload/zapis (endpoint do dokończenia); bez podpisu submit zwraca 400.  
  - **Walidacja na końcu:** wszystkie wymagane pola wypełnione + podpis złożony – dopiero wtedy submit jest możliwy.  
  - Submit: `POST /api/v1/intake-forms/{id}/submit` – backend ustawia formularz na SUBMITTED, wpis kolejki na PATIENT_COMPLETED, konsumuje sesję.
2. **Po submit**
  - Tablet wraca do widoku listy pacjentów (poczekalnia), żeby rejestracja mogła wybrać kolejnego pacjenta.

---

## 3. Rola i uprawnienia tabletu

- **Proponowana rola:** np. `TABLET` lub `WAITING_ROOM` (do dodania do `StaffRole` i RBAC).  
- **Dostęp – tylko kilka endpointów:**
  - **Lista pacjentów w danej kolejce** – np. `GET /api/v1/daily-queues/{id}/entries` (gdzie kolejka jest powiązana z tabletem) lub `GET /api/v1/waiting-room/my-queue-entries`.
  - **POST** `queue-entries/{id}/sessions` – wybór pacjenta, rozpoczęcie sesji, zwrot `intake_form_id`.
  - **GET** definicji zgód i pytań anamnestycznych (słowniki).
  - **GET** kontekstu formularza / danych pacjenta (do ekranu weryfikacji).
  - **PUT** `intake-forms/{id}/anamnesis`, docelowo **PUT** `.../consents`, upload podpisu, **POST** `.../submit`.
- **Brak** dostępu do: pełnej listy pacjentów (wyszukiwarka globalna), zarządzania użytkownikami, tworzenia/edycji kolejek, edycji danych pacjenta, ustawień systemu itd. **Tablet nie potrzebuje więcej uprawnień.**

Implementacja: w backendzie powyższe endpointy przyjmują rolę `TABLET` (lub `WAITING_ROOM`) obok `RECEPTION`/`ADMIN`; panel recepcji nadal korzysta z pełnego zestawu endpointów recepcji.

---

## 4. Diagram przepływu (uproszczony)

```
[Panel recepcji]                    [Backend]                    [Tablet]
RECEPTION/ADMIN                   (jedna przychodnia)                 |
  | POST daily-queues, entries          |                             |
  | GET .../entries                      |                             |
  | Przypisanie: tablet ↔ kolejka       |                             |
  |------------------------------------>|                             |
  |                                     |     [Tablet zalogowany:     |
  |                                     |      rola TABLET,           |
  |                                     |      jedna kolejka]         |
  |                                     |<----------------------------|
  |                                     |  GET my-queue-entries       |
  |                                     |---------------------------->|
  |                                     |  Lista pacjentów (jedna kolejka)
  |                                     |  Rejestracja wybiera pacjenta (tap)
  |                                     |<----------------------------|
  |                                     |  POST queue-entries/{id}/sessions
  |                                     |  → intake_form_id           |
  |                                     |---------------------------->|
  |                                     |  Dane pacjenta → weryfikacja przez pacjenta
  |                                     |  Widok formularza           |
  |                                     |  PUT anamnesis, consents, podpis, POST submit
  |                                     |<----------------------------|
  |                                     |  → SUBMITTED, PATIENT_COMPLETED
  |                                     |  Tablet wraca do listy      |
```

---

## 5. Co znika / co się upraszcza


| Wcześniej                                           | Po uproszczeniu                                                                     |
| --------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Generowanie linku z tokenem jednorazowym            | Nie ma – tablet zalogowany, wybór pacjenta z listy.                                 |
| Przekazywanie linku pacjentowi (np. SMS / QR)       | Nie ma – pacjent dostaje fizycznie tablet z już otwartym formularzem.               |
| Walidacja tokenu (validate) na tablecie             | Niepotrzebna – autoryzacja sesją użytkownika tabletu.                               |
| Osobna „aplikacja pacjenta” vs „aplikacja recepcji” | Jedna aplikacja na tablecie: lista jednej kolejki + weryfikacja danych + formularz. |
| Dostęp pacjenta z zewnątrz (w domu)                 | Nie ma – pacjent wypełnia tylko w poczekalni na tablecie.                           |


---

## 6. Wymagania do dokończenia (backend / API)

1. **Rola TABLET (lub WAITING_ROOM)** – rozszerzenie `StaffRole`, rejestracja użytkowników „tablet” (każdy tablet = osobne konto), RBAC: dostęp tylko do listy pacjentów w kolejce, sesje, formularz (bez edycji danych pacjenta).
2. **Jeden tablet = jedna kolejka** – mechanizm przypisania tabletu do kolejki na dany dzień (konfiguracja / wybór na tablecie lub w panelu recepcji).
3. **Lista pacjentów w kolejce tabletu** – endpoint zwracający wpisy **przypisanej** kolejki (np. `GET /api/v1/waiting-room/my-queue-entries` lub `GET /api/v1/daily-queues/{id}/entries` z kontekstem tabletu), z danymi pacjenta i statusem – dostępny dla roli TABLET.
4. **POST queue-entries/{id}/sessions** – już istnieje; dla tabletu z opcjonalnym przekazaniem `android_id` / `Build.SERIAL`; zwrot `intake_form_id`. Tablet (TABLET) może wywoływać obok RECEPTION/ADMIN.
5. **Ekran weryfikacji danych pacjenta** – GET danych pacjenta powiązanego z queue_entry / intake_form (tylko odczyt; bez możliwości edycji z tabletu).
6. **Endpoint zgód** – `PUT /api/v1/intake-forms/{id}/consents`, dostępny dla roli TABLET (i RECEPTION/ADMIN).
7. **Upload podpisu** – endpoint zapisu/uploadu podpisu dla intake (submit wymaga podpisu); opcjonalnie zapis identyfikatora urządzenia (`android_id`, `Build.SERIAL`) przy sesji/submicie.
8. **TabletDevice** – automatyczne dopisanie urządzenia, gdy loguje się tablet z nieznanym `android_id` (np. rejestracja z użyciem `Build.SERIAL`).

Reszta (anamneza, submit, stany wpisu/formularza) bez zmian; zmienia się sposób wejścia (wybór z listy jednej kolejki, weryfikacja danych pacjenta, potem formularz) oraz zakres (jedna przychodnia, jedna kolejka na tablet).