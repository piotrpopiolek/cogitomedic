# Code Review – Findings and Recommendations

Data przeglądu: 2025-03-11  
Priorytety: (1) Błędy logiczne i bugi, (2) Bezpieczeństwo, (3) Wydajność, (4) Utrzymanie, (5) Styl.

---

## 1. Naprawione w ramach przeglądu

### 1.1 GET /api/v1/staff-users?role=… – FieldError (KRYTYCZNY – naprawione)

**Problem:** Model `StaffUser` nie ma już pola `role` (usunięte w migracji `0007_remove_role`). Role są określane przez grupy Django (`Doctor`, `Reception`, `Admin`, `Tablet`). Wywołanie `StaffUser.objects.filter(role=role)` przy podaniu parametru `role` w GET powodowało `FieldError`.

**Rozwiązanie:** W `apps/users/api_views.py` filtr po roli zastąpiono filtrem po grupie: `qs.filter(groups__name=group_name).distinct()`, z walidacją `role in {"RECEPTION", "DOCTOR", "ADMIN", "TABLET"}` i zwrotem 400 przy nieprawidłowej wartości.

---

## 2. Bezpieczeństwo – rekomendacje

### 2.1 Brak scope’u clinic_site w API formularzy intake (IDOR)

**Lokalizacja:** `apps/intake/api_views.py` – `intake_form_detail_view`, `intake_form_consents_view`, `intake_form_signature_view`, `intake_form_anamnesis_view`, `intake_form_submit_view`.

**Problem:** Endpointy przyjmują `intake_form_id` (UUID) i nie sprawdzają, czy formularz należy do kolejki w placówce przypisanej użytkownikowi (RECEPTION/TABLET). Użytkownik z rolami RECEPTION/TABLET, który zna UUID formularza z innej placówki, może go odczytać/modyfikować.

**Rekomendacja:** Przed wywołaniem `get_intake_form_context` / `save_intake_*` dodać sprawdzenie zakresu: np. pobrać `PatientIntakeForm` z `queue_entry__daily_queue__clinic_site_id` i zweryfikować, że `clinic_site_id` jest w `get_scoped_clinic_site_ids(request.user)`. W przeciwnym razie zwracać 404 (bez ujawniania, że formularz istnieje).

### 2.2 Walidacja clinic_site_ids w POST /api/v1/staff-users/{id}/clinic-sites

**Lokalizacja:** `apps/users/api_views.py` – `staff_user_clinic_sites_view` (POST).

**Problem:** `user.clinic_sites.set(body.clinic_site_ids)` przyjmuje dowolne UUID. Nieistniejące ID są po cichu pomijane przez Django M2M, więc użytkownik może dostać mniej placówek niż wysłał, bez informacji o błędzie. Brak też sprawdzenia, że ID odnoszą się do aktywnych `ClinicSite`.

**Rekomendacja:** Przed `.set()`: zweryfikować, że wszystkie `body.clinic_site_ids` istnieją w `ClinicSite.objects.filter(id__in=body.clinic_site_ids)` i ewentualnie że `is_active=True`. Jeśli lista się nie zgadza – zwrócić 400 z czytelnym komunikatem.

### 2.3 ALLOWED_HOSTS w produkcji

**Lokalizacja:** `cogitomedica/settings.py`.

**Problem:** W README jest informacja, że w prod **musi** być ustawione `ALLOWED_HOSTS`, ale w kodzie przy `ENVIRONMENT == "prod"` wymuszany jest tylko `SECRET_KEY`. Puste `ALLOWED_HOSTS` w prod skutkuje odrzuceniem wszystkich requestów, ale bez jasnego błędu startu aplikacji.

**Rekomendacja:** Dla `ENVIRONMENT == "prod"` dodać:  
`if not ALLOWED_HOSTS: raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")`  
(po zbudowaniu listy `ALLOWED_HOSTS` z env).

### 2.4 Walidatory haseł wyłączone

**Lokalizacja:** `cogitomedica/settings.py` – `AUTH_PASSWORD_VALIDATORS` jest pustą listą (wszystkie wpisy zakomentowane).

**Rekomendacja:** Włączyć przynajmniej `MinimumLengthValidator` i `CommonPasswordValidator` w prod (np. pod warunkiem `ENVIRONMENT == "prod"`), aby ograniczyć słabe hasła kont personelu.

---

## 3. Logika i przypadki brzegowe

### 3.1 Retry processing – puste body

**Lokalizacja:** `apps/medical/api_views.py` – `medical_document_retry_processing_view`.

**Obserwacja:** Przy `JSONDecodeError` ustawiane jest `body = RetryProcessingRequest()` (domyślne wartości). Zachowanie jest spójne z „retry bez opcjonalnego reason” – OK.

---

## 4. Wydajność

### 4.1 Lista użytkowników – brak prefetchu grup

**Lokalizacja:** `apps/users/api_views.py` – `staff_users_view` (GET).

**Rekomendacja:** Przy filtrowaniu po `groups__name` zapytanie jest poprawne. Jeśli w przyszłości w serializacji pojawią się inne dane z grup, warto dodać `.prefetch_related("groups")`, aby uniknąć N+1.

### 4.2 Audit events – filtrowanie po JSONB (metadata)

**Lokalizacja:** `apps/operations/api_views.py` – `audit_events_view` (filtr dla DOCTOR: `metadata__assigned_doctor_id`, `metadata__actor_user_id`).

**Obserwacja:** Filtrowanie po polu JSON/JSONB może być wolniejsze. W razie problemów z wydajnością rozważyć indeks GIN na `metadata` lub wydzielone kolumny do filtrowania.

---

## 5. Utrzymanie i spójność

### 5.1 Obrona przed path traversal w retention cleanup

**Lokalizacja:** `apps/outbox/services.py` – `_try_delete_file()`.

**Obserwacja:** `pdf_local_path` jest ustawiane tylko przez aplikację (generatory PDF), więc ryzyko path traversal jest niskie. Dla obrony w głąb warto przed `path.unlink()` sprawdzić, że `path.resolve()` jest pod `Path(settings.MEDIA_ROOT).resolve()` (i ewentualnie że nie wychodzi poza media root).

### 5.2 Spójność testów z modelem użytkownika

**Rekomendacja:** Dodać test integracyjny dla GET `/api/v1/staff-users?role=DOCTOR` (i ewentualnie innych ról), aby zabezpieczyć przed regresją po zmianach w modelu (np. ponownym usunięciu pola `role` lub zmianie sposobu przypisywania ról).

---

## 6. Podsumowanie

| Priorytet | Status | Działanie |
|-----------|--------|-----------|
| Bug: filtr `role` w staff-users | **Naprawione** | Filtr po `groups__name`, walidacja roli |
| IDOR w API intake form | Do zrobienia | Dodać scope po clinic_site w endpointach formularzy |
| Walidacja clinic_site_ids (POST clinic-sites) | Do zrobienia | Sprawdzenie istnienia (i opcjonalnie is_active) przed `.set()` |
| ALLOWED_HOSTS w prod | Do zrobienia | `ImproperlyConfigured` gdy puste w prod |
| Walidatory haseł | Do zrobienia | Włączyć w prod |
| Path traversal w retention | Opcjonalne | Sprawdzenie ścieżki pod MEDIA_ROOT |
| Test GET staff-users?role= | Do zrobienia | Nowy test w apps.users.api_tests |

Dokument można uzupełniać przy kolejnych przeglądach i linkować z README lub z wewnętrznej dokumentacji procesu jako „Code review findings”.
