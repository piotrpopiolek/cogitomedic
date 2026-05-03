# Instrukcja: Administrator (rola Admin)

Administrator ma **pełny dostęp do Django Admin** (`/admin/`), zarządzanie użytkownikami, konfiguracją placówek, importami pacjentów (XLSX), tłumaczeniami oraz modelem operacyjnym (outbox, zadania). Ten dokument **nie zastępuje** runbooków technicznych — wskazuje, gdzie szukać procedur.

## Wymagania wstępne

- Konto z grupą **Admin** i flagą **staff** (wymagana do Django Admin).
- Zrozumienie, że zmiany w **danych produkcyjnych** i **tłumaczeniach** wpływają na pacjentów i personel — działaj według zmiany (change management) placówki.

---

## 1. Logowanie i nawigacja

Wejdź na **`/admin/`** — masz dostęp do wszystkich zarejestrowanych modeli (Reception, Users, Medical, Intake, Outbox, Core, itd.).

![Strona główna Django Admin](/docs/manual/assets/screenshots/admin-01-index.png)

---

## 2. Użytkownicy personelu (`StaffUser`)

**Ścieżka:** Users → Staff users (nazwa zależna od tłumaczenia).

### 2.1 Tworzenie konta

- Użyj formularza dodawania; **grupy** (`Reception`, `Doctor`, `Admin`, `Tablet`, `Manager`) określają rolę.
- **Admin** musi mieć **is_staff=True** — system może to wymuszać przy zapisie.
- Pole **clinic_sites** (wiele do wielu): przypisz placówki dla **lekarza** i personelu, którego zakres widoczności danych ograniczają placówki.

![Edycja użytkownika — grupy i kliniki](/docs/manual/assets/screenshots/admin-02-staff-user.png)

### 2.2 Filtrowanie listy po roli

Na liście użytkowników można dodać parametr URL **`?role=RECEPTION`** (lub `DOCTOR`, `ADMIN`, `TABLET`, `MANAGER`) — filtrowanie po grupie (implementacja w `StaffUserAdmin`).

---

## 3. Placówki, gabinety, kolejki

- **Clinic site** — kod, nazwa, m.in. ustawienia domyślne dla **importu PDF** (`pdf_import_default_consulting_room`, `pdf_import_shift_code`).
- **Consulting room** — gabinet przypisany do placówki.
- **Daily queue / Queue entry** — jak w instrukcji recepcji; administrator widzi wszystkie zakresy (nie ogranicza go scope placówki, o ile nie zmieniono polityki).

---

## 3a. Autoryzacja ścieżki papierowej (T1)

**Role:** tylko **Admin** lub **Manager** (jak w API).

**Adres:** **`/admin/paper-intake/`** (menu Unfold / link z panelu admina).

- **Hub:** wybór wpisu kolejki w statusie **oczekiwania** z kolejek dziennych z ostatnich 30 dni (lista obejmuje wszystkie placówki — spójnie z wejściem na stronę wpisu).
- **Strona wpisu:** autoryzacja lub cofnięcie autoryzacji z polem powodu (10–500 znaków), zgodnie z regułami domeny (czas wizyty + 3 h, brak dokumentu, brak cyfrowej ankiety w statusie wysłanym itd.).
- **API (integracje / klient HTTP):** `POST` / `DELETE` na `/api/v1/queue-entries/<uuid>/paper-intake-authorization` — tam nadal obowiązuje **zakres placówek** (`get_scoped_clinic_site_ids`), inaczej niż w HTML pod `/admin/paper-intake/`.

Szczegóły modelu i przepływu: plan [`.cursor/plans/dokument_medyczny_bez_ankiety.plan.md`](../../.cursor/plans/dokument_medyczny_bez_ankiety.plan.md) (sekcja o T1/T2).

---

## 4. Urządzenia tabletów (`TabletDevice`)

W **Reception → Tablet devices** (lub równoważna ścieżka):

- **Przypisz Clinic site** do urządzenia — inaczej tablet na `/tablet/` nie zobaczy kolejek (komunikat o nieprzypisanym tablecie).
- Identyfikacja urządzenia wiąże się z logowaniem (Android ID / API) — szczegóły w README projektu.

---

