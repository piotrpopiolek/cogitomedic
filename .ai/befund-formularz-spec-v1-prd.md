# Formularz Befund: od tworzenie_befund.txt do wersji PRD

Dokument traktuje **tworzenie_befund.txt** jako pierwszą wersję części medycznej (checklist kliniczny) i mapuje ją na wymagania PRD oraz kontrakt `medical_payload` v1 z db-plan/api-plan, aby dojść do **jednolitego formularza w wersji PRD**.

---

## 1. Źródła


| Źródło                                    | Opis                                                                                                                                            |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **tworzenie_befund.txt**                  | Pierwsza wersja: opis formularza z checkboxami (DE), sekcje 1–10, przykłady Textbausteine per zmiana i podsumowanie.                            |
| **PRD §3.3, §5 (US-008, US-009, US-019)** | Zasada „baza, nie klatka”; struktura Befund; generowanie tekstu z checkboxów (edytowalne); podsumowanie zbiorcze (edytowalne); własne szablony. |
| **db-plan §5.2, api-plan §4.4**           | Kontrakt `medical_payload` v1: pola globalne, `lesions[]`, kody enum, `generated_text` / `edited_text`.                                         |


---

## 2. Mapowanie: tworzenie_befund.txt → PRD / medical_payload v1

Każda sekcja z **tworzenie_befund.txt** jest mapowana na pole w `medical_payload` i na zachowanie UI (single/multi-select, edytowalny tekst).


| Nr w tworzenie_befund.txt | Treść (DE)                                                                           | Typ wyboru                                | Pole w medical_payload v1                           | Uwagi PRD                                                                                                     |
| ------------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **1**                     | Untersuchungsumfang: Intimbereich nicht untersucht, Mundschleimhaut nicht untersucht | Mehrfachauswahl                           | `examination_scope[]`                               | Enumy: `INTIMATE_AREA_NOT_EXAMINED`, `ORAL_MUCOSA_NOT_EXAMINED`.                                              |
| **2**                     | Hauttyp nach Fitzpatrick (I–VI, II–III, nicht eindeutig)                             | Nur eine Auswahl                          | `fitzpatrick_type`                                  | Enum: `TYPE_I` … `TYPE_VI`, `TYPE_II_III`, `UNDETERMINED`.                                                    |
| **3**                     | Gesamtbeurteilung der Bildanalyse: keine / kontrollbedürftige Hautveränderungen      | Nur eine Auswahl                          | `overall_image_assessment`                          | `NO_CONTROL_NEEDED` | `CONTROL_NEEDED`.                                                                       |
| **4**                     | Läsionen (Wideodermatoskop – Gruppierung)                                             | Grupy: numery z urządzenia (np. 2, 3, 13)  | `lesions[]` z `lesion_numbers`                      | Jedna grupa = jedna lista numerów (`lesion_numbers: [2, 3, 13]`) + wspólny opis (cechy, ocena, ryzyko, tekst). |
| **5**                     | Dermatoskopische Merkmale (Asymmetrie, Begrenzung, …)                                | Mehrfachauswahl **pro Gruppe**            | `lesions[].dermatoscopic_features[]`                | 10 enumów (ASYMMETRY, IRREGULAR_BORDER, … REGRESSION_AREAS).                                                  |
| **6**                     | Klinisch-dermatoskopische Einschätzung (Unauffällig … Suspekt)                       | Nur eine **pro Gruppe**                   | `lesions[].clinical_assessment`                     | `UNREMARKABLE`, `SLIGHTLY_ATYPICAL`, `CONTROL_NEEDED`, `SUSPICIOUS`.                                          |
| **7**                     | Einschätzung des Malignitätsrisikos (Kein / Niedriger / Kann nicht ausgeschlossen)   | Nur eine **pro Gruppe**                   | `lesions[].malignancy_risk`                         | `NO_SUSPICION`, `LOW_SUSPICION`, `CANNOT_EXCLUDE`.                                                            |
| **5–7 → Text**            | Generierter Text **pro Gruppe** (Textbaustein)                                       | —                                         | `lesions[].generated_text`, `lesions[].edited_text` | System generuje z cech + oceny; lekarz edytuje → `edited_text`. Do PDF: `edited_text` lub `generated_text`.   |
| **Krok 3**                | Zusammenfassung für den Gesamtbefund (automatisch)                                   | —                                         | `summary_generated_text`, `summary_edited_text`     | Generowanie zbiorcze z listy zmian; edytowalne.                                                               |
| **9**                     | Ärztliche Empfehlung (3/6 Monate, bei Veränderung, keine kurzfristige)               | Mehrfachauswahl                           | `recommendations[]`                                 | Enumy: `FOLLOWUP_3_MONTHS`, `FOLLOWUP_6_MONTHS`, `PROMPT_VISIT_ON_CHANGE`, `NO_SHORT_TERM_FOLLOWUP_REQUIRED`. |
| **10**                    | Ärztliche Gesamteinschätzung (kein höhergradiger / kann nicht ausgeschlossen)        | Nur eine Auswahl                          | `final_assessment`                                  | `NO_HIGH_GRADE_SUSPICION`, `HIGH_GRADE_CANNOT_BE_EXCLUDED`.                                                   |


