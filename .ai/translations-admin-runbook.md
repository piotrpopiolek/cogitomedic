# Runbook: Translation Operations (Administrator)

## Cel
Bezpieczna operacyjna edycja tłumaczeń DB-only (`de`, `en`, `pl`) dla kategorii:
- `doctor`
- `reception`
- `waiting_room`
- `administration`
- `other`

## 1) Pierwsze uruchomienie / seed

Uruchom (Docker):
- `docker compose run --rm web python manage.py migrate`
- `docker compose run --rm web python manage.py load_default_translations`
- `docker compose run --rm web python manage.py check_translations_completeness`

Jeżeli check zwraca błąd, nie publikuj zmian — najpierw uzupełnij brakujące języki w adminie.

## 2) Edycja tłumaczeń w Admin

1. Wejdź do `Admin -> Translation keys` i sprawdź:
   - kategorię,
   - `is_html_allowed`,
   - `allowed_placeholders`.
2. Wejdź do `Admin -> Translation values` i edytuj wartość dla właściwego `language_code`.
3. Zapis spowoduje automatyczny bump wersji cache (`TranslationCacheVersion`) przez sygnały.

## 3) Reguły bezpieczeństwa

- Dla kluczy z `is_html_allowed=false` HTML jest zabroniony.
- Dla `is_html_allowed=true` wartość jest sanityzowana (whitelist) przed zapisem.
- Dozwolony format placeholderów: `{placeholder_name}`.
- Zabronione: `%s`, `%(name)s`, `{name:.2f}`, niestandardowe tokeny.

## 4) Walidacja po zmianie

Uruchom:
- `docker compose run --rm web python manage.py check_translations_completeness`

Szybki smoke test:
- panel lekarza (`doctor`) i/lub podgląd PDF dla zmienionych kluczy,
- jeśli zmieniano `doctor.pdf_label.*`, sprawdzić PDF preview.

## 5) Rollback (awaryjny)

Opcja A (najprostsza):
1. W Admin przywróć poprzednią wartość `TranslationValue`.
2. Zapis automatycznie odświeży wersję cache.

Opcja B (z backupu DB):
1. Odtwórz rekordy `translation_value` z backupu.
2. Uruchom `check_translations_completeness`.

## 6) Zasady publikacji PDF

- `publish_locale` jest wymagane w `POST /publish`.
- Dla wersji `PUBLISHED` locale jest trwałe i audytowalne.
- PDF przy publikacji i outbox używa `version.publish_locale`.

## 7) Checklista release

- [ ] `migrate` wykonane
- [ ] `load_default_translations` wykonane (jeśli nowy env)
- [ ] `check_translations_completeness` = OK
- [ ] testy (`test-ci`) = OK
- [ ] smoke test UI/PDF = OK
