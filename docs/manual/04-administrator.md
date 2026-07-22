# Instrukcja: Administrator

Administrator ma **pełny dostęp do panelu administracyjnego** (`/admin/`), zarządza użytkownikami, konfiguracją placówek, importami pacjentów (XLSX), tłumaczeniami oraz działaniem systemu. Ten dokument wskazuje, gdzie szukać procedur.

## Wymagania wstępne

- Konto z grupą **Admin** i dostępem do panelu administracyjnego.
- Pamiętaj, że zmiany w danych i tłumaczeniach wpływają na pacjentów i personel.

---

## 1. Logowanie i nawigacja

Wejdź na **`/admin/`** — masz dostęp do wszystkich głównych sekcji systemu.

![Strona główna panelu administracyjnego](/docs/manual/assets/screenshots/admin-01-index.png)

---

## 2. Użytkownicy personelu

**Ścieżka:** Users → Staff users (nazwa zależna od tłumaczenia).

### 2.1 Tworzenie konta

- Użyj formularza dodawania; grupa konta określa rolę (np. recepcja, lekarz, admin, tablet, manager, **księgowość**).
- Konto administratora musi mieć dostęp do panelu.
- Przypisz placówki lekarzowi i personelowi, jeśli ich widoczność ma być ograniczona do wybranych miejsc.

![Edycja użytkownika — grupy i kliniki](/docs/manual/assets/screenshots/admin-02-staff-user.png)

### 2.2 Filtrowanie listy po roli

Na liście użytkowników możesz filtrować konta według roli.

---

## 3. Placówki, gabinety, kolejki

- **Placówka** — kod, nazwa oraz ustawienia domyślne importu.
- **Consulting room** — gabinet przypisany do placówki.
- **Kolejka dzienna / wpis kolejki** — jak w instrukcji recepcji; administrator zwykle widzi pełny zakres danych.
- **Pacjent — korekta danych osobowych** (imię, nazwisko, telefon, data urodzenia, adres, placówki itd.): procedura krok po kroku i skutki dla portalu wyników / PDF z laboratorium — [01-rejestracja.md § 4.1](01-rejestracja.md).

---

## 3a. Autoryzacja ścieżki papierowej (T1)

**Role:** tylko **Admin** lub **Manager**.

**Adres:** **`/admin/paper-intake/`** (menu Unfold / link z panelu admina).

- **Lista wpisów:** wybierz wpis kolejki w statusie oczekiwania.
- **Strona wpisu:** wykonaj autoryzację lub cofnięcie autoryzacji z podaniem powodu.
- Szczegóły integracyjne dla działu IT są opisane w dokumentacji technicznej.

**Instrukcja operacyjna (krok po kroku, diagram):** [04-administrator-paper-intake.md](04-administrator-paper-intake.md) oraz [paper_intake_flow.md](paper_intake_flow.md).

---

## 4. Urządzenia tabletów (`TabletDevice`)

W **Reception → Tablet devices** (lub równoważna ścieżka):

- **Przypisz Clinic site** do urządzenia — inaczej tablet na `/tablet/` nie zobaczy kolejek (komunikat o nieprzypisanym tablecie).
- Identyfikacja urządzenia jest powiązana z logowaniem. W razie problemów skontaktuj się z IT.

---

## 5. Tłumaczenia interfejsu i PDF

Teksty widoczne w interfejsie i PDF są edytowane bezpośrednio w panelu administracyjnym.

Szczegóły techniczne dla działu IT: [`.ai/translations-admin-runbook.md`](../../.ai/translations-admin-runbook.md)

Przed zmianą produkcyjną:

- sprawdź **placeholdery** w stringach,
- bezpieczeństwo treści publikowanych w systemie,
- spójność kluczy między językami DE/EN/PL.

---

## 6. Szablony tekstu lekarza

Szablony prywatne vs publiczne w obrębie kliniki — zasady uprawnień w warstwie serwisu i dokumentacja:

