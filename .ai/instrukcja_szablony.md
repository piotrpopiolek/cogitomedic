# Instrukcja: Szablony lekarza i presety grup

## Gdzie się definiuje presety grup

**Presety grup** („Ulubiony preset grupy”) są elementami **szablonu lekarza** (Doctor Text Template). Definiuje się je w:

1. **Panelu admina Django**: **Medical → Szablony lekarza** (Doctor templates), w polu **„Ulubione grup zmian”** (`lesion_group_favorites`),  
   **albo**
2. **Przez API**: `POST /api/v1/doctor-text-templates` / `PATCH /api/v1/doctor-text-templates/{id}` z ciałem zawierającym `lesion_group_favorites`.

Poniżej opis jest dla **admina** (krok po kroku w UI).

---

## Krok 1: Wejście w szablony lekarza

- Zaloguj się do panelu admina (Cogitomedica).
- W menu po lewej w sekcji **Medical** wybierz **„Szablony lekarza”** (Doctor templates).

---

## Krok 2: Nowy szablon albo edycja istniejącego

- **Nowy preset w nowym szablonie**: kliknij **„Dodaj szablon lekarza”** (Add doctor template).
- **Dodanie presetów do istniejącego**: otwórz wybrany szablon (klik w nazwę).

---

## Krok 3: Wypełnienie pól obowiązkowych szablonu

Uzupełnij m.in.:

- **Nazwa** – np. „Szablon kontrolny”.
- **Język szablonu** (`template_locale`) – np. `de-DE`, `pl-PL`, `en-GB`.
- **Treść szablonu** (`template_body`) – dowolna treść (może być pusta jeśli korzystasz głównie z presetów).

Bez tego szablon się nie zapisze.

---

## Krok 4: Wpisanie presetów w polu „Ulubione grup zmian”

W formularzu szablonu znajdź pole **„Ulubione grup zmian”** (w bazie: `lesion_group_favorites`).

**W panelu admina (z włączonym JavaScript):** dostępny jest **edytor wizualny**: lista kart (presetów) z przyciskami „Dodaj preset” i „Usuń”. W każdej karcie uzupełniasz:
- **Nazwa** – np. „Zmiana kontrolna”,
- **Ocena kliniczna** (clinical assessment) – wybór z listy,
- **Ryzyko złośliwości** (malignancy risk) – wybór z listy,
- **Cechy dermatoskopowe** – wielokrotny wybór (checkboxy),
- **Tekst (sekcja 8)** – treść wstawiana do pola „8. Text (generiert / bearbeitet)” po „Zastosuj”.

Edytor synchronizuje dane z polem JSON poniżej. **Bez JavaScript** możesz edytować bezpośrednio **pole tekstowe JSON** – wpisujesz poprawną listę JSON (format jak poniżej). Zapis w bazie pozostaje w tym samym formacie; presety można też definiować przez API.

### Format jednego presetu (dla edycji JSON / API)

```json
{
  "name": "Nazwa presetu (np. Zmiana kontrolna)",
  "dermatoscopic_features": ["ASYMMETRY", "MULTICOLOR"],
  "clinical_assessment": "CONTROL_NEEDED",
  "malignancy_risk": "LOW_SUSPICION",
  "text": "Tekst do sekcji 8 (generiert / bearbeitet) – dowolny opis zmiany."
}
```

### Przykład całego pola „Ulubione grup zmian” (lista kilku presetów)

```json
[
  {
    "name": "Zmiana kontrolna",
    "dermatoscopic_features": ["ASYMMETRY", "MULTICOLOR"],
    "clinical_assessment": "CONTROL_NEEDED",
    "malignancy_risk": "LOW_SUSPICION",
    "text": "Zmiana kontrolna do obserwacji."
  },
  {
    "name": "Unauffällig",
    "dermatoscopic_features": [],
    "clinical_assessment": "UNREMARKABLE",
    "malignancy_risk": "NO_SUSPICION",
    "text": "Unauffällige Läsion."
  }
]
```