## 5. Tłumaczenia interfejsu i PDF

Teksty UI i PDF są utrzymywane **w bazie danych** i edytowalne w Django Admin — **brak fallbacków z kodu w runtime**.

**Runbook:** [`.ai/translations-admin-runbook.md`](../../.ai/translations-admin-runbook.md)

Przed zmianą produkcyjną:

- sprawdź **placeholdery** w stringach,
- politykę **anty-XSS** (treści z admina mogą trafiać do HTML),
- spójność kluczy między językami DE/EN/PL.

---

## 6. Szablony tekstu lekarza

Szablony prywatne vs publiczne w obrębie kliniki — zasady uprawnień w warstwie serwisu i dokumentacja:

- [`.ai/instrukcja_szablony.md`](../../.ai/instrukcja_szablony.md)

---

## 7. Import pacjentów z pliku XLSX

Z poziomu listy **Daily queues** dostępny jest **Import pacjentów z pliku XLSX** (`import-xlsx/`). Wgrany plik trafia do kolejki zadań w tle; typ wsadu w bazie jest ustawiany jako **DAILY_FILE_IMPORT** (implementacja w `enqueue_patient_xlsx_import`).

- Używaj importu plikowego tylko z **zaufanych źródeł** i po weryfikacji kolumn.
- Niezgodne wiersze są raportowane w batchu / błędach importu — sprawdzaj **Patient import batches** i **Patient import errors**.

![Import XLSX z poziomu kolejek (ten sam widok używany przez recepcję)](/docs/manual/assets/screenshots/admin-03-import-xlsx.png)

---

## 8. Outbox i integracje

- **Outbox events** — kolejka zdarzeń (GENERATE_PDF, HIDRIVE_UPLOAD, SMS_SEND). Przy statusach **FAILED** / **DEAD_LETTER** diagnozuj z logami i runbookiem alertów.
- Dashboard recepcji (`/admin/reception-dashboard/`) — skrót dla personelu; administrator może używać tego samego + pełnych widoków modeli.

---

## 9. Monitoring (infrastruktura)

Metryki Prometheus, Grafana, Alertmanager — opis w [README.md](../../README.md) sekcja *Monitoring services*. Nie są częścią codziennej pracy recepcji, ale administrator IT powinien mieć dostęp do dashboardów.

---

## 10. API i dokumentacja

- Swagger: `/api/docs/swagger/` (wymaga zalogowania staff).
- Plany API: [`.ai/api-plan-pl.md`](../../.ai/api-plan-pl.md)

---

## 11. Konto kierownicze (grupa `Manager`)

Grupa **Manager** służy do **nadzoru operacyjnego** bez pełni praw **Admin** (migracja `0013_create_manager_role_group` w `users` przypisuje ograniczony zestaw uprawnień modeli: recepcja, kolejki, import XLSX, podgląd dokumentów medycznych itd.).

- Logowanie do **Django Admin** i **reception-dashboard** jak uprawniony personel recepcji w tym scope.
- Panel **Lekarz** (`/doctor/`) oraz odpowiadające **REST API v1** (np. `GET/POST /api/v1/medical-documents` i podkatalogi) — konto `Manager` ma te same role w dekoratorach co lekarz i admin w module medycznym (pełen widok kolejki / nadzór; mutacje nadal ograniczają uprawnienia Django, np. brak `change_medicaldocument` w migracji grupy).
- Czas trwania **sesji** (cookie) dla personelu, w tym Manager, jest taki sam jak dla pozostałych ról kadry operacyjnej (middleware sesji w `RoleBasedSessionExpiryMiddleware` — patrz ustawienia).

## 12. Dobre praktyki

- **Kopie zapasowe** i testy zmian na stagingu przed produkcją.
- **Minimalne uprawnienia:** personelowi nie przypisuj grupy Admin bez potrzeby; **Manager** tylko tam, gdzie wymagany jest nadzór wielu modułów z ograniczonym CRUD względem pełnego Admina.
- **Audyt:** zmiany krytycznych ustawień dokumentuj w systemie ticketów placówki.

Powiązane: [Przegląd (m.in. tabela ról)](00-przeglad.md), [Recepcja](01-rejestracja.md), [Lekarz](03-doktor.md).