- [`.ai/instrukcja_szablony.md`](../../.ai/instrukcja_szablony.md)

---

## 7. Import pacjentów z pliku XLSX

Z poziomu listy **Daily queues** dostępny jest **Import pacjentów z pliku XLSX**. Po wgraniu plik jest przetwarzany w tle.

- Używaj importu plikowego tylko z **zaufanych źródeł** i po weryfikacji kolumn.
- Niezgodne wiersze są raportowane w historii importu.

![Import XLSX z poziomu kolejek (ten sam widok używany przez recepcję)](/docs/manual/assets/screenshots/admin-03-import-xlsx.png)

---

## 8. Integracje i błędy

- W razie statusów błędów sprawdź szczegóły i skontaktuj się z działem IT.
- Dashboard recepcji (`/admin/reception-dashboard/`) — skrót dla personelu; administrator może używać tego samego + pełnych widoków modeli.
- Scenariusze: [SC-006](scenariusze.md#sc-006), [SC-013](scenariusze.md#sc-013), [SC-024](scenariusze.md#sc-024), [SC-026](scenariusze.md#sc-026), [SC-027](scenariusze.md#sc-027); indeks: [scenariusze.md](scenariusze.md).

---

## 9. Monitoring

Narzędzia monitoringu są opisane w [README.md](../../README.md). Nie są częścią codziennej pracy recepcji, ale administrator IT powinien mieć do nich dostęp.

---

## 10. Dokumentacja techniczna

- Dokumentacja techniczna dla IT: [`.ai/api-plan-pl.md`](../../.ai/api-plan-pl.md)

---

## 11. Konto kierownicze (grupa `Manager`)

Grupa **Manager** służy do nadzoru operacyjnego bez pełni praw administratora.

- Logowanie do panelu administracyjnego i dashboardu recepcji tak jak uprawniony personel recepcji.
- Panel lekarza (`/doctor/`) jest dostępny także dla Managera w zakresie nadzoru.
- Czas trwania sesji dla Managera jest taki sam jak dla pozostałych ról personelu.

## 12. Dobre praktyki

- **Kopie zapasowe** i testy zmian na stagingu przed produkcją.
- **Minimalne uprawnienia:** nie przyznawaj konta administratora bez potrzeby; rolę Manager dawaj tylko tam, gdzie naprawdę jest potrzebny nadzór; konto **Accounting** tylko dla osób z księgowości.
- **Audyt:** zmiany krytycznych ustawień dokumentuj w systemie ticketów placówki.

## 13. Konto księgowości (grupa `Accounting`)

Grupa **Accounting** służy wyłącznie do odczytu raportu rozliczeniowego Befund — bez dostępu do pacjentów, kolejek ani innych ekranów administracyjnych.

- Utwórz konto staff z grupą **Accounting** (przez panel Users → Staff users albo API `POST /api/v1/staff-users` z `role=ACCOUNTING`). Konto musi mieć `is_staff=True`, żeby zalogować się do Unfold.
- Grupa **nie** dostaje uprawnień Django ModelAdmin — dostęp wynika z dedykowanych widoków (`accounting_report_access_ok` w `apps/operations/accounting_access.py`).
- Po zalogowaniu w menu bocznym: sekcja **Księgowość** → **Raport tygodniowy** (`/admin/accounting/report/`).
- Zakres danych: **wszystkie placówki** (jak u administratora). Manager widzi ten sam raport, ale tylko dla przypisanych placówek.
- Szczegóły kolumn, filtrów dat i eksportu: [08-ksiegowosc-raport.md](08-ksiegowosc-raport.md).

Powiązane: [Przegląd (m.in. tabela ról)](00-przeglad.md), [Recepcja](01-rejestracja.md), [Lekarz](03-doktor.md), [Raport księgowości](08-ksiegowosc-raport.md), [Ścieżka papierowa — procedura](04-administrator-paper-intake.md), [Ścieżka papierowa — diagram](paper_intake_flow.md), [Scenariusze operacyjne](scenariusze.md).