W ten sposób **cały formularz z tworzenie_befund.txt** ma dokładne odwzorowanie w kontrakcie `medical_payload` v1 z db-plan.

---

## 3. Formularz w wersji PRD – spójna specyfikacja

Poniżej formularz Befund w wersji PRD: ten sam zestaw pól co w tworzenie_befund.txt, plus zachowania wymagane przez PRD (generowanie tekstu, edycja, szablony).

### 3.1. Zasady (z PRD)

- **Baza, nie klatka:** Tekst z checkboxów jest **bazą wyjściową**; lekarz **może i powinien** go edytować przed zatwierdzeniem. Może dopisywać własne teksti (wolne pole, własne szablony).
- **Dwa poziomy generowania:** (1) tekst **per zmiana** (z cech dermatoskopowych + oceny klinicznej + ryzyka), (2) **podsumowanie zbiorcze** z listy zmian. Oba edytowalne.
- **Zapis:** W `medical_payload` zapisywane są: wybory strukturyzowane (checkboxy/enumy) **oraz** `generated_text` / `edited_text` (per zmiana i dla podsumowania). Do PDF/archiwum trafia wersja po edycji (`edited_text` jeśli jest, inaczej `generated_text`).
- **Szablony (US-019):** Lekarz może wskazać szablon bazowy przy generowaniu; system zapisuje `template_context` (template_id, name, locale). Zmiana szablonu nie modyfikuje historycznych wersji.

### 3.2. Struktura formularza (ekran lekarza)

Kolejność i grupowanie zgodne z tworzenie_befund.txt; etykiety DE/EN z db-plan (lub tworzenie_befund.txt dla DE).

1. **Untersuchungsumfang** (multi)
  Checkboxy: Intimbereich nicht untersucht, Mundschleimhaut nicht untersucht  
   → `examination_scope[]`
2. **Hauttyp nach Fitzpatrick** (single)
  Radio: I, II, III, IV, V, VI, II–III, nicht eindeutig bestimmbar  
   → `fitzpatrick_type`
3. **Gesamtbeurteilung der Bildanalyse** (single)
  Radio: Keine kontrollbedürftigen … / Kontrollbedürftige … erkennbar  
   → `overall_image_assessment`
4. **Läsionen (Wideodermatoskop)** (grupy)
  Lekarz wpisuje numery zmian z urządzenia i grupuje je. Jedna grupa = jedna lista `lesion_numbers` (np. 2, 3, 13) + sekcje 5–7 + pole tekstowe (wygenerowany + edytowany).  
   UI: przycisk „+ Gruppe hinzufügen”, w każdej grupie pole „Numery w grupie” (np. 2, 3, 13).
5. **Dermatoskopische Merkmale** (multi, **pro Gruppe**)
  Checkboxy: Asymmetrie, Unregelmäßige Begrenzung, … Regressionsareale  
   → `lesions[].dermatoscopic_features[]`
6. **Klinisch-dermatoskopische Einschätzung** (single, **pro Gruppe**)
  Radio: Unauffällig, Leicht atypisch, Kontrollbedürftig, Suspekt  
   → `lesions[].clinical_assessment`
7. **Einschätzung des Malignitätsrisikos** (single, **pro Gruppe**)
  Radio: Kein Malignitätsverdacht, Niedriger, Kann nicht ausgeschlossen  
   → `lesions[].malignancy_risk`
8. **Text pro Gruppe (edytowalny)**
  System wypełnia na podstawie 5–7 (`generated_text`); lekarz edytuje w polu → `edited_text`. Do PDF trafia wersja po edycji.
