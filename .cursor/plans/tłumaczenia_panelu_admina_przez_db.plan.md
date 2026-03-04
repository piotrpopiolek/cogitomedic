---
name: Tłumaczenia panelu admina przez DB
overview: Wdrożenie mechanizmu tłumaczeń interfejsu panelu administracyjnego (opartego o Django Unfold i strukturę modeli) przy użyciu istniejących tabel `TranslationKey` i `TranslationValue` w bazie danych, zamiast standardowych plików .po.
todos:
  - id: admin-dicts
    content: Stworzenie pliku `cogitomedica/admin_i18n.py` ze słownikami tłumaczeń (DE/EN/PL) dla nawigacji panelu administracyjnego oraz kluczowych modeli.
    status: pending
  - id: admin-seeding
    content: Aktualizacja komendy `load_default_translations.py` o wczytywanie kategorii `ADMINISTRATION`.
    status: pending
  - id: admin-db-proxy
    content: Implementacja `db_gettext_lazy(key, default)` w `apps/core/translation_service.py` wraz z optymalizacją pobierania per-request.
    status: pending
  - id: admin-unfold-sidebar
    content: Użycie `db_gettext_lazy` w konfiguracji `UNFOLD["SIDEBAR"]` w pliku `settings.py`.
    status: pending
  - id: admin-models-verbose
    content: Aplikacja `db_gettext_lazy` w wybranych parametrach `verbose_name` dla najważniejszych modeli i metod `@admin.display`.
    status: pending
isProject: false
---

# Plan dodania tłumaczeń panelu administracyjnego do bazy danych

Zgodnie z założeniem o kontynuacji istniejącego podejścia (tłumaczenia w DB zamiast plików `.po`), zrealizujemy to poprzez stworzenie leniwej funkcji tlumaczącej, zasilenie bazy kluczami dla admina oraz modyfikację konfiguracji modeli i Unfold.

## Krok 1: Stworzenie słowników startowych dla panelu

1. Utworzymy nowy plik `cogitomedica/admin_i18n.py`.
2. Zdefiniujemy w nim słowniki (np. `ADMIN_UI_DE`, `ADMIN_UI_EN`, `ADMIN_UI_PL`), które będą zawierać bazowe teksty:
  - Nawigacja / Sidebar (np. "Panele", "Rejestracja", "Użytkownicy").
  - Nazwy poszczególnych modułów i modeli (np. "Patient", "ClinicSite").
  - Kluczowe nazwy pól (jeśli chcemy tłumaczyć również kolumny tabel).

## Krok 2: Zasilenie bazy danych (Seeding)

1. Edytujemy `apps/core/management/commands/load_default_translations.py`.
2. Dodamy import słowników z `admin_i18n.py` i rozbudujemy komendę tak, aby zapisywała te klucze w bazie.
3. Klucze otrzymają kategorię `TranslationCategory.ADMINISTRATION`.

## Krok 3: Leniwe proxy do tłumaczeń z bazy (`db_gettext_lazy`)

1. Ponieważ mechanizm Django Admin rozwiązuje stringi "w locie" przy renderowaniu dziesiątek kolumn, obecna funkcja `get_translation_map` (która za każdym razem odpytuje tabelę wersji) mogłaby wywołać problem *N+1 zapytań* dla pojedynczego widoku.
2. W `apps/core/translation_service.py` zaimplementujemy funkcję proxy (np. `db_gettext_lazy(key: str, default: str)`), bazującą na `django.utils.functional.lazy`.
3. Aby uniknąć degradacji wydajności, odczyt z bazy będzie minimalizowany przy pomocy zoptymalizowanego cachowania per request.

## Krok 4: Zastosowanie tłumaczeń w konfiguracji Django Unfold

1. W `cogitomedica/settings.py` w bloku `UNFOLD["SIDEBAR"]` zastąpimy zahardkodowane na sztywno polskie stringi (np. `"title": "Lekarz"`) funkcją `db_gettext_lazy`.

## Krok 5: Wpięcie tłumaczeń w modele (opcjonalnie dla najważniejszych widoków)

1. W najważniejszych modelach dodamy atrybuty `verbose_name` oraz `verbose_name_plural` do klasy `Meta` z wykorzystaniem `db_gettext_lazy` (np. dla klas `StaffUser`, `Patient`, `DailyQueue`, `MedicalDocument` itd.).
2. Zaktualizujemy nazwy kolumn niestandardowych (zdekorowanych przez `@admin.display`) w plikach `admin.py`, by również używały `db_gettext_lazy` dla parametru `description`.

