---
name: ""
overview: ""
todos: []
isProject: false
---

# Plan: Edycja tłumaczeń przez administrację

## Cel

Umożliwić administratorom zmianę tekstów w obsługiwanych językach (DE, EN, PL) bez edycji kodu – przez Django Admin.

## Stan obecny

- **Źródła tłumaczeń** (na stałe w kodzie):
  - `cogitomedica/doctor_i18n.py`: `DOCTOR_UI_DE/EN/PL` (~100 kluczy), `FITZPATRICK_DE/PL/EN` (8 pozycji na język).
  - `apps/medical/pdf_builder.py`: `PDF_LABELS` (nagłówki sekcji PDF: de-DE, en-GB, pl-PL).
  - `cogitomedica/tablet_i18n.py`: stringi formularza tablety (opcjonalnie w kolejnej fazie).
- **Użycie**: `get_doctor_ui(lang)`, `get_fitzpatrick_choices(lang)` w panelu lekarza i w budowniczym PDF; etykiety PDF w `pdf_builder`.

## Zakres planu

1. Faza 1: **Panel lekarza + PDF** (doctor_i18n + etykiety PDF).
2. Faza 2 (opcjonalna): rozszerzenie na tablet (tablet_i18n) i ewentualne inne obszary.

---

## Architektura (Faza 1)

### Zasada: DB z domyślnymi z kodu

- Tłumaczenia przechowywane w **modelu Django**.
- **Domyślne wartości** pozostają w kodzie (słowniki/słowniki w `doctor_i18n.py` i etykiety w `pdf_builder.py`). Są używane gdy w DB brak wpisu dla danego klucza/języka.
- Warstwa dostępu: funkcje `get_doctor_ui(lang)` / `get_fitzpatrick_choices(lang)` (oraz etykiety PDF) **najpierw** ładują z DB (z cache), **następnie** uzupełniają brakujące klucze z domyślnych z kodu. Dzięki temu:
  - nowe klucze dodane w kodzie od razu mają tekst (bez wpisów w adminie),
  - admin może nadpisać wybrane teksty bez migracji danych dla wszystkich kluczy.

### Model danych

**Opcja A (rekomendowana): jeden model `Translation`**

- Pola: `key` (CharField, np. `"rec_followup_3"`), `language_code` (CharField, max 10, np. `"de"`, `"pl"`, `"en"`), `value` (TextField).
- Unikalność: `UniqueConstraint` na `(key, language_code)`.
- Opcjonalnie: `category` (CharField, np. `"doctor_ui"`, `"fitzpatrick"`, `"pdf_label"`) – ułatwia filtrowanie w adminie i ewentualne osobne widoki.
- Zalety: prosty model, łatwa migracja danych, jeden ekran admina do wszystkich tekstów.

**Opcja B: osobny model dla Fitzpatrick**

- Np. `FitzpatrickLabel(code, language_code, label)` – tylko 8×3 = 24 wiersze. Można traktować jak „słownik Fitzpatrick” z osobnym inline w adminie. Nadal z domyślnymi z kodu.

Rekomendacja: **Opcja A** z polem `category`, aby w adminie filtrować np. tylko „doctor_ui” lub „pdf_label”. Fitzpatrick reprezentowane jako klucze typu `fitzpatrick_TYPE_I`, `fitzpatrick_TYPE_II`, … (spójnie z resztą).

### Konwencja kluczy

- **Doctor UI**: istniejące klucze z `DOCTOR_UI`_* (np. `area_name`, `rec_followup_3`).
- **Fitzpatrick**: `fitzpatrick_TYPE_I`, `fitzpatrick_TYPE_II`, …, `fitzpatrick_UNDETERMINED`.
- **PDF labels**: `pdf_label.befund`, `pdf_label.document_id`, `pdf_label.patient`, … (prefiks aby nie kolidować z doctor_ui).

Języki: `de`, `en`, `pl` (spójne z `lang` w panelu). W PDF używane są locale `de-DE`, `en-GB`, `pl-PL` – warstwa dostępu mapuje je na `de`/`en`/`pl` (już tak jest w `_authoring_locale_to_lang`).

---

## Warstwa dostępu (API dla aplikacji)

1. **Cache**
  - Klucze cache np. `translations:doctor_ui:de`, `translations:doctor_ui:pl`, … (per język i ewentualnie per kategoria).
  - TTL np. 300 s lub brak TTL z invalidacją przy zapisie w adminie (sygnał `post_save` na `Translation` – czyścimy cache dla danego języka/kategorii).
2. **get_doctor_ui(lang)**
  - Pobierz z cache; przy braku: załaduj z DB wszystkie wpisy dla `category="doctor_ui"` (lub bez kategorii jeśli key nie ma prefiksu) i `language_code=lang`.
  - Połącz: `defaults = DOCTOR_UI_DE/EN/PL[lang]`, potem `defaults.update(db_dict)`. Zwróć `defaults`.
  - Zapisz wynik w cache.
3. **get_fitzpatrick_choices(lang)**
  - Domyślna lista z kodu (FITZPATRICK_DE/PL/EN). Dla każdego (code, _) sprawdź w DB (lub w jednym słowniku z cache) wpis `fitzpatrick_{code}` dla `lang`; jeśli jest, użyj jako label.
  - Cache: można trzymać „słownik Fitzpatrick” per lang (code → label) i budować listę `[(code, label), ...]`.
