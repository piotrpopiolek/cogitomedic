---
name: ""
overview: ""
todos: []
isProject: false
---

# Plan: poprawa UX definiowania „Ulubione grup zmian” w adminie

## Cel

Zastąpić **jedno duże pole tekstowe z surowym JSON** w formularzu szablonu lekarza (Medical → Szablony lekarza) **strukturalnym UI**: dodawanie/usuwanie presetów, wybór wartości z list (cechy dermatoskopowe, ocena kliniczna, ryzyko złośliwości), pola tekstowe dla nazwy i opisu. Bez zmiany modelu ani API, w granicach stacku z `requirements.txt` (Django 6, django-unfold, brak SPA).

---

## Stan obecny

- **Pole:** `DoctorTextTemplate.lesion_group_favorites` (JSONField, `default=list`).
- **Admin:** `DoctorTextTemplateAdmin` (Unfold) – pole wyświetlane jako domyślny textarea na surowy JSON.
- **Struktura elementu:** `name`, `dermatoscopic_features` (lista kodów), `clinical_assessment`, `malignancy_risk`, `text` – zgodnie z `FavoriteLesionGroupPreset` w `api_schemas.py` i `.ai/instrukcja_szablony.md`.
- **Dozwolone wartości** (źródło prawdy: `medical_payload_schemas.py` + instrukcja):
  - **dermatoscopic_features:** `ASYMMETRY`, `IRREGULAR_BORDER`, `INHOMOGENEOUS_PIGMENTATION`, `MULTICOLOR`, `ATYPICAL_PIGMENT_NETWORK`, `IRREGULAR_GLOBULES`, `IRREGULAR_DOTS`, `STRUCTURELESS_AREAS`, `ATYPICAL_VASCULAR_STRUCTURES`, `REGRESSION_AREAS`.
  - **clinical_assessment:** `UNREMARKABLE`, `SLIGHTLY_ATYPICAL`, `CONTROL_NEEDED`, `SUSPICIOUS`.
  - **malignancy_risk:** `NO_SUSPICION`, `LOW_SUSPICION`, `CANNOT_EXCLUDE`.

---

## Kierunek rozwiązania (w granicach stacku)

- **Model i API:** bez zmian – nadal jedna lista JSON w `lesion_group_favorites`.
- **Admin:** niestandardowy **widget** dla tego pola (lub niestandardowe pole formularza + widget), który:
  1. Pokazuje **listę presetów** (karty / wiersze) z przyciskami „Dodaj preset” i „Usuń”.
  2. Dla każdego presetu: **name** (input), **dermatoscopic_features** (checkboxy lub multi-select), **clinical_assessment** (select), **malignancy_risk** (select), **text** (textarea).
  3. Wartości opcji (kody + ewentualnie etykiety) pochodzą z backendu (jedno źródło: `medical_payload_schemas` lub stałe w widgecie/adminie).
  4. Przy zapisie formularza do pola trafia **ten sam JSON** co dziś (lista obiektów) – albo przez ukryty textarea uzupełniany przez JS, albo przez pole formularza zwracające listę (Django JSONField przyjmuje listę).

---

## Kroki implementacji

### 1. Źródło opcji (backend)

- Wydzielić (np. w `apps/medical/constants.py` lub w `medical_payload_schemas.py`) listy do użycia w adminie:
  - `DERMATOSCOPIC_FEATURE_CHOICES`, `CLINICAL_ASSESSMENT_CHOICES`, `MALIGNANCY_RISK_CHOICES` (pary `(kod, etykieta)` lub same kody; etykiety można brać z tłumaczeń lub z `befund_text.py`).
- Przekazać te opcje do widgetu (np. przez `widget.get_context()` lub atrybuty form field w `DoctorTextTemplateAdmin.get_form()` / `formfield_for_dbfield()`).

### 2. Niestandardowy widget

- **Klasa widgetu** (np. `LesionGroupFavoritesWidget` w `apps/medical/widgets.py`):
  - Dla wartości: czy pole ma zwracać **string (JSON)** czy **list** – spójnie z tym, jak Django JSONField w formularzu odczytuje/zapisuje wartość (z reguły już jako list/dict). Widget powinien przyjmować wartość jako listę i w `value_from_datadict` zwracać to, co form field oczekuje (lista → JSONField w modelu zapisze bez zmian).
  - **Render:** wyświetlić ukryty `<textarea name="...">` z JSON (żeby przy wyłączonym JS zapis nadal działał z surowym JSON) oraz kontener na „wizualny edytor” (div z kartami presetów).
  - Do kontenera dołączyć **dane opcji** (np. w `data-`* lub w osobnym `<script type="application/json">`), żeby JS mógł budować selecty i checkboxy.

### 3. Logika po stronie klienta (JS)

