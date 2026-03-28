---
name: Dostep rejestrator moduly
overview: Przygotuję plan RBAC dla roli RECEPTION, spójny z PRD, planem API i istniejącym planem dla lekarza. Plan zdefiniuje moduły dostępne i niedostępne dla recepcji, reguły object-level oraz luki/ryzyka wymagające doprecyzowania przed implementacją.
todos:
  - id: rbac-matrix
    content: Zdefiniować docelową macierz dostępu RECEPTION do modułów i endpointów API.
    status: pending
  - id: object-scope
    content: Ustalić reguły object-level dla kolejek, pacjentów, sesji, urządzeń i importów.
    status: pending
  - id: boundary-decisions
    content: Opisać granice między RECEPTION a TABLET, DOCTOR i ADMIN oraz domknąć niejednoznaczności dokumentacyjne.
    status: pending
isProject: false
---

# Plan dostępu rejestratora (rola RECEPTION) do modułów

Plan opracowany na podstawie: [.ai/prd.md](.ai/prd.md), [.ai/api-plan.md](.ai/api-plan.md), [.ai/api-plan-pl.md](.ai/api-plan-pl.md), [.ai/db-plan.md](.ai/db-plan.md), [.ai/staff-api-contract.md](.ai/staff-api-contract.md), [README.md](README.md), [.cursor/plans/plan-dostep-lekarz-moduly.plan.md](.cursor/plans/plan-dostep-lekarz-moduly.plan.md), [.cursor/plans/plan_proces-poczekalni.plan.md](.cursor/plans/plan_proces-poczekalni.plan.md).

## Cel

Określenie, do jakich modułów, zasobów API i encji danych powinien mieć dostęp użytkownik z rolą `RECEPTION`, aby obsłużyć pełny proces recepcji i poczekalni: logowanie, tworzenie i edycję pacjentów, zarządzanie kolejkami i wpisami, uruchamianie sesji formularza na tablecie, importy oraz uproszczony monitoring operacyjny.

## Założenia źródłowe

- Źródłem prawdy dla docelowego zakresu jest dokumentacja produktowa i kontrakty API, nie bieżące rozjazdy implementacyjne.
- `RECEPTION` odpowiada za operacyjny przepływ recepcji i poczekalni, ale nie za część medyczną dokumentu, słowniki systemowe ani operacje utrzymaniowe niskiego poziomu.
- `RECEPTION` działa wyłącznie w obrębie przypisanych placówek (`clinic_site`) i wszystkie listy oraz operacje mutujące powinny respektować ten scope.
- `TABLET` pozostaje rolą minimalną, ograniczoną do obsługi aktualnego formularza intake.
- `DOCTOR` pozostaje właścicielem modułu dokumentu medycznego.
- `ADMIN` pozostaje właścicielem użytkowników, słowników, pełnego audytu, outboxu, retencji i metryk.

## Docelowy zakres dostępu RECEPTION

### 1. Auth

- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`

Recepcja ma standardowy dostęp do logowania i odczytu własnej sesji.

### 2. Kolejki dzienne i wpisy kolejki

- `GET /daily-queues`
- `POST /daily-queues`
- `PATCH /daily-queues/{id}`
- `GET /daily-queues/{id}/entries`
- `POST /daily-queues/{id}/entries`
- `GET /queue-entries/{id}`
- `PATCH /queue-entries/{id}`
- `DELETE /queue-entries/{id}`

To jest główny moduł pracy rejestratora. Recepcja tworzy kolejki, dodaje pacjentów do dnia pracy, aktualizuje status wpisów i obsługuje sytuacje operacyjne w poczekalni.

### 3. Pacjenci

- `GET /patients`
- `POST /patients`
- `GET /patients/{id}`
- `PATCH /patients/{id}`

Recepcja ma dostęp do tworzenia i aktualizacji pacjentów w zakresie przypisanych placówek (w tym ścieżka manualna bez `Doctolib Patient ID`, zgodnie z regułami unikalności w modelu).

### 4. Lokacje i gabinety

- `GET /clinic-sites`
- `GET /consulting-rooms`

Dostęp tylko do odczytu, jako słowniki pomocnicze do tworzenia i filtrowania kolejek. CRUD tych zasobów pozostaje po stronie `ADMIN`.

### 5. Urządzenia tabletowe

- `GET /tablet-devices`
- `POST /tablet-devices`
- `GET /tablet-devices/{id}`
- `PATCH /tablet-devices/{id}`
- `DELETE /tablet-devices/{id}`
- opcjonalnie operacyjnie `POST /tablet-devices/{id}/heartbeat`

Recepcja zarządza pulą urządzeń tabletowych wykorzystywanych w poczekalni.

### 6. Sesje formularza i start procesu na tablecie

- `POST /queue-entries/{id}/sessions`

Recepcja może przygotować formularz dla pacjenta i przekazać tablet do wypełnienia. Standardowy panel recepcji nie powinien być głównym miejscem edycji formularza intake; za właściwe wypełnienie formularza odpowiada `TABLET`.

### 7. Importy

- `POST /imports/patients`
- `GET /imports/batches`
- `GET /imports/batches/{id}`
- `GET /imports/batches/{id}/errors`

Recepcja ma pełny dostęp operacyjny do importów dziennych oraz do przeglądu wyników importu.

### 8. Uproszczony dashboard operacyjny

Recepcja powinna mieć dostęp do prostego dashboardu aplikacyjnego pokazującego:

- status importów,
- zaległe dokumenty wymagające interwencji,
- błędy krytyczne widoczne biznesowo,
- bezpieczne komunikaty o awariach procesu publikacji.

Ten widok nie powinien opierać się na surowym dostępie do pełnego `outbox_event` ani pełnego `audit_event`, tylko na zawężonym read modelu lub dedykowanym widoku UI.

## Moduły bez dostępu dla RECEPTION

- `staff-users` i przypisania klinik użytkowników,
- `consent-definitions`,
- `anamnesis-definitions`,
- `medical-documents`, `medical-document-versions`, `doctor-text-templates`,
- pełne `audit-events`,
- `outbox-events`, retry outboxu, ręczne przetwarzanie outboxu,
- ręczne uruchamianie retencji,
- `observability/metrics`.

Recepcja nie powinna mieć dostępu do modułów administracyjnych, medycznych ani techniczno-utrzymaniowych, nawet jeśli obecna implementacja miejscami to dopuszcza.

## Granice między rolami

- `RECEPTION` zarządza pacjentem, kolejką, importem i uruchomieniem procesu intake, ale wyłącznie w obrębie przypisanych placówek.
- `TABLET` obsługuje wyłącznie wybór kolejki/pacjenta oraz sam formularz intake w zakresie aktualnej sesji.
- `DOCTOR` pracuje wyłącznie na dokumencie medycznym i jego wersjach.
- `ADMIN` zarządza konfiguracją, personelem, operacjami technicznymi i pełną obserwowalnością.

## Docelowa polityka object-level dla RECEPTION

### 1. `clinic-sites`

- `ALLOW-READ`: recepcja widzi wyłącznie placówki przypisane do użytkownika przez relację zakresu (`staff_user_clinic_site` lub równoważny mechanizm autoryzacji).
- `DENY`: brak dostępu do placówek spoza przypisanego zakresu.
- `DENY-WRITE`: recepcja nie tworzy, nie edytuje i nie usuwa placówek.

### 2. `consulting-rooms`

- `ALLOW-READ`: recepcja widzi wyłącznie gabinety należące do przypisanych placówek.
- `DENY`: brak dostępu do gabinetów spoza przypisanych placówek.
- `DENY-WRITE`: recepcja nie tworzy, nie edytuje i nie usuwa gabinetów.

### 3. `daily-queues`

- `ALLOW`: kolejka należy do placówki w zakresie recepcji.
- `DENY`: kolejka poza zakresem placówki użytkownika.

### 4. `queue-entries`

- `ALLOW`: wpis należy do kolejki dostępnej dla recepcji.
- `DENY`: wpis poza zakresem widocznych kolejek.

### 5. `patients`

- `ALLOW-READ`: pacjent należy do placówki obsługiwanej przez recepcję lub występuje w kolejce tej placówki.
- `ALLOW-WRITE`: tworzenie i aktualizacja tylko w kontekście placówek obsługiwanych przez recepcję.
- `DENY`: pacjent poza zakresem placówek użytkownika.

### 6. `patient sessions`

- `ALLOW`: sesja tworzona dla wpisu kolejki dostępnego dla recepcji.
- `DENY`: próba uruchomienia sesji dla obcego wpisu lub nieaktywnego urządzenia.

### 7. `tablet-devices`

- `ALLOW-READ`: recepcja widzi urządzenia dostępne dla przypisanych placówek.
- `ALLOW-WRITE`: recepcja może aktywować, dezaktywować i utrzymywać urządzenia używane w przypisanych placówkach.
- `DENY`: brak dostępu do urządzeń spoza zakresu placówek użytkownika.
- `UWAGA`: obecny model danych nie ma jawnego `clinic_site_id` na `tablet_device`; przed implementacją trzeba dopiąć albo relację placówki do urządzenia, albo spójny mechanizm mapowania urządzenia do zakresu recepcji.

### 8. `imports`

- `ALLOW`: batch uruchomiony przez recepcję lub dotyczący placówki z jej zakresem.
- `DENY`: batch spoza zakresu użytkownika, jeśli system będzie wieloplacówkowy.

## Encje danych kluczowe dla roli RECEPTION

- `staff_user`
- `staff_user_clinic_site`
- `patient`
- `patient_clinic_site`
- `clinic_site`
- `consulting_room`
- `daily_queue`
- `queue_entry`
- `tablet_device`
- `patient_form_session`
- `patient_intake_form` jako kontekst sesji, nie jako główny moduł edycji panelu recepcji
- `patient_import_batch`
- `patient_import_error`
- wybrane agregaty read-only dla dashboardu operacyjnego

## Niejednoznaczności do domknięcia przed implementacją

### 1. Scope recepcji po placówce

To jest założenie przyjęte w tym planie jako stan docelowy: recepcja nie działa globalnie, tylko w obrębie przypisanych placówek. Przed implementacją trzeba jedynie doprecyzować techniczny sposób egzekwowania tego scope w każdym endpointzie i modelu pomocniczym.

### 2. Zakres recepcji w intake

Kontrakty API jasno dają recepcji `POST /queue-entries/{id}/sessions`, ale część dokumentów sugeruje też pomocniczy udział recepcji w dalszym flow intake. Plan powinien przyjąć domyślnie:

- panel recepcji nie wystawia pełnej edycji intake,
- głównym klientem dla endpointów intake jest `TABLET`,

### 3. Rozjazd dokumentacja vs implementacja

W dokumentacji mogą pozostawać rozjazdy względem retry outboxu. Plan przyjmuje jako stan docelowy:

- surowy outbox i retry tylko dla `ADMIN`,
- recepcja widzi jedynie bezpieczny status biznesowy w dashboardzie.

## Proponowana struktura docelowego dokumentu

- `Cel`
- `Podsumowanie RBAC`
- `Moduły z dostępem RECEPTION`
- `Moduły bez dostępu`
- `Polityka object-level`
- `Encje DB i relacje`
- `TODO przed implementacją`
- `Podsumowanie końcowe`

## TODO przed implementacją

1. Zamrozić kontrakt RBAC dla `RECEPTION` w API i frontendzie staff.
2. Dopisać formalną macierz `ALLOW/DENY` dla `daily-queues`, `queue-entries`, `patients`, `sessions`, `imports`, `tablet-devices`.
3. Domknąć techniczny model scope po `clinic_site` dla `RECEPTION` oraz ustalić, jak traktować tablety w modelu wieloplacówkowym.
4. Rozdzielić docelowy dashboard recepcji od surowych endpointów outbox i audit.
5. Ujednolicić dokumentację z implementacją tam, gdzie dziś `RECEPTION` ma szersze uprawnienia niż wynikają z PRD i planów API.

## Podsumowanie

Docelowo `RECEPTION` powinna mieć pełny dostęp operacyjny do modułów recepcji i poczekalni w obrębie przypisanych placówek: pacjenci, kolejki, wpisy, sesje, tablety, importy i uproszczony monitoring. Nie powinna mieć dostępu do części medycznej, słowników administracyjnych ani narzędzi utrzymaniowych klasy outbox, retention i pełne metryki.