4. **Etykiety PDF**
  - Obecnie `PDF_LABELS` w `pdf_builder.py` – słownik per locale (de-DE, en-GB, pl-PL).
  - Nowa funkcja np. `get_pdf_labels(locale: str) -> dict[str, str]`: domyślne z `PDF_LABELS`, nadpisania z DB (klucze `pdf_label.befund`, …), cache per locale. W `_pdf_labels(locale)` wywołać `get_pdf_labels` zamiast tylko słownika z kodu.

---

## Django Admin

- **Model**: `Translation` (key, language_code, value, opcjonalnie category).
- **TranslationAdmin**:
  - `list_display`: key, language_code, value (skrót, np. 60 znaków), category.
  - `list_filter`: language_code, category.
  - `search_fields`: key, value.
  - `list_editable`: nie dla value (TextField). Można rozważyć `value` w formularzu listy jako krótki TextField (tylko jeśli value są krótkie).
  - Grupowanie po języku: np. `list_filter` po `language_code` i przeglądanie „wszystkie DE”, „wszystkie PL”.
- **Eksport/import**: opcjonalnie `django-import-export` lub management command `dump_translations` / `load_translations` (JSON/CSV), żeby administracja mogła edytować w pliku i wgrać zbiorczo.

---

## Migracja danych (zaludnienie DB)

- **Management command** (np. `load_default_translations`):
  - Dla każdego klucza z DOCTOR_UI_DE/EN/PL wstawia `Translation(key=key, language_code=lang, value=...)` tylko jeśli wpis nie istnieje (get_or_create).
  - To samo dla FITZPATRICK_* jako `fitzpatrick_TYPE_I` itd.
  - To samo dla PDF_LABELS (klucze `pdf_label.`*).
- Uruchamiane raz po wdrożeniu; później nowe klucze w kodzie mogą być uzupełniane tym samym commandem (idempotent) lub pozostawać tylko w kodzie jako domyślne.

---

## Kroki wdrożenia (Faza 1)

1. **Model i migracja**
  - Dodać app (np. `apps.i18n` lub w istniejącej `apps.core`) model `Translation(key, language_code, value, category=None)`, unique (key, language_code). Migracje.
2. **Domyślne źródła**
  - Zachować w `doctor_i18n.py` i `pdf_builder.py` obecne słowniki jako „defaults”; nie usuwać ich.
3. **Warstwa dostępu**
  - W `cogitomedica/doctor_i18n.py` (lub w nowym modułach `apps.i18n.loader` / `apps.i18n.doctor`):
    - Funkcja `get_translations_from_db(lang, category=None)` → dict key→value (z cache).
    - Zmienić `get_doctor_ui(lang)`: merge domyślnych z kodu z dict z DB; cache.
    - Zmienić `get_fitzpatrick_choices(lang)`: domyślne z kodu, nadpisania etykiet z DB (fitzpatrick_*); cache.
  - W `apps/medical/pdf_builder.py`: dodać `get_pdf_labels(locale)` (merge PDF_LABELS z DB), użyć w `_pdf_labels()`.
4. **Invalidacja cache**
  - W adminie: w `TranslationAdmin` override `save_model` / sygnał `post_save` na `Translation` – po zapisie usunąć z cache klucze dla danego `language_code` (i ewentualnie category). Prosta funkcja `invalidate_translation_cache(lang=None, category=None)`.
5. **Admin**
  - Zarejestrować `Translation` w Django Admin; konfiguracja list_display, list_filter, search_fields.
6. **Management command**
  - `load_default_translations`: wypełnienie DB domyślnymi wartościami z kodu (get_or_create), idempotent.
7. **Testy**
  - Test że `get_doctor_ui("pl")` zwraca domyślne gdy DB puste; test że po zapisie w DB wartość się zmienia i cache jest invalidowany; test że brak klucza w DB nie powoduje błędu (fallback na kod).

---

## Faza 2 (opcjonalna)

- Rozszerzenie na `tablet_i18n`: ten sam model `Translation` z kategorią np. `"tablet_form"`; `get_form_ui_strings(form_locale)` ładuje z DB + domyślne z kodu.
- Ewentualnie osobna kategoria dla „staff” / recepcja.

---

## Ryzyka i uwagi

- **Wydajność**: Odpytywanie DB przy każdym request bez cache byłoby kosztowne – **cache jest konieczny**. Invalidation przy zapisie w adminie wystarczy.
- **Spójność**: Usunięcie klucza z kodu przy istniejących wpisach w DB – wartość z DB pozostanie (może być „osierocona”). Można okresowo czyścić wpisy bez odpowiadającego klucza w domyślnych (opcjonalny command).
- **Uprawnienia**: Tylko użytkownicy z uprawnieniami do edycji modelu `Translation` (np. superuser / grupa „Content / Translations”) powinni móc zmieniać tłumaczenia.

---

## Podsumowanie

- Jeden model **Translation(key, language_code, value, category)**.
- Domyślne wartości w kodzie; DB nadpisuje wybrane klucze; cache per język z invalidacją przy zapisie.
- Admin: listowanie/filtrowanie po języku i kategorii, wyszukiwanie, edycja value.
- Command do zaludnienia DB domyślnymi z kodu.
- Po wdrożeniu panel lekarza i PDF korzystają z tych samych tekstów co dziś, z możliwością edycji w Django Admin.