### Dozwolone wartości

- **`dermatoscopic_features`** – lista z kodów (można pustą `[]`):  
  `ASYMMETRY`, `IRREGULAR_BORDER`, `INHOMOGENEOUS_PIGMENTATION`, `MULTICOLOR`, `ATYPICAL_PIGMENT_NETWORK`, `IRREGULAR_GLOBULES`, `IRREGULAR_DOTS`, `STRUCTURELESS_AREAS`, `ATYPICAL_VASCULAR_STRUCTURES`, `REGRESSION_AREAS`.
- **`clinical_assessment`** – dokładnie jeden z:  
  `UNREMARKABLE`, `SLIGHTLY_ATYPICAL`, `CONTROL_NEEDED`, `SUSPICIOUS`.
- **`malignancy_risk`** – dokładnie jeden z:  
  `NO_SUSPICION`, `LOW_SUSPICION`, `CANNOT_EXCLUDE`.
- **`name`** – 1–120 znaków.
- **`text`** – 1–5000 znaków (treść wstawiana do pola „8. Text (generiert / bearbeitet)” po „Zastosuj”).

---

## Krok 5: Zapisywanie szablonu

Kliknij **„Zapisz”** (albo „Zapisz i dodaj nowy” / „Zapisz i kontynuuj edycję”).  
Jeśli JSON w „Ulubione grup zmian” jest poprawny, zapis przejdzie bez błędu.

---

## Krok 6: Użycie w formularzu Befund

- W panelu **Lekarz** otwórz dokument (Befund).
- W **sekcji 4** dodaj (lub wybierz) **grupę zmian** (Läsion Nr. / numer(y) w grupie).
- W tej samej grupie w polu **„Ulubiony preset grupy”** wybierz z listy **„Wybierz szablon…”** najpierw **szablon** (jeśli jest ich kilka), a potem **preset** (np. „Zmiana kontrolna”).
- Kliknij **„Zastosuj”**.

Efekt: w tej grupie zmian ustawią się zaznaczenia cech dermatoskopowych, ocena kliniczna, ocena ryzyka złośliwości oraz tekst w polu „8. Text (generiert / bearbeitet)” – zgodnie z definicją presetu.

---

## Alternatywa: definiowanie przez API

Presety grup można też definiować przez API, bez ręcznego wpisywania JSON w adminie:

- **Utworzenie szablonu z presetami:**  
  `POST /api/v1/doctor-text-templates`  
  Body (JSON): `name`, `template_locale`, `template_body`, **`lesion_group_favorites`** (lista obiektów jak wyżej), opcjonalnie `is_global`, `is_active` itd.

- **Modyfikacja presetów:**  
  `PATCH /api/v1/doctor-text-templates/{id}`  
  Body: np. tylko `"lesion_group_favorites": [ ... ]`.

Struktura każdego elementu `lesion_group_favorites` jest taka sama jak w JSON w polu „Ulubione grup zmian” w adminie.

---

## Mapowanie pól w adminie (szablon lekarza)

| Pole na formularzu   | Pole w modelu            | Opis |
|----------------------|--------------------------|------|
| Ulubione grup zmian  | `lesion_group_favorites` | Presety grup (sekcja 4 + 8) |
| Treść szablonu       | `template_body`          | Główna treść; używana w sekcji 9 (jeden preset), prefix przy generowaniu |
| Jest globalne        | `is_global`              | Szablon dla wszystkich (tylko admin) |
| Czy aktywny         | `is_active`              | Czy szablon jest dostępny na liście |

---

## Funkcja pola „Treść szablonu” (`template_body`)

- **W panelu lekarza (sekcja 9):** Treść szablonu jest traktowana jako jeden preset do wklejenia w sekcję 9 („Ulubiony tekst sekcji 9”).
- **Przy generowaniu tekstu Befund:** Opcjonalnie `template_body` jest dopisywany na początku wygenerowanego podsumowania (nagłówek / wstęp).
