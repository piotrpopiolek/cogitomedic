---
name: ""
overview: ""
todos: []
isProject: false
---

# Plan: Edycja tłumaczeń przez administrację (wersja po decyzjach)

## Decyzje architektoniczne (ustalone)

1. **Jedno źródło prawdy: wyłącznie DB**
  Kod nie przechowuje ani nie dostarcza fallbacków tłumaczeń runtime.
2. **Kategorie biznesowe tłumaczeń**: `doctor`, `reception`, `waiting_room`.
3. **Właściciel merytoryczny i decyzyjny**: **Administrator**.
4. **Wymaganie bezpieczeństwa**: polityka anty-XSS dla tłumaczeń.
5. **Wymaganie spójności PDF**: język publikowanego PDF musi być trwały i audytowalny per wersja dokumentu.

---

## Cel

Umożliwić administracji edycję tłumaczeń DE/EN/PL przez Django Admin, z zachowaniem:

- spójności między workerami,
- walidacji kluczy i placeholderów,
- bezpieczeństwa renderowania,
- pełnej identyfikowalności języka publikacji PDF.

---

## Stan obecny (krótko)

- Tłumaczenia są rozsiane w kodzie (`doctor_i18n.py`, `pdf_builder.py`).
- PDF przy publikacji bazuje dziś na `medical_payload.authoring_locale` wersji dokumentu.
- Jest ryzyko dryfu i brak typowanej walidacji kluczy.

---

## Architektura docelowa (DB-only)

### 1) Model danych

**A. `TranslationKey` (rejestr typowanych kluczy)**

- `key` (unikalny, np. `doctor.rec_followup_3`, `doctor.pdf_label.summary`)
- `category` (`doctor` | `reception` | `waiting_room`)
- `description` (opis biznesowy)
- `is_html_allowed` (bool, default `false`)
- `allowed_placeholders` (JSON array, np. `["patient_name", "date"]`)
- `status` (`ACTIVE`, `DEPRECATED`)

**B. `TranslationValue`**

- FK do `TranslationKey`
- `language_code` (`de`, `en`, `pl`)
- `value` (TextField)
- unikalność `(translation_key, language_code)`
- pola audytowe: `updated_by`, `updated_at`

**C. (PDF) rozszerzenie wersji dokumentu**

- `MedicalDocumentVersion.publish_locale` (CharField, np. `en-GB`)
- ustawiane **w momencie publikacji** i potem niemutowalne.

> Uwaga: `publish_locale` rozwiązuje ryzyko utraty informacji "w jakim języku zlecono publikację", niezależnie od późniejszych zmian tłumaczeń lub kolejnych wersji dokumentu.

### 2) Konwencja kluczy

- `doctor.*` dla panelu lekarza i PDF lekarza (np. `doctor.rec_followup_3`, `doctor.pdf_label.summary`)
- `reception.*` dla recepcji
- `waiting_room.*` dla waiting room

Wszystkie klucze są zarejestrowane w `TranslationKey`, a nie "wolnym stringiem".

---

## Walidacja typów kluczy i placeholderów

### Problem

`String-key model` bez kontraktu daje literówki i błędy runtime.

### Rozwiązanie

1. **Twardy rejestr kluczy (`TranslationKey`)**
  - `TranslationValue` nie może istnieć bez klucza z rejestru.
  - Brak możliwości wpisania „nowego” klucza ad hoc z admina bez jego zdefiniowania.
2. **Walidator placeholderów przy zapisie**
  - Parser wyciąga placeholdery z `value` (np. `{name}`, `{date}`).
  - Zapis odrzucany, gdy:
    - są placeholdery spoza `allowed_placeholders`,
    - brakuje placeholderów wymaganych przez kontrakt klucza (jeśli oznaczone jako required).
3. **Test kontraktowy kluczy**
  - testy sprawdzają, że wszystkie klucze używane przez kod istnieją w `TranslationKey`.
  - testy sprawdzają komplet języków (`de`, `en`, `pl`) dla kluczy aktywnych.

---

## Globalna spójność cache (multi-worker / multi-instance)

### Problem

Lokalna invalidacja w jednym procesie nie wystarczy.

### Rozwiązanie

