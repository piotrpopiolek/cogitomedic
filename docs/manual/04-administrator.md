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

- Użyj formularza dodawania; **grupy** (`Reception`, `Doctor`, `Admin`, `Tablet`) określają rolę.
- **Admin** musi mieć **is_staff=True** — system może to wymuszać przy zapisie.
- Pole **clinic_sites** (wiele do wielu): przypisz placówki dla **lekarza** i personelu, którego zakres widoczności danych ograniczają placówki.

![Edycja użytkownika — grupy i kliniki](/docs/manual/assets/screenshots/admin-02-staff-user.png)

### 2.2 Filtrowanie listy po roli

Na liście użytkowników można dodać parametr URL **`?role=RECEPTION`** (lub `DOCTOR`, `ADMIN`, `TABLET`) — filtrowanie po grupie (implementacja w `StaffUserAdmin`).

---

## 3. Placówki, gabinety, kolejki

- **Clinic site** — kod, nazwa, m.in. ustawienia domyślne dla **importu PDF** (`pdf_import_default_consulting_room`, `pdf_import_shift_code`).
- **Consulting room** — gabinet przypisany do placówki.
- **Daily queue / Queue entry** — jak w instrukcji recepcji; administrator widzi wszystkie zakresy (nie ogranicza go scope placówki, o ile nie zmieniono polityki).

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

## 11. Dobre praktyki

- **Kopie zapasowe** i testy zmian na stagingu przed produkcją.
- **Minimalne uprawnienia:** personelowi nie przypisuj grupy Admin bez potrzeby.
- **Audyt:** zmiany krytycznych ustawień dokumentuj w systemie ticketów placówki.

Powiązane: [Przegląd](00-przeglad.md), [Recepcja](01-rejestracja.md), [Lekarz](03-doktor.md).
