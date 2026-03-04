---
name: Migracja RBAC na Django Groups
overview: Plan naprawczy przejścia z hardkodowanych ról na standardowe grupy Django (auth.Group), oparty o wymagania dokumentu dostępu lekarza do modułów.
todos:
  - id: migrate-groups
    content: Stworzenie Data Migration tworzącej grupy, uprawnienia i przenoszącej obecnych użytkowników z `role` do `groups`
    status: completed
  - id: helpers-api
    content: Stworzenie metod pomocniczych dla `StaffUser` (np. `.is_doctor`, `.is_reception`) i podmiana we wszystkich API views/serwisach
    status: completed
  - id: cleanup-admin
    content: Usunięcie nadpisywanych metod `has_*_permission` w plikach `admin.py` i podmiana `get_queryset`
    status: completed
  - id: remove-role-schema
    content: Usunięcie pola `role` z `StaffUser`, wygenerowanie usunięcia go w DB oraz aktualizacja `apps/users/admin.py`
    status: completed
  - id: tests-auth-backend
    content: Zaktualizowanie Backendów logowania oraz mocków w testach jednostkowych
    status: completed
isProject: false
---

# Plan naprawczy: Przejście z ról na Django Groups

Przejście z pola `StaffUser.role` na natywne grupy Django (`auth.Group`) znacznie uprości system uprawnień, wyeliminuje konieczność ręcznego nadpisywania metod `has_*_permission` w panelu administratora i będzie zgodne z dobrymi praktykami Django.

Oto kroki konieczne do zrealizowania tej zmiany:

## Faza 1: Migracja danych i definicja Grup (Data Migration)

1. **Definicja grup i uprawnień**:
  - Grupy docelowe to: `Doctor`, `Reception`, `Admin`, `Tablet`.
  - W module `apps/users` zdefiniujemy plik z listą wymaganych uprawnień dla poszczególnych ról (zgodnie z `plan-dostep-lekarz-moduly.plan.md`).
    - **Doctor**: tylko uprawnienia `view_`* dla `Patient`, `ClinicSite`, `ConsultingRoom`, `DailyQueue` oraz uprawnienia zapisu/odczytu dla `MedicalDocument` i `DoctorTextTemplate`.
    - **Reception**: pełen odczyt/zapis (np. `add_patient`, `change_patient`) dla pacjentów i kolejek.
    - **Admin**: uprawnienia na wszystkie zasoby.
2. **Migracja danych (Data Migration)**:
  - Utworzymy pustą migrację wywołując komendę na dockrze (np. `docker compose exec web python manage.py makemigrations --empty users`) (przed usunięciem pola `role`).
  - Skrypt migracyjny utworzy wymagane `Group` w bazie oraz przypisze do nich stosowne standardowe permissions (`auth.Permission`).
  - Następnie skrypt ziteruje po wszystkich istniejących użytkownikach, sprawdzi ich obecne `user.role` i doda ich do odpowiedniej grupy (`user.groups.add()`).

## Faza 2: Zmiana logiki autoryzacji w kodzie

1. **Helpery autoryzacyjne**:
  - Utworzymy w modelu `StaffUser` (lub jako osobne helpery w `users/utils.py`) properties/metody zastępujące dotychczasową rolę:

```python
     @property
     def is_doctor(self):
         return self.groups.filter(name="Doctor").exists()
     

```

1. **Czyszczenie panelu Admina (`apps/*/admin.py`)**:
  - Dzięki użyciu standardowych Permissions z grup **możemy usunąć** całą nadmiarową logikę `has_module_permission`, `has_view_permission`, `has_change_permission`, `has_add_permission`, `has_delete_permission` dla roli DOCTOR (Django zablokuje np. dodawanie pacjentów, jeśli grupa Doctor nie ma `add_patient`).
  - Zachowamy jedynie logikę `get_queryset` sprawdzającą filtry `object-level` (np. przypisania do placówek), ale zamienimy w niej warunek z `getattr(request.user, "role", None) == "DOCTOR"` na `request.user.is_doctor`.
2. **Modyfikacja widoków API**:
  - Zaktualizujemy dekoratory, Permission Classes i sprawdzanie dostępu we wszystkich plikach API (np. `apps/medical/api_views.py`, `apps/reception/api_views_split/*.py`), zmieniając `.role == "DOCTOR"` na wywołanie `.is_doctor`.
  - Zmodyfikujemy zwrotkę dla endpointów, takich jak `/auth/me`, by zwracały tablicę `groups` lub listę `roles` wyciągniętych z nazw przypisanych grup, zachowując kompatybilność z wymogami frontendu.

## Faza 3: Usunięcie starej architektury i sprzątanie

1. **Schema Migration (usunięcie `role`)**:
  - Usuniemy z definicji modelu `StaffUser` pole `role` oraz `StaffRole`.
  - Wygenerujemy nową migrację Django wykonując operacje na kontenerze dockera (np. `docker compose exec web python manage.py makemigrations`), która zrzuci to pole z bazy danych.
2. **Dostosowanie panelu użytkowników**:
  - W `apps/users/admin.py` zmienimy widok dla `StaffUser`. Wrzucimy standardowy widżet do zarządzania grupami (`filter_horizontal = ('groups',)`), by móc z poziomu panelu nadawać nowym użytkownikom odpowiednią grupę (np. Reception/Doctor).
3. **Zmiana Backendów Autoryzacji**:
  - Plik `apps/users/auth_backends.py` (`StaffRoleAdminBackend`) zostanie zaktualizowany, aby dawał pełne prawa (`has_module_perms`, `has_perm`), jeśli w grupie występuje `Admin`, ewentualnie użyjemy wprost flagi `is_superuser` lub natywnych przypisań perms.
4. **Aktualizacja testów**:
  - Zmodyfikujemy mocki i fabryki w testach integracyjnych (`tests.py`, `api_tests.py`), aby zamiast przypisywać `role=StaffRole.DOCTOR`, dodawały tworzonego testowego użytkownika do odpowiedniej grupy.

