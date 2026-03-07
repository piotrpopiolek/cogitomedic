# Tłumaczenia w migracjach (core)

Weryfikacja: ile kluczy i wpisów tłumaczeń trafia do bazy **wyłącznie przez migracje** (bez `load_default_translations`).

## Migracje seedujące tłumaczenia

| Migracja | Opis | Klucze (TranslationKey) | Wartości (TranslationValue) |
|----------|------|--------------------------|------------------------------|
| **0003** | Tablet consent (formularz) | 2 | 2 × 3 = **6** |
| **0004** | Admin UI (menu, modele, przyciski) | 65 | 65 × 3 = **195** |
| **0005** | Admin – przyciski (btn_save, …) | 4 | 4 × 3 = **12** |
| **0006** | Admin – menu użytkownika i motyw | 6 | 6 × 3 = **18** |
| **0007** | Admin – etykiety pól (field_*) | 6 | 6 × 3 = **18** |
| **0008** | Admin – logowanie/wylogowanie + pola modeli | 7 + 118 = **125** | 125 × 3 = **375** |
| **0009** | Aktualizacja wartości pól (administration.field_*) | 0 (tylko update) | ~121 kluczy × 3 j. |
| **0010** | Aktualizacja doctor.text_placeholder, doctor.btn_generate | 0 (tylko update) | 2 klucze × 3 j. |
| **0011** | Doctor – template_select_hint | 1 | 1 × 3 = **3** |
| **0013** | Doctor – komunikaty walidacji przed publikacją | 5 | 5 × 3 = **15** |

## Suma (tylko migracje tworzące nowe klucze)

- **Klucze:** 2 + 65 + 4 + 6 + 6 + 125 + 1 + 5 = **214**
- **Wartości:** 6 + 195 + 12 + 18 + 18 + 375 + 3 + 15 = **642**

## Kategorie

| Kategoria | Klucze z migracji |
|-----------|--------------------|
| `administration` | 0003: 0, 0004: 65, 0005: 4, 0006: 6, 0007: 6, 0008: 125 → **~206** (0008 dodaje też field_* i login_*) |
| `waiting_room` | 0003: 2 → **2** |
| `doctor` | 0011: 1, 0013: 5 → **6** |

## Uwagi

- **0009** i **0010** nie tworzą nowych kluczy; aktualizują istniejące wpisy `TranslationValue` (np. po zmianie treści w kodzie).
- Większość tłumaczeń **doctor** (formularz lekarza, Fitzpatrick, etykiety PDF, sekcje 1–11 itd.) pochodzi z komendy **`load_default_translations`**, nie z migracji. Migracje obejmują tylko: 1 hint (0011) i 5 komunikatów walidacji (0013).
- Aby zobaczyć faktyczną liczbę w bazie po `migrate` (bez load_default_translations):
  - `TranslationKey.objects.count()`
  - `TranslationValue.objects.count()`
