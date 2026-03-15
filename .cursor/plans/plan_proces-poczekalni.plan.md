---
name: ""
overview: ""
todos: []
isProject: false
---

# Proces poczekalni – uproszczony (tablet na wyposażeniu rejestracji)

Tablety są na wyposażeniu rejestracji. Tablet jest **zalogowany na stałe** na specjalną rolę z dostępem **wyłącznie do jednego widoku: poczekalnia**. W tym widoku rejestracja **wybiera kolejkę** na tablecie (nie ma twardego przypisania tabletu do kolejki w panelu recepcji), potem widzi listę pacjentów tej kolejki i wybiera pacjenta, któremu przekazuje tablet do wypełnienia ankiety. Brak linków z tokenem i osobnej „aplikacji pacjenta” – jeden ekran tabletu, jedna rola, jeden flow. **Pacjent wypełnia ankietę wyłącznie w poczekalni na tablecie od rejestracji – brak dostępu z zewnątrz.**

---

## 1. Założenia


| Aspekt                | Decyzja                                                                                                                                                                                                                                                                                    |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Tablet**            | Urządzenie rejestracji, stale zalogowane (sesja/cookie). Na recepcji np. 2–4 tablety. **Tablet jest przypisany do jednej placówki** (ClinicSite) – w modelu `TabletDevice` pole `clinic_site`; widzi wyłącznie kolejki tej placówki. Przypisania dokonuje się w panelu admin lub przez API (PATCH tablet-devices). Bez przypisania tablet nie wyświetla kolejek.                                                                             |
| **Rola tabletu**      | Dedykowana rola (np. `TABLET` lub `WAITING_ROOM`) z dostępem **tylko** do: wybór kolejki, lista pacjentów w wybranej kolejce, formularz intake (z walidacją na końcu: wszystkie pola + podpis). Tablet nie potrzebuje więcej uprawnień.                                                    |
| **Widok poczekalnia** | Rejestracja **wybiera kolejkę** na tablecie (np. lista dzisiejszych kolejek), potem lista pacjentów tej kolejki; po wyborze pacjenta – ekran z danymi pacjenta do weryfikacji, potem formularz intake.                                                                                     |
| **Aktor wyboru**      | Rejestracja wybiera pacjenta na tablecie z listy; przekazuje tablet pacjentowi; pacjent **sprawdza poprawność swoich danych**, potem wypełnia ankietę (zgody, anamneza, podpis) i wysyła.                                                                                                  |
| **Uwierzytelnianie**  | Sesja (cookie) lub Bearer – ten sam użytkownik tabletu. **Brak** tokenów jednorazowych w URL. Sesja tabletu: **kilka godzin** (na tabletach nie edytuje się danych pacjenta – korekty tylko z kont RECEPTION).                                                                             |
| **TabletDevice**      | Każdy tablet ma **własne konto** (rola TABLET). Model `TabletDevice`: `android_id` (unikalny identyfikator urządzenia), opcjonalnie **`clinic_site`** (FK do placówki). Przy pierwszym logowaniu z `android_id` tworzony jest wpis TabletDevice (auto-dopisanie). Aby tablet widział kolejki, musi być **przypisany do placówki** w adminie lub przez API. |


---

## 1b. Decyzje (audyt, bezpieczeństwo, dowody)


| Ryzyko / wątpliwość                                                    | Decyzja                                                                                                                                                         |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Wspólna tożsamość w audycie** (wszystkie akcje = użytkownik tabletu) | **Podpis pacjenta na zakończenie ankiety jest dowodem.** Dodatkowo można zapisywać `android_id`, `Build.SERIAL`, aby identyfikować, który tablet został wydany. |
| **Kradzież / przejęcie sesji**                                         | Rejestracja ma nadzór nad tabletem; **wystarczy blokada ekranu** (np. po wyjściu z aplikacji / po czasie bezczynności).                                         |
| **Brak izolacji „pacjent vs personel”**                                | **Podpis pacjenta – tego nikt nie podrobi.** Identyfikacja tabletu (`android_id`, `Build.SERIAL`) pozwala powiązać wypełnienie z konkretnym urządzeniem.        |
| **Pacjent wypełnił w domu**                                            | Nie dotyczy: **pacjent wypełnia tylko w poczekalni na tablecie** od rejestracji; nie ma dostępu z zewnątrz.                                                     |
| **Brak dostępu z zewnątrz = zero elastyczności**                       | **Świadoma decyzja.**                                                                                                                                           |
| **Wiele placówek / wiele tabletów**                                    | **Początkowa wersja systemu obsługuje tylko jedną przychodnię.**                                                                                                |


---

## 1c. Decyzje techniczne (token, TabletDevice)


| Aspekt                              | Decyzja                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Sesja bez tokenu**                | **Wycofanie tokenu z modeli i z pozostałej dokumentacji.** Obecnie `PatientFormSession` ma obligatoryjne `token_hash` – w nowym flow tablet nie używa tokenu; autoryzacja to „request.user.role == TABLET + intake_form w wybranej kolejce”. Wykonujemy **migracje bazy**, które usuwają pole tokenu (np. `token_hash`) z modelu i zależną logikę. Po migracji nie ma generowania ani walidacji tokenu. |
| **TabletDevice – tylko android_id** | **Migracja:** usuwamy z modelu `TabletDevice` pola `name` i `device_code`, wprowadzamy **tylko `android_id`** (unikalny identyfikator urządzenia). Auto-dopisanie: przy pierwszym logowaniu tabletu z danym `android_id` tworzony jest wpis w TabletDevice.                                                                                                                                             |


---

## 2. Przepływ krok po kroku

### 2.1 Przygotowanie (panel recepcji – RECEPTION/ADMIN)