- Jeden plik JS (np. `static/admin/js/lesion_group_favorites_widget.js` lub w `apps/medical/static/...`), dołączany tylko na stronie add/change szablonu lekarza:
  - **Odczyt:** sparsować JSON z textarea, dla każdego elementu wyrenderować „kartę” presetu (name, checkboxy dla cech, select clinical, select malignancy, text).
  - **Dodaj preset:** dopisać pusty obiekt do listy, przeładować widok kart.
  - **Usuń preset:** usunąć element z listy, przeładować widok.
  - Przy każdej zmianie w polach: zbudować listę obiektów z formularza i zapisać do textarea jako `JSON.stringify(...)`.
  - Walidacja po stronie klienta opcjonalna (np. wymagane name/text, wybór co najmniej jednej wartości w selectach); nie zastępuje walidacji serwerowej.

### 4. Walidacja po stronie serwera

- W formularzu szablonu (własny `ModelForm` dla `DoctorTextTemplate` zarejestrowany w adminie) w metodzie `clean_lesion_group_favorites`:
  - Iterować po elementach listy i walidować każdy przez **Pydantic** `FavoriteLesionGroupPreset` (albo zestaw dopuszczalnych wartości z `medical_payload_schemas`).
  - W razie błędu: `raise ValidationError` z czytelnym komunikatem (np. który preset, które pole, dozwolone wartości).
- Dzięki temu nawet przy wyłączonym JS lub przy zapisie przez API dane pozostają poprawne.

### 5. Integracja w adminie

- W `DoctorTextTemplateAdmin`:
  - **formfield_for_dbfield:** dla `lesion_group_favorites` ustawić niestandardowy form field (jeśli potrzebny) i widget `LesionGroupFavoritesWidget` z przekazanymi opcjami (choices).
  - Lub **get_form** z rozszerzonym `ModelForm`, w którym pole `lesion_group_favorites` ma widget `LesionGroupFavoritesWidget` i ewentualnie własne `clean_lesion_group_favorites`.
- Upewnić się, że skrypt JS jest ładowany na stronie add/change szablonu (np. przez `Media` na adminie lub na formularzu).

### 6. Stylowanie (opcjonalnie)

- Style Unfold: użyć klas Unfold (np. karty, przyciski), żeby wygląd był spójny z panelem.
- Minimalne własne style w pliku CSS w aplikacji `medical` tylko jeśli konieczne (układ kart, odstępy).

### 7. Testy i dokumentacja

- **Testy:** jednostkowy test widgetu (render zawiera textarea + kontener, opcje w danych); test formularza – walidacja `clean_lesion_group_favorites` (poprawna lista, niepoprawny kod, puste name itd.); opcjonalnie test integracyjny admina (np. Selenium) – otwarcie formularza, dodanie presetu, zapis, odczyt.
- **Dokumentacja:** zaktualizować `.ai/instrukcja_szablony.md`: w kroku 4 opisać nowy interfejs (dodawanie presetów w formularzu, wybór z list zamiast ręcznego JSON), z informacją, że nadal można edytować/importować przez API i że zapis w bazie pozostaje w tym samym formacie.

---

## Ryzyka i ograniczenia

- **Bez JS:** użytkownik widzi textarea z JSON; zapis nadal działa. Można dodać krótką informację w help_text: „Przy włączonej obsłudze JavaScript dostępny jest edytor wizualny.”
- **Unfold:** jeśli Unfold nadpisuje szablony formularza, upewnić się, że widget jest renderowany w tym samym miejscu co zwykłe pole (np. bez dodatkowego owijania, które ukrywa textarea).
- **Tłumaczenia:** etykiety opcji (clinical_assessment, malignancy_risk, dermatoscopic_features) – jeśli mają być wielojęzyczne, podłączyć do istniejącego systemu tłumaczeń; na początek można użyć kodów lub etykiet z `befund_text.py` / `pdf_builder.py`.

---

## Podsumowanie


| Element      | Działanie                                                           |
| ------------ | ------------------------------------------------------------------- |
| Model / API  | Bez zmian                                                           |
| Źródło opcji | Stałe/choices z `medical_payload_schemas` (lub constants)           |
| Widget       | Niestandardowy widget: textarea (fallback) + div na karty presetów  |
| JS           | Jedno plik: render kart z JSON, add/remove, sync do textarea        |
| Walidacja    | `clean_lesion_group_favorites` z Pydantic / dozwolonymi wartościami |
| Admin        | `formfield_for_dbfield` / `get_form` + Media (JS/CSS)               |
| Docs         | Aktualizacja `.ai/instrukcja_szablony.md`                           |


Po realizacji planu użytkownik w adminie definiuje „Ulubione grup zmian” przez formularz z listami zamiast ręcznego wpisywania JSON, przy zachowaniu obecnego formatu danych i stacku.