1. **Wspólny backend cache** (Redis/Memcached), nie local-memory.
2. **Versioned cache keys**:
  - trzymamy globalny licznik wersji per kategoria+język, np. `i18n:v:doctor:pl`.
  - klucz danych zawiera wersję: `i18n:data:doctor:pl:v42`.
3. **Po zapisie tłumaczenia**:
  - transakcyjnie zwiększamy `i18n:v:{category}:{language}`.
  - wszystkie instancje automatycznie zaczną czytać nową wersję.
4. **Bezpieczny fallback techniczny**:
  - przy awarii cache czytamy bezpośrednio z DB (nigdy z kodowych słowników).

---

## Spójność języka PDF przy publikacji (analiza + decyzja)

### Obecnie

- Flow JS robi `PUT /draft` z `authoring_locale`, potem `POST /publish`.
- Outbox generuje PDF dla opublikowanej wersji.
- Język jest obecnie pochodną payloadu wersji.

### Ryzyko

- Brak jawnego, dedykowanego pola audytowego `publish_locale`.
- Przy analizie incydentu trudniej udowodnić „w jakim języku zlecono publikację”.

### Docelowo

1. W `publish_document_version(...)` zapisujemy `publish_locale` na `MedicalDocumentVersion`.
2. Outbox PDF używa `**version.publish_locale`** jako źródła języka.
3. `publish_locale` jest immutable po publikacji.
4. W audit event zapisujemy `publish_locale` + `published_by_user_id`.

To gwarantuje, że:

- lekarz A może opublikować EN, lekarz B DE,
- język każdej wersji zostaje trwale przypisany i nie ginie.

---

## Polityka bezpieczeństwa XSS dla tłumaczeń

1. **Domyślnie tylko plain text**
  - `is_html_allowed=false` dla większości kluczy.
2. **Renderowanie**
  - backend/templates: standardowe escapowanie (autoescape on),
  - frontend JS: preferować `textContent` zamiast `innerHTML`.
3. **Jeśli HTML potrzebny wyjątkowo**
  - tylko dla kluczy z `is_html_allowed=true`,
  - sanitizacja whitelistą (np. dopuszczone: `b`, `strong`, `i`, `br`, `ul`, `li`),
  - usuwanie atrybutów eventowych i URL-i `javascript:`.
4. **Walidacja przy zapisie w adminie**
  - jeśli `is_html_allowed=false`, zapis odrzucany przy wykryciu tagów HTML.

---

## Django Admin (operacyjnie)

- `TranslationKeyAdmin`: zarządzanie kontraktem kluczy (kategoria, placeholdery, html policy, status).
- `TranslationValueAdmin`: edycja wartości per język.
- Filtry: `category`, `language_code`, `status`.
- Audyt: kto zmienił i kiedy.

Rola odpowiedzialna za poprawność: **Administrator**.

---

## Plan wdrożenia

1. Dodać modele `TranslationKey`, `TranslationValue` + migracje.
2. Dodać `publish_locale` do `MedicalDocumentVersion` + migracja.
3. Napisać jednorazowy skrypt migracyjny: przenieść wszystkie aktualne tłumaczenia z kodu do DB.
4. Przepiąć runtime:
  - `get_doctor_ui`, `get_fitzpatrick_choices`, etykiety PDF -> odczyt wyłącznie z DB.
5. Dodać walidację placeholderów i polityki HTML.
6. Dodać globalną strategię cache versioning + invalidation.
7. Dodać testy:
  - kompletność kluczy/języków,
  - walidacja placeholderów,
  - XSS policy,
  - trwałość `publish_locale` i zgodność języka wygenerowanego PDF.

---

## Kryteria akceptacji

1. Brak odwołań runtime do słowników tłumaczeń w kodzie.
2. Każdy klucz używany przez UI/PDF istnieje w `TranslationKey`.
3. Zmiana tłumaczenia jest widoczna na wszystkich instancjach bez restartu.
4. Każdy opublikowany PDF ma przypisany i audytowalny `publish_locale`.
5. W testach bezpieczeństwa tłumaczenia nie mogą wstrzyknąć aktywnego HTML/JS tam, gdzie nie jest to dozwolone.