Wykonywane na stanowisku recepcji (panel staff), nie na tablecie:

1. **Kolejka dzienna** – utworzenie lub wybór kolejki na dziś: `POST/GET /api/v1/daily-queues` (data, placówka, gabinet, zmiana).
2. **Pacjenci w kolejce** – dodawanie pacjentów: wyszukanie/utworzenie pacjenta (`GET/POST /api/v1/patients`), potem `POST /api/v1/daily-queues/{id}/entries` z `patient_id`. Lista wpisów: `GET /api/v1/daily-queues/{id}/entries`.

### 2.2 Tablet: zalogowany użytkownik z rolą „poczekalnia”

1. **Logowanie tabletu** (jednorazowo lub po wygaśnięciu sesji)
  Konto typu „tablet poczekalni” (np. użytkownik z rolą `TABLET`). Po zalogowaniu tablet ma dostęp **tylko** do:
  - **wyboru kolejki** (np. lista dzisiejszych kolejek),
  - **listy pacjentów w wybranej kolejce**,
  - oraz po wyborze pacjenta – **ekranu weryfikacji danych pacjenta**, a potem **formularza intake** (zgody, anamneza, podpis, submit).
2. **Widok poczekalnia na tablecie**
  - Rejestracja **wybiera kolejkę** (np. `GET /api/v1/daily-queues?queue_date=today`, potem wybór jednej z list).  
  - Tablet wywołuje API zwracające **listę pacjentów w wybranej kolejce** (np. `GET /api/v1/daily-queues/{id}/entries`).  
  - Na ekranie: lista (imię, nazwisko, pozycja, status); rejestracja **wybiera jednego pacjenta** (tap).

### 2.3 Wybór pacjenta → weryfikacja danych → formularz

1. **Wybór pacjenta = rozpoczęcie sesji formularza**
  - Po tapnięciu pacjenta tablet wywołuje **POST /api/v1/queue-entries/{queue_entry_id}/sessions** (z opcjonalnym `form_locale`, `tablet_device_id` / `android_id`). **Bez tokenu** – sesja tworzona dla zalogowanego użytkownika tabletu.  
  - Backend tworzy/aktualizuje sesję (bez pola token), tworzy lub wiąże formularz intake, zwraca `**intake_form_id`**.  
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
  - **Wybór kolejki** – np. `GET /api/v1/daily-queues?queue_date=today` (lista dzisiejszych kolejek do wyboru na tablecie).
  - **Lista pacjentów w wybranej kolejce** – np. `GET /api/v1/daily-queues/{id}/entries`.
  - **POST** `queue-entries/{id}/sessions` – wybór pacjenta, rozpoczęcie sesji (bez tokenu), zwrot `intake_form_id`.
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
  |------------------------------------>|                             |
  |                                     |     [Tablet zalogowany:     |
  |                                     |      rola TABLET]           |
  |                                     |<----------------------------|
  |                                     |  GET daily-queues?queue_date=today
  |                                     |---------------------------->|
  |                                     |  Rejestracja wybiera kolejkę (tap)
  |                                     |  GET daily-queues/{id}/entries
  |                                     |<----------------------------|
  |                                     |  Lista pacjentów → wybór pacjenta (tap)
  |                                     |  POST queue-entries/{id}/sessions (bez tokenu)
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

1. **Rola TABLET (lub WAITING_ROOM)** – rozszerzenie `StaffRole`, rejestracja użytkowników „tablet” (każdy tablet = osobne konto), RBAC: dostęp tylko do wyboru kolejki, listy pacjentów w kolejce, sesje, formularz (bez edycji danych pacjenta).
2. **Wybór kolejki na tablecie** – recepcja na tablecie wybiera kolejkę z listy dzisiejszych kolejek (np. `GET /api/v1/daily-queues?queue_date=today`). **Brak twardego przypisania** tabletu do kolejki w panelu recepcji.
3. **Lista pacjentów w wybranej kolejce** – `GET /api/v1/daily-queues/{id}/entries` z danymi pacjenta i statusem – dostępny dla roli TABLET.
4. **POST queue-entries/{id}/sessions** – zmiana: sesja **bez tokenu** (migracja usuwa token z modelu). Dla tabletu: opcjonalne przekazanie `android_id`; zwrot `intake_form_id`. Tablet (TABLET) może wywoływać obok RECEPTION/ADMIN.
5. **Wycofanie tokenu** – migracje bazy: usunięcie pola tokenu (np. `token_hash`) z `PatientFormSession` i zależnej logiki; usunięcie z pozostałej dokumentacji. Autoryzacja w flow tabletu: `request.user.role == TABLET` + intake_form w wybranej kolejce.
6. **Ekran weryfikacji danych pacjenta** – GET danych pacjenta powiązanego z queue_entry / intake_form (tylko odczyt; bez możliwości edycji z tabletu).
7. **Endpoint zgód** – `PUT /api/v1/intake-forms/{id}/consents`, dostępny dla roli TABLET (i RECEPTION/ADMIN).
8. **Upload podpisu** – endpoint zapisu/uploadu podpisu dla intake (submit wymaga podpisu); opcjonalnie zapis `android_id` przy sesji/submicie.
9. **TabletDevice** – migracja: **usunąć** pola `name` i `device_code`, wprowadzić **tylko `android_id`** (unikalny). Auto-dopisanie: przy pierwszym logowaniu tabletu z nieznanym `android_id` tworzony jest wpis TabletDevice.

Reszta (anamneza, submit, stany wpisu/formularza) bez zmian; zmienia się sposób wejścia (wybór kolejki na tablecie → lista pacjentów → weryfikacja danych → formularz) oraz zakres (jedna przychodnia).