9. **Zusammenfassung Gesamtbefund (edytowalny)**
  System generuje podsumowanie z listy zmian (`summary_generated_text`); lekarz edytuje → `summary_edited_text`.
10. **Ärztliche Empfehlung** (multi)
  Checkboxy: Verlaufskontrolle 3/6 Monate, bei Veränderung zeitnah, keine kurzfristige Kontrolle  
    → `recommendations[]`
11. **Ärztliche Gesamteinschätzung** (single)
  Radio: Kein höhergradiger Malignitätsverdacht / Kann nicht sicher ausgeschlossen  
    → `final_assessment`

Dodatkowo (PRD): opcjonalny **wybór szablonu** (własny/globalny) przy generowaniu tekstu oraz **wolne pole / własne dopiski** – bez zmiany kontraktu v1 (można trzymać w `edited_text` lub w przyszłym rozszerzeniu).

### 3.3. Przepływ w UI

1. Lekarz wybiera opcje (1–7, 10, 11) i ewentualnie wybrane zmiany (4) z cechami i ocenami (5–7).
2. Front pokazuje pola tekstowe (per zmiana i podsumowanie); lekarz wpisuje/edyuje. Zapis szkicu (PUT draft) zapisuje `medical_payload` z `edited_text` / `summary_edited_text` (oraz opcjonalnie `generated_text` z szablonu przy zapisie).
3. Publikacja: do PDF/archiwum trafia tekst końcowy (edited lub generated). Idempotentność publikacji zgodnie z US-009.

---

## 4. Różnice: „pierwsza wersja” vs „wersja PRD”


| Aspekt        | tworzenie_befund.txt (pierwsza wersja)  | Wersja PRD                                                                                           |
| ------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Zawartość pól | Te same sekcje 1–10, te same opcje (DE) | Identycznie + pole wyboru szablonu i swoboda dopisywania                                             |
| Tekst         | Przykładowe Textbausteine (opis)        | Zapis w `medical_payload`: `generated_text` + `edited_text` (per zmiana i summary)                   |
| Edycja        | Nie opisana wprost                      | Wymagana możliwość edycji wygenerowanego tekstu przed zatwierdzeniem                                 |
| Szablony      | Brak                                    | Opcjonalny szablon lekarza przy generowaniu (US-019)                                                 |
| Język         | Niemiecki w dokumencie                  | DE/EN wg db-plan; `authoring_locale` w payload                                                       |
| API / DB      | —                                       | Pełny kontrakt `medical_payload` v1 (db-plan, api-plan); walidacja przy zapisie (draft).             |


Formularz w wersji PRD to więc **ten sam formularz** co w tworzenie_befund.txt, z dodanymi zachowaniami: generowanie → edycja → zapis wersji i publikacja, oraz opcjonalnie szablony.

---

## 5. Rekomendacje implementacyjne

1. **Backend:**
  - Wprowadzić **pełną walidację Pydantic** dla `medical_payload` v1 (enumy, `lesions[]` z `lesion_numbers` niepuste i bez duplikatów, reguły: `lesions` puste tylko przy `overall_image_assessment=NO_CONTROL_NEEDED`).
2. **Frontend:**
  - Formularz w kolejności sekcji 1–11 jak wyżej; etykiety DE/EN z jednego słownika (db-plan lub osobny plik tłumaczeń).
  - Pola tekstowe (per zmiana i podsumowanie); zapis draft z pełnym `medical_payload`.
3. **PRD / dokumentacja:**
  - W PRD (lub w osobnym „Spec formularza Befund”) można wskazać, że **formularz kliniczny** jest zdefiniowany w tworzenie_befund.txt, a **kontrakt danych i zachowania systemowe** w db-plan §5.2 i api-plan §4.4 oraz w tym dokumencie.

---

## 6. Podsumowanie

- **tworzenie_befund.txt** = pierwsza wersja części medycznej: pełna lista pól (1–10) i przykłady tekstów.
- **Formularz w wersji PRD** = ten sam formularz + generowanie tekstu (per zmiana + podsumowanie), edytowalne teksty, zapis `generated_text`/`edited_text` w `medical_payload`, opcjonalne szablony i zasada „baza, nie klatka”.
- Mapowanie 1:1 między sekcjami tworzenie_befund.txt a polami `medical_payload` v1 umożliwia jednolitą implementację backendu (walidacja przy draft) i frontu (checkboxy/radio + pola tekstowe edytowalne).

